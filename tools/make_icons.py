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
    for k in range(9):  # grain
        y0 = 40 + k * 52
        d.arc((-200, y0 - 30, S + 200, y0 + 60), 190, 350, fill=(178, 128, 80, 90), width=4)
    mask = Image.new("L", (S, S), 0)
    rounded(ImageDraw.Draw(mask), (16, 16, S - 16, S - 16), 96, fill=255)
    im.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(im)
    # engraved scene: mountains + moon + rows
    d.polygon([(70, 400), (190, 210), (250, 300), (320, 170), (450, 400)], fill=(92, 56, 30, 255))
    d.polygon([(165, 252), (190, 210), (214, 250), (198, 242), (184, 256)], fill=(236, 214, 178, 255))
    d.polygon([(292, 216), (320, 170), (348, 216), (330, 206), (312, 220)], fill=(236, 214, 178, 255))
    for y in range(330, 400, 12):
        d.line([(80, y), (440, y)], fill=(236, 214, 178, 120), width=3)
    d.ellipse((96, 96, 150, 150), outline=(92, 56, 30, 255), width=8)
    # laser beam and bright dot
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.line([(470, 30), (356, 300)], fill=(255, 40, 40, 200), width=26)
    g.ellipse((326, 270, 386, 330), fill=(255, 60, 60, 230))
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    im.alpha_composite(glow)
    d.line([(470, 30), (356, 300)], fill=(255, 235, 235, 255), width=8)
    d.ellipse((342, 286, 370, 314), fill=(255, 255, 255, 255))
    rounded(d, (16, 16, S - 16, S - 16), 96, outline=(70, 42, 22, 255), width=10)
    return im


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
    perimeter_icon().save(ASSETS / "perimeter.ico", sizes=sizes)
    print("icons written to", ASSETS)
