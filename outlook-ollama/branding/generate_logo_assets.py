"""Regenerate all downstream icon assets from logo.png and app_icon.png.

Outputs:
    branding/logo.ico                        multi-size .ico for Windows shortcuts
    branding/app_icon.ico                    multi-size .ico embedded in the exe
    addin/assets/icon-{16,32,64,80,128}.png  Office Add-in ribbon icons

The ribbon icons use `app_icon.png` (the simplified mark) if present, falling
back to `logo.png` (the full wordmark version). Both the shortcut ICO and the
PyInstaller ICO are produced.

Usage:
    pip install Pillow
    python outlook-ollama/branding/generate_logo_assets.py
"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent  # outlook-ollama/

LOGO_PATH        = HERE / "logo.png"
APP_ICON_PATH    = HERE / "app_icon.png"            # simplified mark
LOGO_ICO_OUT     = HERE / "logo.ico"
APP_ICON_ICO_OUT = HERE / "app_icon.ico"
ADDIN_ASSETS     = REPO_ROOT / "addin" / "assets"

ICON_SIZES = [16, 32, 64, 80, 128]
ICO_SIZES  = [16, 24, 32, 48, 64, 128, 256]


def _fit_square(img: Image.Image, size: int, transparent: bool = False) -> Image.Image:
    """Scale `img` into a size-x-size square PNG (preserves aspect)."""
    img = img.convert("RGBA")
    w, h = img.size
    scale = min(size / w, size / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    bg = (0, 0, 0, 0) if transparent else (255, 255, 255, 255)
    canvas = Image.new("RGBA", (size, size), bg)
    canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2), resized)
    return canvas


def _write_ico(src: Image.Image, dest: Path) -> None:
    """Save a multi-size .ico. Save the largest frame so Pillow can downscale;
    saving a smaller frame with a `sizes` list silently drops larger entries."""
    largest = max(ICO_SIZES)
    _fit_square(src, largest, transparent=True).save(
        dest, format="ICO", sizes=[(s, s) for s in ICO_SIZES]
    )


def main() -> None:
    if not LOGO_PATH.exists():
        raise SystemExit(
            f"logo.png not found at {LOGO_PATH}\n"
            "Run `python _render_logo.py` to produce it, or drop your own PNG "
            "there (square, >= 256x256 recommended, transparent bg preferred)."
        )

    logo_full = Image.open(LOGO_PATH)
    app_icon  = Image.open(APP_ICON_PATH) if APP_ICON_PATH.exists() else None

    ADDIN_ASSETS.mkdir(parents=True, exist_ok=True)

    # Office Add-in PNG ribbon icons - use the simplified mark when available.
    ribbon_source = app_icon if app_icon is not None else logo_full
    src_label = "mark" if app_icon is not None else "full"
    for s in ICON_SIZES:
        out = ADDIN_ASSETS / f"icon-{s}.png"
        _fit_square(ribbon_source, s).save(out, format="PNG")
        print(f"  wrote {out.relative_to(REPO_ROOT)} ({s}x{s}, {src_label})")

    # Start Menu / Desktop shortcut icon - full wordmark.
    _write_ico(logo_full, LOGO_ICO_OUT)
    print(f"  wrote {LOGO_ICO_OUT.relative_to(REPO_ROOT)} (sizes: {ICO_SIZES})")

    # Embedded window/tray/exe icon - simplified mark so it reads at 16x16.
    if app_icon is not None:
        _write_ico(app_icon, APP_ICON_ICO_OUT)
        print(f"  wrote {APP_ICON_ICO_OUT.relative_to(REPO_ROOT)} (sizes: {ICO_SIZES})")
    else:
        print("  (app_icon.png missing - run _render_mark.py first for a crisp tray icon)")


if __name__ == "__main__":
    main()
