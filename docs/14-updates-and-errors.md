# Self-update and the error log

## Self-update (downloaded app only)
- Built by CI (`build` job): one file per platform, named `Mod-Manager-windows.exe`, `Mod-Manager-macos`, `Mod-Manager-linux`. Pushing a tag `vX.Y.Z` (must equal `modmanager.__version__`) publishes them with `SHA256SUMS.txt`.
- Windows also gets `Mod-Manager-Setup.exe` (Inno Setup, `installer/ModManager.iss`): per-user install to `%LOCALAPPDATA%\\Programs\\Mod Manager`, Start-menu entry, optional desktop shortcut, uninstaller. Per-user so the in-app update can replace the program without administrator rights. CI installs it silently, starts the installed app and uninstalls it. Not code-signed.
- **Update now** (banner, only when `can_self_update` is true, i.e. running the packaged app):
  1. latest release via the GitHub API (same check as before; user-initiated),
  2. download `SHA256SUMS.txt` and this platform's file: https only, `github.com` / `api.github.com` / `*.githubusercontent.com`, 300 MB cap, the optional `MODMANAGER_GITHUB_TOKEN` is never forwarded to the CDN,
  3. refuse unless the file's SHA-256 is listed and equal,
  4. rename the running app to `<name>.old`, move the new file in (undone if that fails), start the new copy (`MODMANAGER_RESTARTED=1`, it waits for the port), exit. `.old` is deleted on the next start.
- The restarted copy opens its own window when the old one was a window (`MODMANAGER_MODE=window` is passed through the environment); a browser tab reloads itself instead.
- A source checkout refuses and says to use `git pull` / the ZIP.
- **What the checksum does and does not give you:** it detects a corrupted or swapped download. It is not a code signature; whoever can publish a release in the repository can publish a matching checksum. Windows SmartScreen / macOS Gatekeeper warnings appear on first run because the builds are unsigned.
- Status: the update logic is unit-tested (checksum mismatch, missing hash, redirects, swap/rollback, restart call) and the Linux build was started and served the page in testing. A full download-and-replace against a real published release has to be done once a second release exists.

## Error log
- File: `ModManager-errors.log` in the real Documents folder (Windows: asked from the shell, so OneDrive-redirected Documents works; else `~/Documents`; else home). Override with `MODMANAGER_LOG_DIR`. ~1 MB cap, one rotated copy `.log.1`.
- Written for: unexpected server errors (the page gets JSON `{error, log_file}` instead of a dropped connection), crashes at start-up, uncaught exceptions in worker threads, and script errors / failed requests reported by the page (`/api/client-error`, max 200 per run, fields truncated).
- Entry = time, source (`server`, `page`, `startup`, `crash`, `thread`, `update`), message, where, traceback/stack, app + Python + OS versions. No mod contents.
- The page shows a red banner with the path for server errors and script errors; ordinary validation messages stay as toasts.

## The app window
`modmanager/window.py`. `python -m modmanager` starts the local server in a thread and shows the page in a window; when the window closes the server stops and the process ends.
1. **pywebview** (Windows: WebView2 via `gui="edgechromium"`, so the old Internet Explorer engine is never used; macOS: WebKit). Not used on Linux. Bundled into the Windows and macOS apps by CI (`--collect-all webview`); CI starts `--probe-window` on the built app and requires the platform layer to load.
2. **Edge / Chrome / Chromium** started with `--app=<url>` and its own profile folder (`<config>/window`). If an instance with that profile is already running it takes over and the call returns at once; then the app keeps serving until Ctrl+C.
3. **The default browser**, also what `--browser` does.
The Windows app is built `--windowed` (no console). A startup failure is shown in a message box and written to the error log.
