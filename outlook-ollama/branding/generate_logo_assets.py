"""Regenerate all downstream icon assets from logo.png (and optional logo-mark.png).

Outputs:
    branding/logo.ico                        multi-size .ico for Windows shortcuts
    addin/assets/icon-{16,32,64,80,128}.png  Office Add-in ribbon icons

If a square `logo-mark.png` exists next to `logo.png`, it is used for the small
ribbon sizes (16/32) where the full wordmark becomes illegible. Otherwise the
full logo is used everywhere.

Usage:
    pip install Pillow
    python outlook-ollama/branding/generate_logo_assets.py
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent  # outlook-ollama/

LOGO_PATH     = HERE / "logo.png"
LOGO_MARK     = HERE / "logo-mark.png"      # optional
ICO_OUT       = HERE / "logo.ico"
ADDIN_ASSETS  = REPO_ROOT / "addin" / "assets"

# sizes that appear in manifest.xml
ICON_SIZES = [16, 32, 64, 80, 128]
ICO_SIZES  = [16, 24, 32, 48, 64, 128, 256]

SMALL_THRESHOLD = 32  # sizes <= this prefer logo-mark.png if present


def _fit_square(img: Image.Image, size: int) -> Image.Image:
    """Scale `img` into a size-x-size square PNG on a white background (preserves aspect)."""
    img = img.convert("RGBA")
    w, h = img.size
    scale = min(size / w, size / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2), resized)
    return canvas


def main() -> None:
    if not LOGO_PATH.exists():
        raise SystemExit(
            f"logo.png not found at {LOGO_PATH}\n"
            "Drop your company logo there (square PNG, >= 256x256 recommended, "
            "transparent background preferred), then re-run this script."
        )

    logo_full = Image.open(LOGO_PATH)
    logo_mark = Image.open(LOGO_MARK) if LOGO_MARK.exists() else None

    ADDIN_ASSETS.mkdir(parents=True, exist_ok=True)

    # Office Add-in PNG ribbon icons
    for s in ICON_SIZES:
        source = logo_mark if (logo_mark is not None and s <= SMALL_THRESHOLD) else logo_full
        out = ADDIN_ASSETS / f"icon-{s}.png"
        _fit_square(source, s).save(out, format="PNG")
        src = "mark" if source is logo_mark else "full"
        print(f"  wrote {out.relative_to(REPO_ROOT)} ({s}x{s}, {src})")

    # Multi-size .ico for Windows shortcut. Save the largest frame so Pillow
    # can downscale; saving a smaller frame with a `sizes` list would silently
    # drop the larger entries.
    largest = max(ICO_SIZES)
    _fit_square(logo_full, largest).save(
        ICO_OUT, format="ICO", sizes=[(s, s) for s in ICO_SIZES]
    )
    print(f"  wrote {ICO_OUT.relative_to(REPO_ROOT)} (sizes: {ICO_SIZES})")


if __name__ == "__main__":
    main()
