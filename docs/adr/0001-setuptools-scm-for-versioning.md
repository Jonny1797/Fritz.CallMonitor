# Version from the git tag via setuptools-scm, not from pyproject.toml

The App update compares the running app's version with the latest Release tag, so the version baked into a build must always equal its tag. We therefore derive the version from git tags with setuptools-scm and switched the build backend from `uv_build` (which cannot do dynamic versions) to setuptools; uv stays the package manager. A release is now just a changelog update plus a tag; nobody writes a version into `pyproject.toml`.

## Consequences

- CI must check out full history with tags (`fetch-depth: 0`), otherwise builds get `0.1.dev1`.
- Builds between tags carry PEP 440 dev versions (`1.0.2.dev3+g…`), so version comparison uses `packaging.version.Version`, not tuple parsing.
- The editable install goes stale on new commits/tags unless `[tool.uv] cache-keys` includes git commit and tags.
- Without git metadata the build falls back to `0.0.0`.
