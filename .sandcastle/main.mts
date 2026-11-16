import {
  run,
  claudeCode,
  Output,
  StructuredOutputError,
  type AgentStreamEvent,
} from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { z } from "zod";

// Ralph loop: work through feasible `ready-for-agent` Forgejo issues, one per
// iteration, all on one fresh branch, then push it and open a single PR.
//
// Usage: npx tsx .sandcastle/main.mts [max-iterations]   (default: 100)
//        RALPH_MODEL=claude-opus-5-5 npx tsx .sandcastle/main.mts
//        REVIEW_MODEL=... overrides the review pass model (default: Opus).
//
// The agent runs in Docker and only reads Forgejo (FORGEJO_READ_TOKEN from
// .sandcastle/.env). Pushing and PR creation happen here, on the host.

const MAX_ITERATIONS = Number(process.argv[2] ?? 100);
const MODEL = process.env.RALPH_MODEL ?? "claude-sonnet-5-5";
// The review is the last check before the PR, so it gets Opus even when the
// loop runs on a cheaper model.
const REVIEW_MODEL = process.env.REVIEW_MODEL ?? "claude-opus-5-5";
const REMOTE = "origin";
const BASE = "master";
const OWNER = "projects";
const REPO = "Fritz.CallMonitor";

const git = (...args: string[]) =>
  execFileSync("git", args, { encoding: "utf8" }).trim();

const stamp = new Date()
  .toISOString()
  .replace(/[-:]/g, "")
  .replace("T", "-")
  .slice(0, 15);
const branch = `ralph/${stamp}`;
// Host directory mounted into the sandbox: the progress log lives outside the
// worktree so it survives every iteration and never ends up in a commit.
const progressDir = resolve(".sandcastle/runs", stamp);
const progressFile = join(progressDir, "progress.md");

// --- Forgejo credentials ---------------------------------------------------
// Looked up before the run starts, so a missing one stops it now and not only
// after hours of iterations, when the PR is due.
//
// Host credentials with write:repository scope, first match wins: the
// environment, then .sandcastle/host.env (never passed into the sandbox),
// then the forgejo MCP entry in ~/.claude.json (this project's entry first,
// then the global one).
const fromFile = (path: string, key: string) => {
  if (!existsSync(path)) return undefined;
  const line = readFileSync(path, "utf8")
    .split("\n")
    .findLast((l) => l.startsWith(`${key}=`));
  return line?.slice(key.length + 1).trim() || undefined;
};
const fromMcp = (key: string): string | undefined => {
  try {
    const config = JSON.parse(
      readFileSync(join(homedir(), ".claude.json"), "utf8"),
    );
    const project = config.projects?.[git("rev-parse", "--show-toplevel")];
    return (
      project?.mcpServers?.forgejo?.env?.[key] ??
      config.mcpServers?.forgejo?.env?.[key]
    );
  } catch {
    return undefined;
  }
};
const credential = (key: string) =>
  process.env[key] ?? fromFile(".sandcastle/host.env", key) ?? fromMcp(key);
// The URL is no secret, so the sandbox's .env may supply it too; the token
// there is read-only and never used for writing.
const forgejoUrl = (
  credential("FORGEJO_URL") ?? fromFile(".sandcastle/.env", "FORGEJO_URL")
)?.replace(/\/$/, "");
const token = credential("FORGEJO_TOKEN");
if (!forgejoUrl || !token) {
  const missing = [!forgejoUrl && "FORGEJO_URL", !token && "FORGEJO_TOKEN"]
    .filter(Boolean)
    .join(" and ");
  console.error(`No ${missing} found (env, .sandcastle/host.env, ~/.claude.json).`);
  process.exit(1);
}

// --- Fresh branch from the remote base ---------------------------------------
git("fetch", REMOTE, BASE);
// The run branches from REMOTE/BASE; unpushed local commits would be missing
// from the branch (and from the PR's base), so refuse to start.
const ahead = git("log", "--oneline", `${REMOTE}/${BASE}..${BASE}`);
if (ahead) {
  console.error(`Local ${BASE} is ahead of ${REMOTE}/${BASE}:\n${ahead}`);
  console.error(`Push them first (git push ${REMOTE} ${BASE}), then rerun.`);
  process.exit(1);
}
const baseSha = git("rev-parse", `${REMOTE}/${BASE}`);
// Sandcastle checks out an existing branch as is, so this pins the base.
git("branch", branch, baseSha);
mkdirSync(progressDir, { recursive: true });

