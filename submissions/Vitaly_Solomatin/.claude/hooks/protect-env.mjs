#!/usr/bin/env node
// Claude Code PreToolUse hook (matcher: Read|Edit|Write|NotebookEdit).
// Blocks reading or writing secrets files (.env, .env.local, .env.production ...); .env.example stays open.
// Also enforces one project invariant: no `os.environ` / `os.getenv` written into HTTP handlers in
// `backend/app/api/**` — env is read in its own modules (storage/database.py, notify/notifier.py).
// The one exception is the launcher `backend/app/api/__main__.py`: reading API_HOST/API_PORT is its whole job.
// Exit code 2 = the tool call is BLOCKED and stderr is fed back to the agent as the reason.
// PreToolUse hooks run BEFORE the permission check, in EVERY permission mode (even bypassPermissions):
// hooks enforce, AGENTS.md only advises. The permissions.deny rules in settings.json are the second line of defence.
let raw = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) raw += chunk;

let ev = {};
try {
  ev = JSON.parse(raw || "{}");
} catch {
  process.exit(0);
}

const input = ev.tool_input ?? {};
const p = String(input.file_path ?? input.notebook_path ?? "").replace(/\\/g, "/");
const base = p.split("/").pop() ?? "";

if (/^\.env(\..+)?$/.test(base) && base !== ".env.example") {
  const verb = ev.tool_name === "Read" ? "read" : "edit";
  process.stderr.write(
    `Blocked by hook: ${p} is a secrets file; the agent must not ${verb} it. Use .env.example instead and ask the user to update .env manually.\n`,
  );
  process.exit(2);
}

// Дивимось в ОБИДВА поля нового вмісту: Edit кладе його в new_string, Write — у content.
// Одного поля замало: вибір інструмента недетермінований, і з одним полем hook мовчки не спрацює.
const written = `${input.new_string ?? ""}\n${input.content ?? ""}`;
if (
  /(^|\/)backend\/app\/api\//.test(p) &&
  !/(^|\/)backend\/app\/api\/__main__\.py$/.test(p) &&
  /\bos\.(environ|getenv)\b/.test(written)
) {
  process.stderr.write(
    `Blocked by hook: backend/app/api/** — os.environ/os.getenv не в HTTP-обробнику; читайте env у модулі налаштувань (лаунчер __main__.py — виняток)\n`,
  );
  process.exit(2);
}
process.exit(0);
