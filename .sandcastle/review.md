# Context

## Commits made in this run

!`git log --format='%h %s%n%b' {{BASE_SHA}}..HEAD`

## Progress log of this run

!`cat /home/agent/progress/progress.md 2>/dev/null || echo "(empty)"`

# Task

You are the reviewer of an autonomous loop ("Ralph"). Earlier iterations each
solved one Forgejo issue, committed it, and recorded what they did in the
progress log. You did not write any of this code. Review it with fresh eyes
before a human reviews the pull request.

The progress log becomes the pull-request body. Your findings go there too.

## Status updates

A human follows this run in a terminal that shows only your `<status>` lines.
At each milestone, output one line in a text message (not inside a tool call):
`<status>…</status>`, at most ~100 characters, saying what you found or
decided, not which tool you used. Milestones: starting a commit's review
(`<status>Reviewing a1b2c3d (#41)</status>`), a tick that does not hold, a fix
committed, a fix reverted.

## 1. Orient

Read `CLAUDE.md`, `GLOSSARY.md` and the `docs/agents/` topic files it links to. The rules
in `CLAUDE.md` are the review checklist that applies to every commit.

## 2. Review commit by commit

For each commit in `git log --reverse {{BASE_SHA}}..HEAD`:

1. Read its diff (`git show <sha>`) and the issue it references (`Refs #<n>`):

   ```bash
   API="${FORGEJO_URL%/}/api/v1/repos/projects/Fritz.CallMonitor"
   AUTH="Authorization: token $FORGEJO_READ_TOKEN"
   curl -fsS -H "$AUTH" "$API/issues/<n>"
   curl -fsS -H "$AUTH" "$API/issues/<n>/comments"
   ```

2. **Verify every ticked acceptance box** in the progress log's
   `## DONE #<n>` section for that issue. The issue's agent brief (in its
   comments) is the source of the criteria; the progress log holds the ticks.
   Check that every criterion from the brief and its addenda appears there.
   A tick holds only if the named test or check exists, exercises that
   criterion, and passes. Open the test and read it; a test name is not
   proof by itself. Run the tests a tick relies on.
3. Check the diff against the `CLAUDE.md` rules and for correctness bugs.
   If an acceptance criterion itself conflicts with a `CLAUDE.md` rule,
   report the conflict; don't silently follow either side.

Then look at the run as a whole: do later commits break assumptions of
earlier ones, or duplicate logic that another commit added?

### Code smells (report only)

Also scan the run's diff for these smells (Fowler, _Refactoring_ ch. 3).
Each is a judgement call, never a hard violation: label it "possible <smell>",
name the file and function, and add it to `findings`. Never fix a smell, and
skip it where `CLAUDE.md`, `docs/agents/` or tooling (ruff) already decides the
matter.

- **Duplicated Code**: the same logic shape in more than one hunk or file,
  often across commits from different iterations.
- **Speculative Generality**: parameters, flags, hooks or abstractions that no
  issue asked for.
- **Shotgun Surgery**: one logical change scattered across many modules.
- **Mysterious Name**: a function, variable or type whose name doesn't say
  what it does or holds, or that contradicts a `GLOSSARY.md` term.

## 3. Act on findings

- Fix clear defects, report everything else.
- Don't edit `docs/`, `CLAUDE.md` or `GLOSSARY.md`; report findings or
  mismatches there instead.
- Fixes that require a code change of more than 30 lines or more than one module are report only.
- One commit per fix, Conventional Commits format
  (`fix(scope): summary`, …). The commit message body must end with the
  footer line `Refs #<n>` of the issue whose commit it fixes.
- Never change behavior the issue specifies; if you disagree with the spec, report it.

Every fix must keep all feedback loops green before committing:

```bash
uv run pytest
uv run ruff check .   # line-length 100; `uv run ruff check --fix .` for autofixes
```

If a fix cannot be made green, revert it (`git checkout -- . && git clean -fd`)
and report the finding instead. Do **not** push, and do not write to Forgejo.

## 4. Correct the ticks

Where a ticked box does not hold, untick it in place in the progress log and
append the reason, e.g.
`- [ ] <criterion> — <original proof> — **review:** test only covers incoming calls, not missed ones`.
If you fixed it, keep the tick and append `— **review:** fixed in <sha>`.

## 5. Report the review

Do not write a review section into the progress log; the host builds it from
your report. As your final message, output a JSON object inside `<review>`
tags, exactly this shape:

<review>
{
  "verdict": "ship",
  "ticks": { "checked": 0, "held": 0, "corrected": 0 },
  "fixed": [{ "sha": "<short sha>", "issue": 0, "summary": "<one line>" }],
  "findings": ["<finding you did not fix, most important first>"]
}
</review>

- `verdict` is `"ship"` only if every tick holds (after your fixes) and no
  finding needs a human decision; otherwise `"needs-human"`. Smell findings
  never need a human decision on their own.
- `fixed` has one entry per fix commit; `findings` one short, self-contained
  sentence each. Use `[]` for an empty list.

Then stop.