// --- Terminal echo -----------------------------------------------------------
// The log file keeps everything. The terminal shows only what a human follows:
// the agent's `<status>` milestones (asked for in the prompts), one counter
// line for the tool calls between them, and the tail of each feedback-loop run.
const CHECK_TAIL_LINES = 6;
// Only where a command starts, so prose in a heredoc or commit message is no match.
const CHECK_COMMAND = /(^\s*|[;&|(]\s*)uv run (pytest|ruff)(\s|$)/m;
const STATUS = /<status>([\s\S]*?)<\/status>/;
const checkCalls = new Set<string>();
const toolCounts = new Map<string, number>();
let textBuffer = "";
let shownIteration = 0;
const echo = (event: AgentStreamEvent) => {
  if (event.iteration !== shownIteration) {
    flushTools();
    shownIteration = event.iteration;
    console.log(`\n── Iteration ${event.iteration}/${MAX_ITERATIONS} ──`);
  }
  echoOutput(event);
};
const echoOutput = (event: AgentStreamEvent) => {
  const time = event.timestamp.toTimeString().slice(0, 5);
  if (event.type === "toolCall") {
    toolCounts.set(event.name, (toolCounts.get(event.name) ?? 0) + 1);
  } else if (event.type === "text") {
    echoStatus(time, event.message);
  } else if (event.type === "raw") {
    echoCheckTail(event.line);
  }
};
// Text may arrive in chunks, so buffer until a `<status>` tag is complete.
const echoStatus = (time: string, chunk: string) => {
  textBuffer += chunk;
  let match;
  while ((match = STATUS.exec(textBuffer))) {
    flushTools();
    console.log(`  ${time} ▸ ${match[1].trim()}`);
    textBuffer = textBuffer.slice(match.index + match[0].length);
  }
  // Keep only an unclosed tag; plain prose is in the log file.
  const open = textBuffer.lastIndexOf("<status>");
  textBuffer = open === -1 ? "" : textBuffer.slice(open);
};
// `· 12 tools (Read×5, Bash×4, Edit×3)`, most used first.
const flushTools = () => {
  if (toolCounts.size === 0) return;
  const counts = [...toolCounts].sort((a, b) => b[1] - a[1]);
  const total = counts.reduce((sum, [, n]) => sum + n, 0);
  const names = counts.map(([name, n]) => `${name}×${n}`).join(", ");
  console.log(`        · ${total} tool${total === 1 ? "" : "s"} (${names})`);
  toolCounts.clear();
};
// Sandcastle's typed events carry no tool results, so read them from the raw
// stream-json lines, pairing each result with its call by tool id.
const echoCheckTail = (line: string) => {
  if (!line.startsWith("{")) return;
  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch {
    return;
  }
  const blocks = parsed.message?.content;
  if (!Array.isArray(blocks)) return;
  for (const block of blocks) {
    if (
      block.type === "tool_use" &&
      block.name === "Bash" &&
      CHECK_COMMAND.test(block.input?.command ?? "")
    ) {
      checkCalls.add(block.id);
    } else if (
      block.type === "tool_result" &&
      checkCalls.delete(block.tool_use_id)
    ) {
      flushTools();
      const output =
        typeof block.content === "string"
          ? block.content
          : (block.content ?? [])
              .map((part: { text?: string }) => part.text ?? "")
              .join("\n");
      for (const tail of output.trim().split("\n").slice(-CHECK_TAIL_LINES)) {
        console.log(`    ${tail}`);
      }
    }
  }
};

// --- The loop ----------------------------------------------------------------
const result = await run({
  name: "ralph",
  logging: {
    type: "file",
    path: resolve(".sandcastle/logs", `ralph-${stamp}.log`),
    onAgentStreamEvent: echo,
  },
  sandbox: docker({
    mounts: [{ hostPath: progressDir, sandboxPath: "/home/agent/progress" }],
  }),
  agent: claudeCode(MODEL),
  promptFile: "./.sandcastle/prompt.md",
  promptArgs: { BASE_SHA: baseSha },
  maxIterations: MAX_ITERATIONS,
  branchStrategy: { type: "branch", branch },
  hooks: {
    sandbox: {
      // Build the venv once up front instead of in the first iteration.
      onSandboxReady: [
        { command: "uv sync --frozen" },
      ],
    },
  },
});

flushTools();

// --- Push and open one PR ----------------------------------------------------
const commits = Number(git("rev-list", "--count", `${baseSha}..${branch}`));
if (commits === 0) {
  console.log(`Nothing committed; deleting branch ${branch}`);
  git("branch", "-D", branch);
  process.exit(0);
}

// --- Review pass -------------------------------------------------------------
// One fresh-context agent reviews the whole run on the same branch. It checks
// the ticked acceptance boxes, may commit fixes, corrects ticks in the
// progress log, and returns a typed summary that becomes the PR's REVIEW
// section.
const ReviewSchema = z.object({
  verdict: z.enum(["ship", "needs-human"]),
  ticks: z.object({
    checked: z.number().int(),
    held: z.number().int(),
    corrected: z.number().int(),
  }),
  fixed: z.array(
    z.object({ sha: z.string(), issue: z.number().int(), summary: z.string() }),
  ),
  findings: z.array(z.string()),
});
type Review = z.infer<typeof ReviewSchema>;

console.log("\n── Review ──");
let review: Review | undefined;
try {
  const reviewResult = await run({
    name: "ralph-review",
    logging: {
      type: "file",
      path: resolve(".sandcastle/logs", `review-${stamp}.log`),
      onAgentStreamEvent: echoOutput,
    },
    sandbox: docker({
      mounts: [{ hostPath: progressDir, sandboxPath: "/home/agent/progress" }],
    }),
    agent: claudeCode(REVIEW_MODEL),
    promptFile: "./.sandcastle/review.md",
    promptArgs: { BASE_SHA: baseSha },
    maxIterations: 1,
    branchStrategy: { type: "branch", branch },
    hooks: {
      sandbox: {
        onSandboxReady: [
          { command: "uv sync --frozen" },
        ],
      },
    },
    // Retries resume the same session with the validation error fed back.
    output: Output.object({ tag: "review", schema: ReviewSchema, maxRetries: 2 }),
  });
  review = reviewResult.output;
} catch (error) {
  // The loop's commits are worth a PR even when the review summary is broken;
  // the PR then says so instead of claiming a review.
  if (!(error instanceof StructuredOutputError)) throw error;
  console.error(`Review gave no valid <review> summary: ${error.message}`);
}
flushTools();

const reviewSection = (r: Review | undefined) => {
  if (!r) {
    return (
      "## REVIEW\n\n⚠️ The review pass returned no valid summary; " +
      `see \`.sandcastle/logs/review-${stamp}.log\`. Review this PR fully by hand.`
    );
  }
  const list = (items: string[]) =>
    items.length ? items.map((i) => `  - ${i}`).join("\n") : "  - none";
  return [
    "## REVIEW",
    "",
    `**Verdict:** ${r.verdict === "ship" ? "✅ ship" : "⚠️ needs human"}`,
    "",
    `- Ticks checked: ${r.ticks.checked}, held: ${r.ticks.held}, corrected: ${r.ticks.corrected}`,
    "- Fixed:",
    list(r.fixed.map((f) => `${f.sha} (#${f.issue}): ${f.summary}`)),
    "- For the human reviewer:",
    list(r.findings),
  ].join("\n");
};
console.log(`\n${reviewSection(review)}\n`);

const progress = existsSync(progressFile)
  ? readFileSync(progressFile, "utf8")
  : "";
// Issues solved: `Refs #n` commit footers, plus `## DONE #n` progress entries in
// case a commit lacks its footer.
const messages = git("log", "--format=%B", `${baseSha}..${branch}`);
const issues = [
  ...messages.matchAll(/^(?:refs|closes|fixes):? #(\d+)/gim),
  ...progress.matchAll(/^## DONE #(\d+)/gm),
]
  .map((m) => Number(m[1]))
  .filter((n, i, all) => all.indexOf(n) === i)
  .sort((a, b) => a - b);

// The run had to start under a timestamp name because nobody knew which issues
// it would solve; now that we do, rename before the branch ever leaves the host.
const taken = (name: string) =>
  git("branch", "--list", name) !== "" ||
  git("ls-remote", "--heads", REMOTE, name) !== "";
let head = branch;
if (issues.length) {
  const name = `ralph/issue-${issues.join("-")}`;
  const dated = `${name}-${stamp.slice(0, 8)}`;
  head = [name, dated].find((n) => !taken(n)) ?? branch;
  if (head !== branch) git("branch", "-m", branch, head);
}

git("push", "-u", REMOTE, head);

const closes = issues.length
  ? issues.map((n) => `Closes #${n}`).join("\n")
  : "⚠️ No solved issue found in commits or progress log; link the issues by hand.";
// Forgejo treats a `WIP:` title as a draft PR, so it cannot be merged by accident.
const draft = review?.verdict === "ship" ? "" : "WIP: ";
const title =
  draft +
  (issues.length
    ? `Ralph: ${issues.map((n) => `#${n}`).join(" ")}`
    : `Ralph run ${stamp}`);
const body =
  `Autonomous Ralph run \`${stamp}\` (${git("rev-list", "--count", `${baseSha}..${head}`)} commits incl. review, ` +
  `${result.iterations.length} iterations).\n\n${closes}\n\n` +
  `## Progress log\n\n${progress}\n\n` +
  `${reviewSection(review)}\n\n` +
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)\n`;

const response = await fetch(
  `${forgejoUrl}/api/v1/repos/${OWNER}/${REPO}/pulls`,
  {
    method: "POST",
    headers: {
      Authorization: `token ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title, body, head, base: BASE }),
  },
).catch((error: Error) => error);

if (!(response instanceof Error) && response.status === 201) {
  console.log(`PR opened: ${(await response.json()).html_url}`);
} else {
  // Fallback: the branch is pushed, so leave everything needed to open the PR by hand.
  const reason =
    response instanceof Error
      ? response.message
      : `HTTP ${response.status}: ${await response.text()}`;
  const prFile = join(progressDir, "pr.md");
  writeFileSync(prFile, `${title}\n\n${body}`);
  console.error(`Could not open PR (${reason})`);
  console.error(
    `Open it by hand: ${forgejoUrl}/${OWNER}/${REPO}/compare/${BASE}...${head}`,
  );
  console.error(`Title (first line) and body: ${prFile}`);
  console.error(
    "Do this before the next run, or it will redo the same issues.",
  );
}
