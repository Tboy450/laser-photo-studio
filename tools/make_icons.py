"""Draw the two desktop icons into ../assets (only needed if you want to change them)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parents[1] / "assets"
S = 512


def rounded(draw, box, r, **kw):
    draw.rounded_rectangle(box, radius=r, **kw)


def studio_icon():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    for y in range(S):  # warm wood gradient
        t = y / S
        d.line([(0, y), (S, y)], fill=(int(236 - 40 * t), int(196 - 52 * t), int(140 - 50 * t), 255))
    mask = Image.new("L", (S, S), 0)
    rounded(ImageDraw.Draw(mask), (16, 16, S - 16, S - 16), 96, fill=255)
    im.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(im)
    # engraved scene: mountains + moon + rows
    d.polygon([(70, 400), (190, 210), (250, 300), (320, 170), (450, 400)], fill=(92, 56, 30, 255))
    d.polygon([(165, 252), (190, 210), (214, 250), (198, 242), (184, 256)], fill=(236, 214, 178, 255))
    d.polygon([(292, 216), (320, 170), (348, 216), (330, 206), (312, 220)], fill=(236, 214, 178, 255))
    for y in (357, 388):
        d.line([(104, y), (419, y)], fill=(224, 169, 114, 255), width=12)
    # laser beam and bright dot
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.line([(470, 30), (356, 300)], fill=(255, 40, 40, 200), width=26)
    g.ellipse((326, 270, 386, 330), fill=(255, 60, 60, 230))
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    im.alpha_composite(glow)
    d.line([(454, 66), (356, 300)], fill=(156, 28, 20, 255), width=32)
    d.line([(454, 66), (356, 300)], fill=(255, 239, 197, 255), width=15)
    d.ellipse((333, 277, 379, 323), fill=(255, 241, 208, 255), outline=(156, 28, 20, 255), width=7)
    rounded(d, (16, 16, S - 16, S - 16), 96, outline=(70, 42, 22, 255), width=10)
    return im


def job_icon():
    icon = studio_icon()
    draw = ImageDraw.Draw(icon)
    draw.polygon([(325, 272), (455, 272), (499, 316), (499, 495), (325, 495)],
                 fill=(34, 37, 46, 255))
    draw.polygon([(348, 294), (445, 294), (478, 327), (478, 473), (348, 473)],
                 fill=(249, 236, 208, 255))
    draw.polygon([(445, 294), (478, 327), (445, 327)], fill=(179, 129, 82, 255))
    for y in (359, 399, 439):
        draw.line((370, y, 453, y), fill=(106, 65, 37, 255), width=17)
    return icon


def perimeter_icon():
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rounded(d, (16, 16, S - 16, S - 16), 96, fill=(28, 34, 44, 255), outline=(12, 14, 18, 255), width=10)
    x0, y0, x1, y1 = 110, 130, 402, 382
    for k in range(x0, x1, 34):  # dashed frame
        d.line([(k, y0), (min(k + 20, x1), y0)], fill=(205, 210, 220, 255), width=10)
        d.line([(k, y1), (min(k + 20, x1), y1)], fill=(205, 210, 220, 255), width=10)
    for k in range(y0, y1, 34):
        d.line([(x0, k), (x0, min(k + 20, y1))], fill=(205, 210, 220, 255), width=10)
        d.line([(x1, k), (x1, min(k + 20, y1))], fill=(205, 210, 220, 255), width=10)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        g.ellipse((cx - 46, cy - 46, cx + 46, cy + 46), fill=(255, 40, 40, 210))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im)
    for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        d.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), fill=(255, 250, 250, 255))
    d.text((180, 220), "1%", fill=(255, 120, 120, 255), font_size=96)
    return im


if __name__ == "__main__":
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ASSETS.mkdir(exist_ok=True)
    studio_icon().save(ASSETS / "icon.ico", sizes=sizes)
    job_icon().save(ASSETS / "job.ico", sizes=sizes)
    perimeter_icon().save(ASSETS / "perimeter.ico", sizes=sizes)
    print("icons written to", ASSETS)
