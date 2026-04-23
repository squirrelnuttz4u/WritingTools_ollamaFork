# ACNR Intelligence

An in-house AI rewrite / summarize experience for Microsoft Outlook and the
rest of the Windows desktop, powered entirely by ACNR's internal Ollama
server. Ships three complementary paths: a one-command standalone install
for immediate testing, a managed Intune rollout of a rebranded WritingTools
build (system-wide hotkey), and a production-ready Office.js Outlook add-in
that lives in the ribbon. Plus guidance about the VSTO/COM dead-end so
nobody wastes time on it.

## Deployment paths

| Path | Integration | Platforms | Effort | When to pick |
| --- | --- | --- | --- | --- |
| A. WritingTools + Intune | System-wide hotkey | Windows / Mac / Linux | Hours | Pilot this week; serves whole Office suite + Teams + browser |
| B. Office.js Outlook add-in (this repo) | Outlook ribbon button | Classic + new Outlook Windows, Mac, web, mobile (read) | ~1 week | Production Outlook rollout, future-proof |
| C. VSTO / COM add-in | Outlook ribbon | Classic Outlook Windows only | - | **Don't.** Microsoft is killing it - unsupported in new Outlook and enterprise default switches April 2026. |

> **Warning:** VSTO and COM add-ins are **not supported in new Outlook on Windows**,
> which becomes the enterprise default in April 2026. Building one today means
> reshipping it inside 12 months. See Microsoft's
> [One Outlook add-in guidance](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/one-outlook).

## Before first build: drop the real logo

`outlook-ollama/branding/logo.png` is currently a **placeholder** (red square
with "ACNR" across it). Replace it with the real ACNR logo (square PNG,
>= 256x256, transparent background preferred) and rerun:

```bash
pip install Pillow
python outlook-ollama/branding/generate_logo_assets.py
```

That regenerates `branding/logo.ico` and the `addin/assets/icon-*.png` ribbon
icons. The task pane and shortcuts pick up the new artwork automatically on
the next install. See `branding/README.md` for details.

## Repo layout

```
outlook-ollama/
├── branding/                        ACNR logo and icon generator
│   ├── logo.png                     master artwork (replace placeholder)
│   ├── logo.ico                     multi-size Windows icon (auto-generated)
│   └── generate_logo_assets.py      rebuilds .ico + ribbon PNGs
├── backend/                         Flask proxy to Ollama (for Path B)
│   ├── app.py                       /rewrite /summarize /generate /generate_sse /models /health
│   ├── requirements.txt
│   ├── Dockerfile                   gunicorn, HEALTHCHECK
│   ├── docker-compose.yml           proxy + Caddy for TLS
│   ├── Caddyfile
│   └── test_app.py                  pytest unit tests
├── addin/                           Office.js Outlook add-in (ACNR Intelligence)
│   ├── manifest.xml                 Ribbon buttons for compose + read
│   ├── taskpane.html
│   ├── taskpane.css
│   ├── taskpane.js
│   └── assets/                      Ribbon icons (generated from branding/)
├── deployment/
│   ├── Install-WritingToolsStandalone.ps1   Path A1 - zero-infra local test
│   └── Build-WritingToolsIntunePackage.ps1  Path A2 - managed Intune rollout
└── README.md                        (this file)
```

## Path A (quick test) - Standalone install on your own machine

Zero infrastructure, no admin, no Intune. Hardcoded to ACNR's lab Ollama server
at `http://192.168.203.100:11434` with model `cogito:32b`. Run on any Windows
box that can reach that IP:

```powershell
cd outlook-ollama\deployment
.\Install-WritingToolsStandalone.ps1
```

Optional parameters (all have sensible defaults):

```powershell
.\Install-WritingToolsStandalone.ps1 `
    -OllamaUrl   "http://192.168.203.100:11434" `
    -OllamaModel "cogito:32b" `
    -Shortcut    "ctrl+space" `
    -Force          # skip overwrite prompt
    -NoLaunch       # install only, don't start it
```

It downloads the latest WritingTools release, extracts to
`%LOCALAPPDATA%\ACNRIntelligence`, writes `config.json` next to the exe
pointing at your Ollama, bundles `branding/logo.ico` as the shortcut icon,
creates Start Menu + Desktop shortcuts named **"ACNR Intelligence"**, probes
`/api/tags` to confirm reachability, and launches the app. Press `Ctrl+Space`
over any selected text to rewrite. Uninstall = delete
`%LOCALAPPDATA%\ACNRIntelligence` and the two shortcuts.

## Path A (managed rollout) - ACNR Intelligence via Intune

On a Windows machine with PowerShell 5.1+:

```powershell
cd outlook-ollama\deployment
.\Build-WritingToolsIntunePackage.ps1           # uses ACNR lab defaults
# or override:
.\Build-WritingToolsIntunePackage.ps1 `
    -OllamaUrl   "http://192.168.203.100:11434" `
    -OllamaModel "cogito:32b"
```

