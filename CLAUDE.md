# CLAUDE.md

PySide6 desktop app that syncs an AVM Fritz!Box's call list (TR-064) into local SQLite and shows a searchable call list plus per-contact history.

- Package manager: **uv** (`uv run …`; never pip).
- Language: in-app strings and code comments are **German**; `CHANGELOG.md` entries are **English**.
- Every notable feature/fix gets a `CHANGELOG.md` entry under `[Unreleased]` — see [docs/agents/changelog.md](docs/agents/changelog.md).

## Commands

```bash
uv run fritz-callhistory   # start the GUI
uv run pytest              # tests (GUI tests run headless automatically)
uv run ruff check .        # lint, line-length 100
```

## Read when relevant

- [Architecture & layering](docs/agents/architecture.md) — before adding modules or cross-layer imports
- [Database & migrations](docs/agents/database.md) — before touching schema, migrations, or call-type logic
- [Threading](docs/agents/threading.md) — before touching `QThread` workers, SQLite connections, or sockets
- [Fritz!Box integration](docs/agents/fritzbox.md) — TR-064 client, call monitor, box-side prerequisites, live CLI test
- [Packaging](docs/agents/packaging.md) — PyInstaller build
- [Issue tracker](docs/agents/issue-tracker.md) · [Triage labels](docs/agents/triage-labels.md) · [Domain docs](docs/agents/domain.md)
