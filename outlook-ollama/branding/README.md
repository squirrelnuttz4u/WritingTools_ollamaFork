# Branding assets

All product naming + iconography for **ACNR Intelligence** flows from this folder.

## Drop the real logo here

Save the American Consolidated Natural Resources, Inc. logo as **`logo.png`**
in this directory. Guidelines:

- **Square** canvas (the app icon, ribbon icon, and shortcut icon are all
  square). If your master logo is wide, render a square version with the
  wordmark centered on a white or transparent background.
- **At least 256x256**, 512x512 preferred. The generator downscales with
  Lanczos filtering, so oversized sources are fine.
- **PNG** with transparent background preferred (keeps it clean on dark
  Outlook themes and Start Menu).

## Optional: small-size mark

Save a simplified square mark (no wordmark, just the map silhouette or
monogram) as `logo-mark.png` in this folder. It will be used automatically
for the 16 px and 32 px ribbon icons where the full wordmark is illegible.
If you don't provide one, the full logo is used at all sizes.

## Regenerate derived assets

After replacing `logo.png`:

```bash
pip install Pillow
python outlook-ollama/branding/generate_logo_assets.py
```

This rewrites:

| Output | Used by |
| --- | --- |
| `branding/logo.ico`                 | Start Menu + Desktop shortcuts |
| `addin/assets/icon-16.png`          | Outlook ribbon (small) |
| `addin/assets/icon-32.png`          | Outlook ribbon (medium) |
| `addin/assets/icon-64.png`          | `IconUrl` in manifest.xml |
| `addin/assets/icon-80.png`          | Outlook ribbon (large) |
| `addin/assets/icon-128.png`         | `HighResolutionIconUrl` |

The task pane (`addin/taskpane.html`) loads `./assets/icon-64.png` directly -
once you regenerate, the header image in Outlook updates automatically.

## Placeholder

A stand-in `logo.png` is committed so nothing is blocked waiting for the real
artwork. It's a red square with "ACNR" and the word **PLACEHOLDER** across it,
so if you ever see it in Outlook you'll know the real logo didn't get dropped
in. To regenerate the placeholder (useful only if you delete it):

```bash
python outlook-ollama/branding/_make_placeholder_logo.py
```
