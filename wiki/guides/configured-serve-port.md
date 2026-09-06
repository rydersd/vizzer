# Per-project persistent serve port

Owner request: each Vizzer installation can own a stable loopback URL that is
safe to bookmark, while sibling projects choose different ports.

## Contract

- `[server] port = N` in `vizzer/vizzer.toml` supplies the default port for
  `vizzer serve`.
- `N` is an integer from 0 through 65535. Boolean, string, negative, and
  out-of-range values fail at the configuration boundary.
- Port `0` preserves the portable ephemeral-port default for new installs.
- Explicit `vizzer serve --port N` wins over project configuration, including
  `--port 0` as an intentional one-run ephemeral override.
- The server remains loopback-only. A configured-port collision fails visibly;
  it must not silently move a bookmarked project to another URL.

## Named acceptance

- `test_server_port_configuration_is_validated`
- `test_serve_uses_configured_port_and_cli_override`
- `test_loopback_serve_open_endpoint_accepts_only_known_item_ids`
- `test_install_creates_engine_and_config`

The decisive counterexample is a project configured for one port and invoked
with `--port 0`: configuration-only or CLI-only implementations cannot satisfy
both the stable default and the explicit ephemeral override.
