"""
Generate Nova's app icons.

PNG/ICO files are binary, so they are not stored in git. SETUP.bat runs this
once and the icons appear in static/icons/. Run it yourself any time with:

    python tools/make_icons.py
"""
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

BG_TOP = (13, 17, 23)
BG_BOT = (26, 35, 56)
STAR = (109, 168, 255)
STAR_HI = (231, 241, 255)


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def four_point_star(draw, cx, cy, outer, inner, colour):
    """A sparkle: four long points with concave sides."""
    pts = []
    for i in range(8):
        angle = math.pi / 2 * (i / 2) - math.pi / 2
        r = outer if i % 2 == 0 else inner
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=colour)


def make(size):
    img = Image.new("RGB", (size, size), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(1, size - 1)
        d.line([(0, y), (size, y)], fill=(
            int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t),
            int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t),
            int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t),
        ))

    c = size / 2
    four_point_star(d, c, c * 0.98, size * 0.40, size * 0.085, STAR)
    four_point_star(d, c, c * 0.98, size * 0.26, size * 0.055, STAR_HI)
    four_point_star(d, size * 0.775, size * 0.245, size * 0.105, size * 0.022, STAR)
    four_point_star(d, size * 0.235, size * 0.755, size * 0.075, size * 0.016, STAR)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), rounded_mask(size, int(size * 0.22)))
    return out


base = str(Path(__file__).resolve().parent.parent / "static" / "icons")
os.makedirs(base, exist_ok=True)

for s in (192, 512):
    make(s).save(f"{base}/nova-{s}.png")
    print("wrote", f"nova-{s}.png")

mask = Image.new("RGBA", (512, 512), (13, 17, 23, 255))
inner = make(360)
mask.paste(inner, (76, 76), inner)
mask.save(f"{base}/nova-maskable-512.png")
print("wrote nova-maskable-512.png")

make(256).save(f"{base}/nova.ico",
               sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote nova.ico")

make(180).convert("RGB").save(f"{base}/apple-touch-icon.png")
print("wrote apple-touch-icon.png")
