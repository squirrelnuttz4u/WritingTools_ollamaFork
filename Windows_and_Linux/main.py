import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _setup_logging():
    """
    Configure logging to file plus stderr.

    --windowed PyInstaller builds have no console, so anything written to
    stderr goes nowhere. We always tee to a rotating log file so users can
    grab diagnostics when something goes wrong.

    Log location order of preference:
      1. Next to the exe (writeable installs)
      2. %LOCALAPPDATA%\\ACNRIntelligence\\ (when ProgramFiles is read-only)
      3. %TEMP%\\acnr-intelligence.log
    """
    candidates = []
    try:
        if getattr(sys, 'frozen', False):
            candidates.append(os.path.dirname(sys.executable))
        else:
            candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
    candidates.append(os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                                   'ACNRIntelligence'))
    candidates.append(os.environ.get('TEMP', '/tmp'))

    log_path = None
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            candidate = os.path.join(d, 'acnr-intelligence.log')
            with open(candidate, 'a'):
                pass
            log_path = candidate
            break
        except OSError:
            continue

    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # File handler (always)
    if log_path:
        fh = RotatingFileHandler(log_path, maxBytes=512 * 1024, backupCount=2, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Stream handler (visible only if there is a console)
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    return log_path


def _dump_startup_diagnostics(log_path):
    """Emit a banner that tells us where the app is reading resources from.

    Every recurring "tray icon missing / logo missing / buttons unstyled"
    bug we've hit has been a path mismatch. This dump catches it instantly:
    paste the first ~30 lines of the log and we know which dir the app saw,
    and which expected files were actually there.
    """
    log = logging.getLogger('acnr.startup')
    log.info('=' * 70)
    log.info('ACNR Intelligence starting up')
    log.info('=' * 70)
    log.info(f'Log file: {log_path}')
    log.info(f'Python:   {sys.version.split()[0]}')
    log.info(f'Frozen:   {bool(getattr(sys, "frozen", False))}')
    log.info(f'sys.executable: {sys.executable}')
    log.info(f'sys.argv:       {sys.argv}')

    try:
        from ui.UIUtils import app_dir, theme, colorMode
        d = app_dir()
        log.info(f'app_dir():     {d}')
        log.info(f'theme:         {theme}')
        log.info(f'colorMode:     {colorMode}')

        expected = [
            'ACNR Intelligence.exe',
            'options.json',
            'config.json',
            'acnr_logo.png',
            'icons',
            os.path.join('icons', 'app_icon.png'),
            os.path.join('icons', 'app_icon.ico'),
            os.path.join('icons', 'pencil_dark.png'),
        ]
        log.info('Expected resources:')
        for name in expected:
            full = os.path.join(d, name)
            mark = 'OK ' if os.path.exists(full) else 'MISSING'
            log.info(f'  [{mark}] {full}')

        try:
            entries = sorted(os.listdir(d))
            log.info(f'Listing of app_dir() ({len(entries)} entries):')
            for e in entries[:50]:
                log.info(f'  - {e}')
        except OSError as e:
            log.warning(f'Could not list app_dir(): {e}')
    except Exception as e:
        log.exception(f'Startup diagnostics failed: {e}')

    log.info('=' * 70)


_log_path = _setup_logging()
_dump_startup_diagnostics(_log_path)


from WritingToolApp import WritingToolApp


def main():
    """
    The main entry point of the application.
    """
    app = WritingToolApp(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
