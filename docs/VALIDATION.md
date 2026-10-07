# Release validation — 2026-10-07

- Python unit tests: **438 passed, 3 skipped** (441 total).
- All distributed Python and JavaScript source files passed syntax checks.
- Source export checked for original owner paths, account identifiers, private endpoints and credential patterns.
- Fresh local UI and authenticated state endpoints checked in a separate data directory.
- Only documented pip requirements installed into a new Python 3.12 environment for startup verification.

No live exchange orders were placed. External providers and optional hardware were not end-to-end certified.

Tests use synthetic portfolios and isolated files. They do not measure future profitability,
general biometric accuracy, long-duration uptime or all third-party service combinations.
Optional integrations require the new user's own configuration. Run the unit suite with
`python -m unittest discover -s tests -q` from this repository.

Device tests include actual loopback TLS transport and signed requests. See DEVICES.md.

The public agent runtime readability update preserves the executable Python AST (excluding
annotations, docstrings and split imports). Five new regression tests verify gate denial,
unknown-tool blocking and API/MCP approval preparation without executing external tools.
