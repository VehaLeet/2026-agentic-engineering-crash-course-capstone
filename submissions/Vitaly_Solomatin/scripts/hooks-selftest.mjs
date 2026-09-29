#!/usr/bin/env node
// Self-test for the Claude Code hooks in .claude/hooks/ — no agent needed.
// Pipes realistic hook payloads through the scripts against a TEMP project dir and checks:
//   1. protect-env.mjs blocks Read/Edit/Write of .env, .env.local, .env.production (exit 2) and allows .env.example + normal files
//   1b. protect-env.mjs blocks os.environ/os.getenv written into backend/app/api/** — through Edit (new_string) AND through
//       Write (content) — and still allows the same text outside it, in the launcher __main__.py, and a clean handler inside it
//   2. log-action.mjs appends one JSON line per event (PreToolUse = proposed, Post* = executed) with repo-relative paths
//   3. a PreToolUse line without a Post line for the same id is reported as "proposed but not executed"
//   4. log-filter.mjs rewrites the tool input so the raw .agent-log/actions.jsonl never reaches the context window:
//      a Bash dump becomes `node scripts/agent-log-summary.mjs`, a Read becomes a Read of .agent-log/summary.txt,
//      and everything else is left untouched
//   5. protect-telegram.mjs blocks any agent call to the Telegram Bot API (api.telegram.org, the app endpoints that reach
//      Telegram, `app.notify test`, WebFetch) and still allows searching the code for those strings and mocked tests
// Usage: node scripts/hooks-selftest.mjs
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const here = process.cwd();
const tmp = mkdtempSync(join(tmpdir(), "hooks-selftest-"));
const env = { ...process.env, CLAUDE_PROJECT_DIR: tmp };
const run = (script, payload) =>
  spawnSync(process.execPath, [join(here, ".claude", "hooks", script)], { input: JSON.stringify(payload), env, encoding: "utf8" });

let failed = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
  if (!ok) failed++;
};

const base = { session_id: "selftest-0001", cwd: tmp, permission_mode: "default" };

// 1. guard
for (const [tool, file, expect] of [
  ["Edit", join(tmp, ".env"), 2],
  ["Write", join(tmp, ".env.local"), 2],
  ["Read", tmp + "\\.env.production", 2],
  ["Edit", join(tmp, ".env.example"), 0],
  ["Read", join(tmp, "lib", "env.ts"), 0],
]) {
  const r = run("protect-env.mjs", { ...base, hook_event_name: "PreToolUse", tool_name: tool, tool_input: { file_path: file } });
  check(`protect-env ${tool} ${file.split(/[\\/]/).pop()} -> exit ${expect}`, r.status === expect, r.status === 2 ? r.stderr.trim() : "");
}

// 1b. app/api invariant: те саме тіло подається двома різними інструментами — Edit кладе його в new_string,
// Write у content. Обидва мусять блокуватись, інакше hook мовчки не спрацює, щойно агент вибере інший інструмент.
//
// Інваріант приїжджає лише на кроці 6 (шар 3), тому до нього ці рядки друкуються як SKIP, а не FAIL:
// файл селфтесту один на весь вечір, і рядок сам перемикається на PASS, щойно предикат з'явиться.
const guardSrc = readFileSync(join(here, ".claude", "hooks", "protect-env.mjs"), "utf8");
const hasApiInvariant = guardSrc.includes("backend/app/api/**");
const handlerWithEnv = '@app.get("/region")\nasync def region():\n    return {"region": os.environ["DEPLOY_REGION"]}\n';
const handlerWithGetenv = 'def token():\n    return os.getenv("TELEGRAM_BOT_TOKEN")\n';
const handlerClean = '@app.get("/health")\nasync def health():\n    return {"status": "ok"}\n';
const api = (...parts) => join(tmp, "backend", "app", "api", ...parts);
for (const [tool, file, field, body, note, expect] of hasApiInvariant ? [
  ["Edit", api("app.py"), "new_string", handlerWithEnv, "", 2],
  ["Write", api("routes.py"), "content", handlerWithEnv, "", 2],
  ["Edit", api("app.py"), "new_string", handlerWithGetenv, "(os.getenv)", 2],
  ["Edit", join(tmp, "backend", "app", "notify", "notifier.py"), "new_string", handlerWithGetenv, "(outside api)", 0],
  ["Write", api("__main__.py"), "content", handlerWithEnv, "(launcher)", 0],
  ["Write", api("app.py"), "content", handlerClean, "(no env)", 0],
] : []) {
  const r = run("protect-env.mjs", { ...base, hook_event_name: "PreToolUse", tool_name: tool, tool_input: { file_path: file, [field]: body } });
  const label = `protect-env ${tool} ${file.split(/[\\/]/).pop()}${note ? " " + note : ""} -> exit ${expect}`;
  check(label, r.status === expect, r.status === 2 ? r.stderr.trim().split("\n")[0] : "");
}
if (!hasApiInvariant) {
  console.log("SKIP  protect-env backend/app/api invariant — правило ще не додано");
}

