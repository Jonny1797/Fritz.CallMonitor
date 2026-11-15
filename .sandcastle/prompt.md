# Context

## Open `ready-for-agent` issues

!`curl -fsS -H "Authorization: token $FORGEJO_READ_TOKEN" "${FORGEJO_URL%/}/api/v1/repos/projects/Fritz.CallMonitor/issues?state=open&type=issues&labels=ready-for-agent&limit=50" | jq '[.[] | {number, title, body, labels: [.labels[].name], assignees: [(.assignees // [])[].login]}]'`

This list is the sole source of truth for what work exists. Do not run your
own unfiltered query to find more issues — if the list is empty, there is
nothing to do.

## Open pull requests

!`curl -fsS -H "Authorization: token $FORGEJO_READ_TOKEN" "${FORGEJO_URL%/}/api/v1/repos/projects/Fritz.CallMonitor/pulls?state=open&limit=50" | jq '[.[] | {number, title, body, head: .head.ref}]'`

## Commits already made in this run

!`git log --oneline {{BASE_SHA}}..HEAD`

## Progress log of this run

!`cat /home/agent/progress/progress.md 2>/dev/null || echo "(empty — first iteration)"`

# Task

You are one iteration of an autonomous loop ("Ralph"). Each iteration starts
with a fresh context. Your memory between iterations is the progress log
`/home/agent/progress/progress.md` plus `git log`.

Do **exactly one** issue this iteration, then stop.

## Status updates

A human follows this run in a terminal that shows only your `<status>` lines.
At each milestone, output one line in a text message (not inside a tool call):
`<status>…</status>`, at most ~100 characters, saying what you found or
decided, not which tool you used. Milestones:

- issue picked: `<status>Picked #41: show voicemail duration (#38, #40 blocked)</status>`
- cause or approach clear: `<status>Cause: call type mapped before the dedupe, not after</status>`
- failing test written, then green: `<status>Test red: test_range_folder_keeps_labels</status>`
- committed, or blocked and reverted, with the reason
- no feasible issue: one status line per skipped issue, with the reason

## 1. Orient

Read `CLAUDE.md`, `GLOSSARY.md` and the `docs/agents/` topic files it links to.

## 2. Pick the next feasible issue

Forgejo is reachable read-only with these commands (`<n>` is the issue number):

```bash
API="${FORGEJO_URL%/}/api/v1/repos/projects/Fritz.CallMonitor"
AUTH="Authorization: token $FORGEJO_READ_TOKEN"
curl -fsS -H "$AUTH" "$API/issues/<n>"               # view an issue
curl -fsS -H "$AUTH" "$API/issues/<n>/comments"      # its comments
curl -fsS -H "$AUTH" "$API/issues/<n>/dependencies"  # issues blocking it
```

An issue is **feasible** when all of these hold:

- it is in the list above (open, labelled `ready-for-agent`);
- it has no assignee;
- it is not already done in this run (not listed in the progress log);
- no open pull request above already references it;
- every blocker (from the dependencies endpoint, or a `Blocked by: #n` line in
  the body) is either closed or already done in this run;
- it is a concrete implementation ticket, not a parent spec whose work is
  split into child issues (a body with a task list of `#n` children). A parent
  spec counts as done when all its children are.

Among the feasible issues, take the one with the lowest number.

If **no** issue is feasible, do not touch the progress log: it becomes the
pull-request body, and a note that nothing is left to do only misleads its
reviewers. Instead, say in your final message why each remaining
`ready-for-agent` issue was skipped, then output exactly
`<promise>COMPLETE</promise>` and stop.

## 3. Implement

- Read the issue body and all comments. The issue is the spec; follow it,
  together with the parent spec if it has one (`Part of #n`).
- Work test-first: write a failing test in `tests/`, make it pass, refactor.
- Test behavior through public interfaces (the CLI or a module's public
  functions), not internals: don't mock internal collaborators or call
  private helpers. A good test survives a refactor that keeps behavior.
- No tautological tests: take expected values from an independent source
  (a literal, a worked example, the issue), never recompute them the way
  the code does. A test that passes by construction proves nothing.
- Keep the change scoped to this one issue. If you find other problems, note
  them in the progress log instead of fixing them.
- Update `CLAUDE.md` / `GLOSSARY.md` / `CHANGELOG.md` (`## [Unreleased]`, entries in English)
  when the change affects them.

## 4. Feedback loops (all must pass before committing)

```bash
uv run pytest
uv run ruff check .   # line-length 100; `uv run ruff check --fix .` for autofixes
```

Never commit with failing tests. If you cannot get them green, do **not**
commit; revert your changes with `git checkout -- . && git clean -fd`, record
what blocked you in the progress log (prefix the line with `BLOCKED #<n>:`),
and stop. A later iteration will skip that issue.

## 5. Commit

- One commit per issue, Conventional Commits format
  (`feat(scope): summary`, `fix(scope): summary`, …).
- The commit message body must end with the footer line `Refs #<n>`.
- Do **not** push, and do not write to Forgejo. The host pushes the branch and
  opens the pull request after the loop.

## 6. Record progress

Append to `/home/agent/progress/progress.md`:

```markdown
## DONE #<n> — <issue title>

- What changed (2–4 bullets)
- Decisions or surprises the next iteration should know about

### Acceptance criteria

- [x] <criterion, copied verbatim from the issue> — <test or check proving it>
- [ ] <criterion not met> — <why not>
```

Copy every checkbox from the issue's acceptance criteria verbatim (omit the
section if the issue has none). Tick a box only when a test or check you ran
proves it; leave it unticked with the reason otherwise. This log becomes the
pull-request body, where the reviewer checks your claims.

Write only about this issue. Do not mention issues you skipped.

Then stop. Do not start a second issue.