The script downloads the latest WritingTools release, writes a correct
`config.json` (native Ollama provider, nested shape, placed next to the exe
where the app actually reads it), bundles `branding/logo.ico` as the Start
Menu icon, and emits a `.intunewin` under `WritingTools-Intune\output\`. App
name in Start Menu / Programs & Features: **ACNR Intelligence**.

In Intune:

1. **Apps → Windows → Add → Windows app (Win32)** and upload the `.intunewin`.
2. Install command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1`
3. Uninstall command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File uninstall.ps1`
4. **Detection rule → Custom script** → upload `detection.ps1`.
5. Install behavior: **System**.
6. Assign to a pilot Entra ID group first, then widen.

Users get a Start Menu shortcut, and on first logon a scheduled task copies the
pre-seeded config into their `%APPDATA%\Writing Tools\config.json`. They press
the hotkey (default `Ctrl+Space`) anywhere - Outlook, Word, Teams, browser - to
rewrite selected text against your internal Ollama.

## Path B - Office.js Outlook Add-in

### 1. Stand up the backend

```bash
cd outlook-ollama/backend
# edit docker-compose.yml: OLLAMA_URL, OLLAMA_MODEL, CORS_ORIGINS, API_KEY
docker compose up -d --build
docker compose logs -f ollama-proxy
curl https://llm.corp.example.com/health
```

Caddy terminates TLS on :443 and reverse-proxies to the Flask app. If you
already have a reverse proxy (F5, Nginx, IIS ARR), point it at
`ollama-proxy:5000` and drop the Caddy service.

### 2. Host the static add-in files

The four files under `addin/` (`taskpane.html`, `taskpane.css`, `taskpane.js`,
`assets/*`) must be served over HTTPS from a corporate-trusted hostname.
Any of these work:

- **Nginx / Caddy / IIS** on a VM - simplest if you already run web servers.
- **Azure Blob Storage** with the static website feature + a CDN/Front Door.
- **SharePoint Online** library fronted by Microsoft 365 CDN.
- **GitHub Pages / internal GitHub Enterprise Pages** for small pilots.

End state: `https://addin.corp.example.com/taskpane.html` returns the page.

### 3. Pre-deployment edits

Before packaging the manifest:

- `addin/taskpane.js` - replace `BACKEND_URL` with your public proxy URL; set
  `API_KEY` if the backend's `API_KEY` env var is set.
- `addin/manifest.xml` - replace every `https://addin.corp.example.com` with
  your actual HTTPS hostname.
- `addin/manifest.xml` - regenerate the `<Id>` GUID:
  `[guid]::NewGuid()` (PowerShell) or `uuidgen` (Linux/Mac).
- `addin/assets/` - replace the placeholder PNGs with your brand.

Validate the manifest: `npx office-addin-manifest validate addin/manifest.xml`.

### 4. Centralized Deployment (M365)

1. Go to [admin.microsoft.com](https://admin.microsoft.com) → **Settings →
   Integrated apps → Upload custom apps**.
2. Choose **Office Add-in** and upload the edited `manifest.xml`.
3. Assign to a pilot Entra ID group, then expand to the org.

The button appears in the Outlook ribbon for assigned users across classic
Outlook Windows, new Outlook Windows, Outlook on the web, and Outlook for Mac
within ~24 hours. One codebase, every surface.

### 5. Local sideload for dev/testing

**Classic Outlook (Windows)**
- File → Options → Trust Center → Trust Center Settings → Trusted Add-in
  Catalogs. Add a network share containing the manifest, tick **Show in menu**,
  restart Outlook.

**New Outlook / Outlook on the web**
- Browse to [https://aka.ms/olksideload](https://aka.ms/olksideload) and upload
  the manifest under **My add-ins → Custom Addins**.

## Integration surface

**Compose mode (drafting or replying to an email):**
- "AI Rewrite" ribbon button opens the task pane.
- Tone picker (professional / friendly / concise / formal / assertive /
  apologetic / grammar-only) plus a free-text instruction box.
- "Rewrite draft" reads the current body via Office.js, sends it to
  `/rewrite`, shows the result. "Insert into email" replaces the body.

**Read mode (viewing a received email):**
- "AI Summarize" ribbon button opens the task pane.
- Returns TL;DR + key points + action items in plain text.
- "Copy summary" puts it on the clipboard.

## Security notes

- **`API_KEY`** - set a long random bearer secret on the backend and mirror it
  into `taskpane.js`. Leaving it blank is fine for an air-gapped LAN; required
  for anything internet-reachable.
- **`CORS_ORIGINS`** - list the *exact* HTTPS origin(s) where the add-in is
  hosted. Wildcard `*` only for early dev.
- **TLS is mandatory** - Office add-ins refuse to load non-HTTPS resources. The
  bundled Caddy config is there for exactly this.
- **Office.js from CDN** - `appsforoffice.microsoft.com/lib/1/hosted/office.js`
  must be reachable from every client. You cannot self-host it; Microsoft
  signs and updates it. If your proxy blocks Microsoft CDNs, whitelist it.
- **Data boundary** - email bodies travel client → your proxy → your Ollama
  server. Nothing goes to external LLM vendors. Log retention on the proxy is
  your call - default config logs to stdout only.

## Sizing the Ollama backend

| Users | Concurrent requests | Recommended model | GPU |
| --- | --- | --- | --- |
| <50 | 1-3 | `llama3.1:8b` | 1x 16 GB (L4) |
| 50-500 | 5-15 | `llama3.1:8b` or `qwen2.5:14b` | 1-2x 24 GB (A10 / L4 / L40) |
| 500+ | 15-50 | Quantized 70b, or horizontally scaled 8b behind a load balancer | 2-4x A100 / H100 |

A **fast 8B usually beats a slow 70B** on perceived UX for rewrite workloads.
Users care about latency-to-first-token on a ~200-word email - not leaderboard
scores. Start at 8B, measure, only size up if the writing quality bar is not
met.