// 2. logger: a proposed+executed Bash, a proposed+executed Edit, a proposed+failed Bash, a proposed-only Edit (blocked)
const events = [
  { ...base, hook_event_name: "PreToolUse", tool_use_id: "t1", tool_name: "Bash", tool_input: { command: "uv run pytest -q" } },
  { ...base, hook_event_name: "PostToolUse", tool_use_id: "t1", tool_name: "Bash", tool_input: { command: "uv run pytest -q" }, tool_response: { stdout: "ok" }, duration_ms: 4200 },
  { ...base, hook_event_name: "PreToolUse", tool_use_id: "t2", tool_name: "Edit", tool_input: { file_path: join(tmp, "app", "page.tsx") } },
  { ...base, hook_event_name: "PostToolUse", tool_use_id: "t2", tool_name: "Edit", tool_input: { file_path: join(tmp, "app", "page.tsx") }, duration_ms: 15 },
  { ...base, hook_event_name: "PreToolUse", tool_use_id: "t3", tool_name: "Bash", tool_input: { command: "npm run typecheck" } },
  { ...base, hook_event_name: "PostToolUseFailure", tool_use_id: "t3", tool_name: "Bash", tool_input: { command: "npm run typecheck" }, error: "Exit code 2\nerror TS2339", duration_ms: 900 },
  { ...base, hook_event_name: "PreToolUse", tool_use_id: "t4", tool_name: "Edit", tool_input: { file_path: join(tmp, ".env") } },
];
for (const e of events) {
  const r = run("log-action.mjs", e);
  check(`log-action ${e.hook_event_name} ${e.tool_name} exits 0 silently`, r.status === 0 && r.stdout === "");
}
const lines = readFileSync(join(tmp, ".agent-log", "actions.jsonl"), "utf8").trim().split("\n").map((l) => JSON.parse(l));
check("log has 7 lines", lines.length === 7);
check("PreToolUse line has no exit field", lines[0].event === "PreToolUse" && !("exit" in lines[0]) && lines[0].id === "t1");
check("PostToolUse Bash keeps cmd and exit 0", lines[1].cmd === "uv run pytest -q" && lines[1].exit === 0 && lines[1].ms === 4200);
check("Edit line stores repo-relative path", lines[3].path === "app/page.tsx", lines[3].path);
check("failure line carries exit code 2", lines[5].exit === 2);

// 3. summary pairs Pre/Post by id
const executedIds = new Set(lines.filter((l) => l.event !== "PreToolUse").map((l) => l.id));
const proposedOnly = lines.filter((l) => l.event === "PreToolUse" && !executedIds.has(l.id));
check("exactly one proposed-but-not-executed action (.env edit)", proposedOnly.length === 1 && proposedOnly[0].path === ".env");
const summary = spawnSync(process.execPath, [join(here, "scripts", "agent-log-summary.mjs"), join(tmp, ".agent-log", "actions.jsonl")], { encoding: "utf8" });
check("agent-log-summary reports 1 proposed but not executed", summary.status === 0 && /1 proposed but not executed/.test(summary.stdout));

