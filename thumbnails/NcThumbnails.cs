// Laser Photo Studio 1.0 - picture previews for laser G-code files (.nc .gcode .gc .ngc) in File Explorer.
// Windows only draws thumbnails for picture files; for G-code it shows the icon of the program that opens it
// (LaserGRBL's "LG"). This add-on reads the file (never changes it), replays the laser moves and draws what will
// be engraved, in the material's colours when the file says which material it is for.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

[assembly: System.Reflection.AssemblyTitle("Laser Photo Studio G-code previews")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
[assembly: ComVisible(false)]

namespace LaserPhotoStudio.Thumbnails
{
    [ComImport, Guid("b824b49d-22ac-4161-ac8a-9916e8fa3f7f"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IInitializeWithStream
    {
        void Initialize(IStream stream, uint grfMode);
    }

    [ComImport, Guid("e357fccd-a995-4576-b01f-234630154e96"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IThumbnailProvider
    {
        void GetThumbnail(uint cx, out IntPtr hbitmap, out int alphaType);
    }

    [ComVisible(true), Guid("983206E5-1402-47E4-957D-D1E57EAD5DF9"), ClassInterface(ClassInterfaceType.None)]
    public sealed class NcThumbnailProvider : IInitializeWithStream, IThumbnailProvider
    {
        const int MaxBytes = 96 * 1024 * 1024;
        byte[] data;

        public void Initialize(IStream stream, uint grfMode)
        {
            using (var ms = new MemoryStream())
            {
                var buf = new byte[1 << 16];
                IntPtr read = Marshal.AllocCoTaskMem(4);
                try
                {
                    while (ms.Length < MaxBytes)
                    {
                        stream.Read(buf, buf.Length, read);
                        int n = Marshal.ReadInt32(read);
                        if (n <= 0) break;
                        ms.Write(buf, 0, n);
                    }
                }
                finally { Marshal.FreeCoTaskMem(read); }
                data = ms.ToArray();
            }
        }

        public void GetThumbnail(uint cx, out IntPtr hbitmap, out int alphaType)
        {
            hbitmap = IntPtr.Zero;
            alphaType = 0;
            int size = (int)Math.Min(Math.Max(cx, 16u), 2048u);
            Bitmap bmp = data == null ? null : Preview.Render(data, size);
            if (bmp == null) throw new COMException("No laser burning moves found.", unchecked((int)0x80004005));
            using (bmp)
            {
                hbitmap = bmp.GetHbitmap();
                alphaType = 1; // WTSAT_RGB
            }
        }
    }

    public static class Preview
    {
        struct Seg { public float X0, Y0, X1, Y1, P; }

        sealed class Parsed
        {
            public readonly List<Seg> Segs = new List<Seg>();
            public readonly HashSet<int> RowYs = new HashSet<int>();
            public readonly StringBuilder Comments = new StringBuilder();
            public double MinX = double.MaxValue, MinY = double.MaxValue, MaxX = double.MinValue, MaxY = double.MinValue;
            public double MaxS, RowLength, OtherLength;
        }

        sealed class State
        {
            public double X, Y, S, Unit = 1;
            public bool Abs = true, Laser;
            public int Motion;
        }

        static readonly Dictionary<string, int[]> Looks = new Dictionary<string, int[]>
        {   // bare material RGB, fully marked RGB (same as the app's previews)
            { "pine", new[] { 233, 203, 156, 66, 38, 22 } },
            { "lightwood", new[] { 240, 220, 182, 78, 48, 28 } },
            { "darkwood", new[] { 150, 100, 64, 40, 24, 14 } },
            { "anodized", new[] { 26, 26, 30, 206, 206, 212 } },
            { "steel", new[] { 200, 182, 128, 110, 110, 112 } },
            { "slate", new[] { 54, 57, 61, 178, 180, 182 } },
            { "leather", new[] { 196, 150, 104, 64, 36, 18 } },
            { "cardboard", new[] { 196, 166, 124, 60, 40, 24 } },
            { "tile", new[] { 242, 242, 238, 28, 28, 28 } },
            { "glass", new[] { 210, 222, 222, 40, 44, 44 } },
            { "acrylic", new[] { 16, 16, 18, 150, 150, 152 } },
            { "", new[] { 250, 250, 247, 30, 30, 30 } },
        };
        static readonly HashSet<string> Woody = new HashSet<string> { "pine", "lightwood", "darkwood", "leather", "cardboard" };

        public static Bitmap RenderFile(string path, int size)
        {
            return Render(File.ReadAllBytes(path), size);
        }

        public static Bitmap Render(byte[] data, int size)
        {
            Parsed p = Parse(data);
            if (p.Segs.Count == 0 || p.MaxS <= 0) return null;
            double pitch = Pitch(p);
            double w = Math.Max(p.MaxX - p.MinX, pitch), h = Math.Max(p.MaxY - p.MinY, pitch);
            double pad = Math.Max(w, h) * 0.05 + pitch;
            double x0 = p.MinX - pad, yTop = p.MaxY + pad, ww = w + 2 * pad, hh = h + 2 * pad;
            double scale = size / Math.Max(ww, hh);
            int W = Math.Max(1, (int)Math.Round(ww * scale)), H = Math.Max(1, (int)Math.Round(hh * scale));
            var acc = new float[W * H];
            double thick = pitch * scale, lineW = Math.Max(thick, 1.0);
            bool raster = p.RowLength >= 4 * p.OtherLength;
            float inv = (float)(1.0 / p.MaxS);
            foreach (Seg sg in p.Segs)
            {
                float pw = sg.P * inv;
                if (Math.Abs(sg.Y1 - sg.Y0) < 1e-6f)
                    Row(acc, W, H, (Math.Min(sg.X0, sg.X1) - x0) * scale, (Math.Max(sg.X0, sg.X1) - x0) * scale,
                        (yTop - sg.Y0) * scale, raster ? thick : lineW, pw);
                else
                    Stroke(acc, W, H, (sg.X0 - x0) * scale, (yTop - sg.Y0) * scale, (sg.X1 - x0) * scale,
                           (yTop - sg.Y1) * scale, lineW, pw);
            }
            string look = Look(p.Comments.ToString());
            int[] col = Looks[look];
            bool woody = Woody.Contains(look);
            float top = Math.Max(Percentile(acc, 0.995), 0.5f);
            double norm = 1 - Math.Exp(-2.4);
            var bmp = new Bitmap(W, H, PixelFormat.Format24bppRgb);
            BitmapData bd = bmp.LockBits(new Rectangle(0, 0, W, H), ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
            try
            {
                var row = new byte[bd.Stride];
                for (int y = 0; y < H; y++)
                {
                    for (int x = 0; x < W; x++)
                    {
                        double v = Math.Max(0, acc[y * W + x] / top);
                        double d = woody ? (1 - Math.Exp(-2.4 * v)) / norm : v;
                        if (d > 1) d = 1;
                        row[x * 3 + 2] = (byte)(col[0] + (col[3] - col[0]) * d);
                        row[x * 3 + 1] = (byte)(col[1] + (col[4] - col[1]) * d);
                        row[x * 3 + 0] = (byte)(col[2] + (col[5] - col[2]) * d);
                    }
                    Marshal.Copy(row, 0, bd.Scan0 + y * bd.Stride, bd.Stride);
                }
            }
            finally { bmp.UnlockBits(bd); }
            return bmp;
        }

        // ------------------------------------------------------------------------------------------ G-code
        static Parsed Parse(byte[] data)
        {
            var p = new Parsed();
            var st = new State();
            string t = Encoding.ASCII.GetString(data);
            int pos = 0, len = t.Length;
            while (pos < len)
            {
                int end = t.IndexOf('\n', pos);
                if (end < 0) end = len;
                Line(t, pos, end, p, st);
                pos = end + 1;
            }
            return p;
        }

        static void Line(string t, int a, int b, Parsed p, State st)
        {
            while (a < b && (t[a] == ' ' || t[a] == '\t')) a++;
            if (a >= b || t[a] == '$' || t[a] == '%') return; // Grbl system commands ($H, $J=...) never burn
            double nx = double.NaN, ny = double.NaN, ni = double.NaN, nj = double.NaN;
            int i = a;
            while (i < b)
            {
                char c = t[i];
                if (c == ';') { Comment(p, t, i, b); break; }
                if (c == '(')
                {
                    int close = t.IndexOf(')', i);
                    if (close < 0 || close > b) close = b;
                    Comment(p, t, i, close);
                    i = close + 1;
                    continue;
                }
                if (c >= 'a' && c <= 'z') c = (char)(c - 32);
                if (c < 'A' || c > 'Z') { i++; continue; }
                int j = i + 1;
                while (j < b && t[j] == ' ') j++;
                int k = j;
                while (k < b && ((t[k] >= '0' && t[k] <= '9') || t[k] == '.' || t[k] == '-' || t[k] == '+')) k++;
                i = Math.Max(k, i + 1);
                double v;
                if (k == j || !double.TryParse(t.Substring(j, k - j), NumberStyles.Float, CultureInfo.InvariantCulture, out v))
                    continue;
                int code = (int)Math.Round(v);
                bool whole = Math.Abs(v - code) < 1e-6;
                switch (c)
                {
                    case 'G':
                        if (!whole) break;
                        if (code >= 0 && code <= 3) st.Motion = code;
                        else if (code == 90) st.Abs = true;
                        else if (code == 91) st.Abs = false;
                        else if (code == 20) st.Unit = 25.4;
                        else if (code == 21) st.Unit = 1;
                        break;
                    case 'M':
                        if (code == 3 || code == 4) st.Laser = true;
                        else if (code == 5) st.Laser = false;
                        break;
                    case 'S': st.S = v; break;
                    case 'X': nx = v; break;
                    case 'Y': ny = v; break;
                    case 'I': ni = v; break;
                    case 'J': nj = v; break;
                }
            }
            if (double.IsNaN(nx) && double.IsNaN(ny)) return;
            double tx = double.IsNaN(nx) ? st.X : (st.Abs ? nx * st.Unit : st.X + nx * st.Unit);
            double ty = double.IsNaN(ny) ? st.Y : (st.Abs ? ny * st.Unit : st.Y + ny * st.Unit);
            if (st.Laser && st.S > 0 && st.Motion != 0)
            {
                if (st.Motion == 1 || (double.IsNaN(ni) && double.IsNaN(nj)))
                    Add(p, st.X, st.Y, tx, ty, st.S);
                else
                    Arc(p, st, tx, ty, double.IsNaN(ni) ? 0 : ni * st.Unit, double.IsNaN(nj) ? 0 : nj * st.Unit);
            }
            st.X = tx;
            st.Y = ty;
        }

        static void Comment(Parsed p, string t, int a, int b)
        {
            if (p.Comments.Length < 8000) p.Comments.Append(t, a, Math.Min(b - a, 400)).Append('\n');
        }

        static void Arc(Parsed p, State st, double tx, double ty, double i, double j)
        {
            double cx = st.X + i, cy = st.Y + j, r = Math.Sqrt(i * i + j * j);
            double a0 = Math.Atan2(st.Y - cy, st.X - cx), a1 = Math.Atan2(ty - cy, tx - cx);
            bool cw = st.Motion == 2;
            double sweep = cw ? a0 - a1 : a1 - a0;
            while (sweep <= 1e-9) sweep += 2 * Math.PI;
            int n = (int)Math.Min(720, Math.Max(4, Math.Ceiling(r * sweep / 0.3)));
            double px = st.X, py = st.Y;
            for (int k = 1; k <= n; k++)
            {
                double a = a0 + (cw ? -1 : 1) * sweep * k / n;
                double qx = k == n ? tx : cx + r * Math.Cos(a), qy = k == n ? ty : cy + r * Math.Sin(a);
                Add(p, px, py, qx, qy, st.S);
                px = qx;
                py = qy;
            }
        }

        static void Add(Parsed p, double x0, double y0, double x1, double y1, double s)
        {
            p.Segs.Add(new Seg { X0 = (float)x0, Y0 = (float)y0, X1 = (float)x1, Y1 = (float)y1, P = (float)s });
            p.MinX = Math.Min(p.MinX, Math.Min(x0, x1));
            p.MaxX = Math.Max(p.MaxX, Math.Max(x0, x1));
            p.MinY = Math.Min(p.MinY, Math.Min(y0, y1));
            p.MaxY = Math.Max(p.MaxY, Math.Max(y0, y1));
            if (s > p.MaxS) p.MaxS = s;
            double len = Math.Sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0));
            if (Math.Abs(y1 - y0) < 1e-6)
            {
                p.RowLength += len;
                if (p.RowYs.Count < 400000) p.RowYs.Add((int)Math.Round(y0 * 1000));
            }
            else p.OtherLength += len;
        }

        static double Pitch(Parsed p)
        {   // the most common gap between neighbouring raster rows (0.1 mm for most jobs)
            if (p.RowYs.Count < 3) return 0.1;
            var ys = new List<int>(p.RowYs);
            ys.Sort();
            var counts = new Dictionary<int, int>();
            for (int k = 1; k < ys.Count; k++)
            {
                int d = ys[k] - ys[k - 1];
                if (d >= 20 && d <= 1000) { int c; counts.TryGetValue(d, out c); counts[d] = c + 1; }
            }
            int best = 100, bestCount = 0;
            foreach (var kv in counts) if (kv.Value > bestCount) { best = kv.Key; bestCount = kv.Value; }
            return best / 1000.0;
        }

        static string Look(string comments)
        {
            string c = comments.ToLowerInvariant();
            int i = c.IndexOf("look:", StringComparison.Ordinal);
            if (i >= 0)
            {
                int a = i + 5;
                while (a < c.Length && c[a] == ' ') a++;
                int b = a;
                while (b < c.Length && char.IsLetter(c[b])) b++;
                string key = c.Substring(a, b - a);
                if (Looks.ContainsKey(key)) return key;
            }
            if (c.Contains("anodiz")) return "anodized";
            if (c.Contains("slate")) return "slate";
            if (c.Contains("acrylic")) return "acrylic";
            if (c.Contains("pine") || c.Contains("plank")) return "pine";
            if (c.Contains("jar lid") || c.Contains("steel")) return "steel";
            return "";
        }

        // ------------------------------------------------------------------------------------------ drawing
        static void Row(float[] acc, int W, int H, double xa, double xb, double yc, double t, float pw)
        {
            if (xb <= xa) return;
            double top = yc - t / 2, bot = yc + t / 2;
            int r0 = Math.Max(0, (int)Math.Floor(top)), r1 = Math.Min(H - 1, (int)Math.Floor(bot));
            int c0 = Math.Max(0, (int)Math.Floor(xa)), c1 = Math.Min(W - 1, (int)Math.Ceiling(xb) - 1);
            for (int r = r0; r <= r1; r++)
            {
                double fy = Math.Min(bot, r + 1) - Math.Max(top, r);
                if (fy <= 0) continue;
                int o = r * W;
                for (int c = c0; c <= c1; c++)
                {
                    double fx = Math.Min(xb, c + 1) - Math.Max(xa, c);
                    if (fx > 0) acc[o + c] += (float)(pw * fx * fy);
                }
            }
        }

        static void Stroke(float[] acc, int W, int H, double xa, double ya, double xb, double yb, double width, float pw)
        {
            double dx = xb - xa, dy = yb - ya, len = Math.Sqrt(dx * dx + dy * dy);
            if (len <= 0) return;
            int n = (int)Math.Ceiling(len / 0.5);
            float amount = (float)(pw * (len / n) * width);
            for (int k = 0; k < n; k++)
            {
                double f = (k + 0.5) / n;
                double x = xa + dx * f - 0.5, y = ya + dy * f - 0.5;
                int ix = (int)Math.Floor(x), iy = (int)Math.Floor(y);
                float fx = (float)(x - ix), fy = (float)(y - iy);
                Put(acc, W, H, ix, iy, amount * (1 - fx) * (1 - fy));
                Put(acc, W, H, ix + 1, iy, amount * fx * (1 - fy));
                Put(acc, W, H, ix, iy + 1, amount * (1 - fx) * fy);
                Put(acc, W, H, ix + 1, iy + 1, amount * fx * fy);
            }
        }

        static void Put(float[] acc, int W, int H, int x, int y, float v)
        {
            if (x >= 0 && y >= 0 && x < W && y < H) acc[y * W + x] += v;
        }

        static float Percentile(float[] acc, double q)
        {
            int nonzero = 0;
            foreach (float v in acc) if (v > 0) nonzero++;
            if (nonzero == 0) return 1;
            int stride = Math.Max(1, nonzero / 250000);
            var vals = new List<float>(nonzero / stride + 1);
            int seen = 0;
            foreach (float v in acc)
                if (v > 0 && (seen++ % stride) == 0) vals.Add(v);
            vals.Sort();
            return vals[Math.Min(vals.Count - 1, (int)(q * vals.Count))];
        }
    }
}
