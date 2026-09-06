# Keep the local dashboard available at a stable address

> Status: shipped
> Deps: []
> Release: R1
> Tags: dogfood, startup

## Intent

Use the same local URL across sessions and start Vizzer automatically at macOS
login, without relying on an agent task to keep a manually launched server alive.

## Acceptance criteria

- Keep the configured loopback port 8480 and dashboard route stable.
- A user LaunchAgent starts this checkout at login and restarts it on exit.
- Refresh source-backed views before serving; avoid a competing vendored engine.
- Replace only this checkout's manual server and leave other projects alone.
- Document logs, restart/disable commands and the local-only/login scope.

## Evidence — 2026-09-05

Installed and enabled `com.vizzer.project.ad84a7edba4f.server`. `plutil -lint`
passed; `launchctl print` reported running with `keepalive` and `runatload`.
One listener on `127.0.0.1:8480` belonged to the LaunchAgent PID, and the dashboard
returned HTTP 200. Actual logout/reboot was not performed. The machine-specific
plist remains in the user's Library; the source launcher is `vizzer/start_server.py`.