// 4. filter: the raw log never reaches the context window
const SUMMARY_CMD = "node scripts/agent-log-summary.mjs";
const logPath = join(tmp, ".agent-log", "actions.jsonl");
const summaryPath = join(tmp, ".agent-log", "summary.txt");
// Hook перебудовує зведення ВЛАСНИМ скриптом проєкту, тож тимчасовому проєкту потрібна його копія.
mkdirSync(join(tmp, "scripts"), { recursive: true });
copyFileSync(join(here, "scripts", "agent-log-summary.mjs"), join(tmp, "scripts", "agent-log-summary.mjs"));

const filter = (payload) => {
  const r = run("log-filter.mjs", { ...base, hook_event_name: "PreToolUse", ...payload });
  let out = {};
  try {
    out = JSON.parse(r.stdout || "{}");
  } catch {
    /* не JSON -> вважаємо, що hook нічого не вирішив */
  }
  return { r, updated: out.hookSpecificOutput?.updatedInput, message: out.systemMessage ?? "" };
};

// Bash: сирий дамп журналу переписуємо, решту не чіпаємо. Кейси "untouched" тут найважливіші — саме вони
// ловлять matcher або предикат, що розрісся зашироко.
for (const [command, expected] of [
  ["cat .agent-log/actions.jsonl", SUMMARY_CMD],

  ["tail -n 500 .agent-log/actions.jsonl | grep PreToolUse", SUMMARY_CMD],
  ["grep gate .agent-log/actions.jsonl", SUMMARY_CMD],
  ["cat ./.agent-log/actions.jsonl", SUMMARY_CMD],
  ["uv run pytest -q", null],
  ["cat package.json", null],
  [SUMMARY_CMD, null],
  ["node scripts/agent-log-summary.mjs .agent-log/actions.jsonl", null],
]) {
  const { r, updated } = filter({ tool_name: "Bash", tool_input: { command, description: "look at the log" } });
  const ok = expected
    ? r.status === 0 && updated?.command === expected && updated?.description === "look at the log"
    : r.status === 0 && r.stdout === "";
  check(`log-filter Bash \`${command}\` -> ${expected ? "summary command" : "untouched"}`, ok, updated?.command ?? "");
}

// Read: перенаправляємо навіть якщо зведення немає — помилка Read видима, а 1,4 МБ у вікні ні.
rmSync(summaryPath, { force: true });
let res = filter({ tool_name: "Read", tool_input: { file_path: logPath, limit: 200 } });
check(
  "log-filter Read actions.jsonl -> summary.txt (summary missing), other input kept",
  res.r.status === 0 && res.updated?.file_path === summaryPath && res.updated?.limit === 200,
  res.updated?.file_path ?? "",
);
check("log-filter rebuilt .agent-log/summary.txt from the log", existsSync(summaryPath) && readFileSync(summaryPath, "utf8").startsWith("Agent actions:"));

// Зведення, свіжіше за журнал, беремо як є...
writeFileSync(summaryPath, "STALE-MARKER\n");
res = filter({ tool_name: "Read", tool_input: { file_path: logPath } });
check(
  "log-filter reuses a summary newer than the log",
  res.updated?.file_path === summaryPath && readFileSync(summaryPath, "utf8").startsWith("STALE-MARKER"),
);
// ...а старіше за журнал — перебудовуємо, щоб зал ніколи не побачив учорашніх чисел.
const past = new Date(Date.now() - 3600000);
utimesSync(summaryPath, past, past);
res = filter({ tool_name: "Read", tool_input: { file_path: logPath } });
check("log-filter rebuilds a summary older than the log", readFileSync(summaryPath, "utf8").startsWith("Agent actions:"));

