"""Generate placeholder Office Add-in icons.

Usage:  pip install Pillow && python generate_icons.py

Writes icon-16.png, icon-32.png, icon-64.png, icon-80.png, icon-128.png next to
this script. Replace with company branding before production rollout.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 32, 64, 80, 128]
BG = (0, 120, 212, 255)       # Fluent UI blue (#0078d4)
FG = (255, 255, 255, 255)     # White
TEXT = "AI"


def _font(size: int) -> ImageFont.FreeTypeFont:
    # Pillow's default is tiny; try to find a bold TrueType that exists on
    # most distros. Fall back to the bitmap default if nothing is found.
    target = max(8, int(size * 0.55))
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, target)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon(size: int, out: Path) -> None:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)
    font = _font(size)

    bbox = draw.textbbox((0, 0), TEXT, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), TEXT, font=font, fill=FG)

    img.save(out, format="PNG")


def main() -> None:
    here = Path(__file__).resolve().parent
    for s in SIZES:
        out = here / f"icon-{s}.png"
        make_icon(s, out)
        print(f"wrote {out.name} ({s}x{s})")


if __name__ == "__main__":
    main()
