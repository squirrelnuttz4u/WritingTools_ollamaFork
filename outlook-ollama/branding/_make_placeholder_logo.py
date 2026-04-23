"""One-off: produce a clearly-temporary logo.png so the rest of the build works
before the real American Consolidated Natural Resources, Inc. logo is delivered.

Replace `logo.png` with the real artwork and rerun `generate_logo_assets.py`.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT  = HERE / "logo.png"

SIZE       = 512
BG         = (178, 34, 34, 255)     # firebrick red - matches ACNR's dominant color
FG         = (255, 255, 255, 255)   # white
ACCENT     = (255, 215, 0, 255)     # gold-ish for the band under the wordmark
BORDER     = (120, 20, 20, 255)


def _font(path_candidates, size):
    for p in path_candidates:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    img = Image.new("RGBA", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(img)

    # Outer ring to hint at "this is a placeholder"
    ring = 14
    draw.rectangle([(ring, ring), (SIZE - ring, SIZE - ring)], outline=BORDER, width=6)

    # ACNR wordmark
    title_font = _font(
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "C:/Windows/Fonts/arialbd.ttf",
         "/Library/Fonts/Arial Bold.ttf"],
        220,
    )
    sub_font = _font(
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "C:/Windows/Fonts/arial.ttf",
         "/Library/Fonts/Arial.ttf"],
        34,
    )

    # main letters
    w, h = draw.textbbox((0, 0), "ACNR", font=title_font)[2:]
    draw.text(((SIZE - w) // 2, (SIZE - h) // 2 - 40), "ACNR", font=title_font, fill=FG)

    # accent bar
    bar_y = (SIZE + h) // 2 - 20
    draw.rectangle([(90, bar_y), (SIZE - 90, bar_y + 8)], fill=ACCENT)

    # subtitle
    sub = "PLACEHOLDER - REPLACE logo.png"
    w2, h2 = draw.textbbox((0, 0), sub, font=sub_font)[2:]
    draw.text(((SIZE - w2) // 2, bar_y + 24), sub, font=sub_font, fill=FG)

    img.save(OUT, format="PNG")
    print(f"wrote {OUT} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
