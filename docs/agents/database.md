# Database & migrations

- No ORM: raw `sqlite3` + repositories in `db/repository.py`.
- Migrations are numbered `.sql` files in `db/migrations/`, applied in order via `PRAGMA user_version` (`db/schema.py`). Add a new numbered file; never edit an applied one.
- The PyInstaller spec globs `db/migrations/*.sql`, so new migrations ship automatically as long as they live there — see [packaging.md](packaging.md).

## Call dedupe

Dedupe uses a **`COALESCE`-based unique index** (`idx_calls_dedupe` in `db/migrations/001_init.sql`), not a table-level `UNIQUE(...)`. SQLite treats `NULL` as never equal to `NULL` in `UNIQUE` constraints, and `caller_number` / `called_number` / `duration_seconds` are often `NULL` (e.g. missed calls have no duration). Replacing it with a plain `UNIQUE` silently reintroduces duplicates on repeated syncs.

## Call type codes

From the installed `fritzconnection` lib (not just its docs):

| Code | Meaning |
|---|---|
| 1 | received |
| 2 | missed |
| 3 | outgoing |
| 9 | active received |
| 10 | rejected |
| 11 | active outgoing |

## Anonymous numbers

Missing/suppressed numbers are normalized to the `ANONYMOUS_NUMBER` sentinel (`sync/normalize.py`, region `DE`) so they group into one pseudo-contact instead of creating duplicates.
