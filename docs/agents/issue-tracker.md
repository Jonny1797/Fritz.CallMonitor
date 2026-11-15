# Issue tracker: Forgejo

Issues and specs for this repo live as issues in the self-hosted Forgejo instance at
`https://mash.gaja-uranos.de/forgejo/projects/Fritz.CallMonitor` (the `origin` git remote). Use the
`forgejo` MCP tools (`mcp__forgejo__*`) for all operations, always with `owner: "projects"`,
`repo: "Fritz.CallMonitor"`.

The `github` remote (`Jonny1797/Fritz.CallMonitor`) is a secondary remote. **Never** file or triage
issues there, and never file into `mattpocock/skills`.

## Conventions

- **Labels are referenced by ID, not name.** The MCP tools (`create_issue`, `add_issue_labels`,
  `edit_issue`, `remove_issue_label`) take numeric label IDs. Resolve names → IDs with `list_labels`
  once per session before applying any label.
- **Create an issue**: `create_issue` with `title`, `body` (markdown), and optional `labels` (IDs).
- **Read an issue**: `get_issue` (`index` = issue number), then `list_issue_comments` for the
  discussion.
- **List issues**: `list_issues` with `state` (`open`/`closed`/`all`), `labels` (comma-separated
  label *names* — this filter takes names), `q` for text search, and `type: "issues"` to exclude PRs.
- **Comment on an issue**: `create_issue_comment`.
- **Apply / remove labels**: `add_issue_labels` / `remove_issue_label` (IDs, see above).
- **Close**: post the explanation with `create_issue_comment` first, then `edit_issue` with
  `state: "closed"`.
- **Parent / child issues**: Forgejo has no native sub-issues. Put `Part of #<parent>` at the top of
  the child body, and keep a markdown task list (`- [ ] #<child>`) in the parent body.
- **Blocking**: Forgejo's **native issue dependencies** (enabled on this repo) are the canonical,
  UI-visible representation. `add_issue_dependency` with `index` = the blocked issue and
  `target_owner`/`target_repo`/`target_index` = the blocker. `list_issue_dependencies` lists an
  issue's blockers. A ticket is unblocked when every blocker is closed.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature
requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues: read with
`get_pull_request` + `get_pr_diff`, list with `list_pull_requests`, and comment/label/close with the
issue tools (Forgejo shares one number space across issues and PRs, so a bare `#42` may be either;
check with `get_pull_request` and fall back to `get_issue`).

## When a skill says "publish to the issue tracker"

Create a Forgejo issue with `create_issue`.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body.
  Create the `wayfinder:*` labels with `create_label` on first use if they don't exist.
- **Child ticket**: an issue with `Part of #<map>` at the top of its body, listed in the map's task
  list, labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the
  ticket is assigned to the driving dev.
- **Blocking**: see **Blocking** under Conventions.
- **Frontier query**: list the map's open children (`list_issues`, scoped to the map's task list),
  drop any with an open blocker (`list_issue_dependencies`) or an assignee; first in map order wins.
- **Claim**: `edit_issue` with `assignees: [<login from get_authenticated_user>]`, the session's
  first write.
- **Resolve**: `create_issue_comment` with the answer, then `edit_issue` `state: "closed"`, then
  append a context pointer (gist + link) to the map's Decisions-so-far.