res = filter({ tool_name: "Read", tool_input: { file_path: tmp + "\\.agent-log\\actions.jsonl" } });
check("log-filter matches a Windows-shaped path too", res.updated?.file_path === summaryPath, res.updated?.file_path ?? "");

for (const p of [join(tmp, "lib", "health.ts"), summaryPath]) {
  const { r, updated } = filter({ tool_name: "Read", tool_input: { file_path: p } });
  check(`log-filter leaves Read ${p.split(/[\\/]/).pop()} alone`, r.status === 0 && r.stdout === "" && !updated);
}

const post = filter({ tool_name: "Read", hook_event_name: "PostToolUse", tool_input: { file_path: logPath } });
check("log-filter ignores events other than PreToolUse", post.r.status === 0 && post.r.stdout === "");
const broken = spawnSync(process.execPath, [join(here, ".claude", "hooks", "log-filter.mjs")], { input: "not json", env, encoding: "utf8" });
check("log-filter survives malformed input (exit 0, silent)", broken.status === 0 && broken.stdout === "");
check(
  "log-filter names itself in systemMessage, so the rewrite is visible",
  /hook \(log-filter\)/.test(filter({ tool_name: "Bash", tool_input: { command: "cat .agent-log/actions.jsonl" } }).message),
);

// 5. protect-telegram: агент не звертається до Bot API — ні напряму, ні через застосунок. Пошук у коді дозволено.
for (const [tool, input, expect, note] of [
  ["Bash", { command: 'curl -s "https://api.telegram.org/bot123:ABC/getUpdates"' }, 2, "curl getUpdates"],
  ["Bash", { command: "python3 -c \"import urllib.request as u; u.urlopen('https://api.telegram.org/bot1/getMe')\"" }, 2, "python one-liner"],
  ["Bash", { command: "curl -s http://127.0.0.1:8080/api/settings/telegram/candidates" }, 2, "app candidates"],
  ["Bash", { command: "curl -s -X POST http://127.0.0.1:8000/settings/telegram/recipients/436586281/test" }, 2, "app test message"],
  ["Bash", { command: "docker compose exec backend python -m app.notify test" }, 2, "CLI notify test"],
  ["Bash", { command: "grep -rn 'api.telegram.org' backend/app" }, 0, "search the code"],
  ["Bash", { command: "grep -rn api.telegram.org backend/app | head" }, 0, "search piped into head"],
  ["Bash", { command: "rg -n settings/telegram/candidates frontend/src" }, 0, "search the code (rg)"],
  ["Bash", { command: "curl -s http://127.0.0.1:8080/api/settings/telegram/recipients" }, 0, "recipients list (no Telegram call)"],
  ["Bash", { command: "cd backend && uv run pytest tests/test_telegram_api.py -q" }, 0, "tests use a mocked Bot API"],
  ["WebFetch", { url: "https://api.telegram.org/bot1/getUpdates", prompt: "x" }, 2, "WebFetch Bot API"],
  ["WebFetch", { url: "https://core.telegram.org/bots/api", prompt: "x" }, 0, "WebFetch Bot API docs"],
]) {
  const r = run("protect-telegram.mjs", { ...base, hook_event_name: "PreToolUse", tool_name: tool, tool_input: input });
  check(`protect-telegram ${tool} ${note} -> exit ${expect}`, r.status === expect, r.status === 2 ? r.stderr.trim().slice(0, 90) : "");
}
const tgBroken = spawnSync(process.execPath, [join(here, ".claude", "hooks", "protect-telegram.mjs")], { input: "not json", env, encoding: "utf8" });
check("protect-telegram survives malformed input (exit 0)", tgBroken.status === 0);

rmSync(tmp, { recursive: true, force: true });
console.log(failed ? `\n${failed} check(s) failed` : "\nall hook checks passed");
process.exit(failed ? 1 : 0);
