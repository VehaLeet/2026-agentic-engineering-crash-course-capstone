#!/usr/bin/env node
// Claude Code PreToolUse hook (matcher: "Bash|Read").
// Keeps the raw agent log OUT of the context window: same question, same tool, summary instead of the JSONL.
//   Bash branch: a raw dump of .agent-log/actions.jsonl (cat/head/tail/less/grep/type ...)
//                -> command rewritten to `node scripts/agent-log-summary.mjs`
//   Read branch: file_path .agent-log/actions.jsonl -> .agent-log/summary.txt (rebuilt when stale)
// The rewrite is returned as hookSpecificOutput.updatedInput — "Replacement tool input object", i.e. the SAME
// tool runs with a different input. A hook cannot turn a Read into a Bash call, which is exactly why the
// matcher has to cover both tools: the agent's choice of tool is not deterministic.
// Never blocks and never fails: any error -> exit 0 and silence, a broken filter must not stop the agent.
import { existsSync, statSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

let raw = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) raw += chunk;

let ev = {};
try {
  ev = JSON.parse(raw || "{}");
} catch {
  process.exit(0);
}

// updatedInput існує лише в PreToolUse; на будь-якій іншій події нам нічого сказати.
if (ev.hook_event_name && ev.hook_event_name !== "PreToolUse") process.exit(0);

const root = process.env.CLAUDE_PROJECT_DIR || ev.cwd || process.cwd();
const ti = ev.tool_input ?? {};

// Та сама нормалізація, що в log-action.mjs, щоб обидва hooks судили про шляхи в одній формі.
const norm = (p) =>
  String(p)
    .replace(/\\/g, "/")
    .replace(/^\/([a-zA-Z])\//, (_, d) => `${d.toUpperCase()}:/`)
    .replace(/^([a-zA-Z]):\//, (_, d) => `${d.toUpperCase()}:/`)
    .replace(/\/$/, "");

const LOG = ".agent-log/actions.jsonl";
const SUMMARY_CMD = "node scripts/agent-log-summary.mjs";
// Команди, що вивалюють файл у вікно. grep тут теж: він фільтрує, але легко віддає тисячі рядків.
// wc свідомо НЕ тут — він повертає одне число і вікна не наповнює, а на кроці 5 саме ним питають
// про кількість рядків у журналі; переписати його означало б зламати той крок.
// що лишити, все одно ухвалює агент — сенс кроку в тому, щоб це рішення сталося ДО вікна, а не в ньому.
const DUMPERS = new Set(["cat", "head", "tail", "less", "more", "nl", "grep", "egrep", "fgrep", "rg", "type"]);

// systemMessage робить підміну видимою в транскрипті: на сцені має бути видно, що спрацював hook, а не збіг.
const emit = (input, message) => {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: { hookEventName: "PreToolUse", updatedInput: input },
      systemMessage: message,
    }),
  );
  process.exit(0);
};

// Перебудовуємо зведення, лише якщо воно старіше за журнал: несвіжі числа на екрані гірші за повільний hook.
// Best effort — якщо не вийшло, все одно перенаправляємо: помилка Read видима, а 1,4 МБ JSONL у вікні — ні.
const refresh = (target, source) => {
  try {
    if (existsSync(target) && existsSync(source) && statSync(target).mtimeMs >= statSync(source).mtimeMs) return;
    const script = join(root, "scripts", "agent-log-summary.mjs");
    if (!existsSync(script)) return;
    const r = spawnSync(process.execPath, [script], { cwd: root, encoding: "utf8", timeout: 5000 });
    if (r.status === 0 && r.stdout) writeFileSync(target, r.stdout);
  } catch {
    /* зведення — зручність, а не передумова */
  }
};

try {
  if (ev.tool_name === "Bash" && typeof ti.command === "string" && norm(ti.command).includes(LOG)) {
    // Дивимось на ПЕРШЕ слово кожного сегмента конвеєра, а не на рядок цілком: `cat … | grep …` — теж дамп,
    // а `node scripts/agent-log-summary.mjs .agent-log/actions.jsonl` згадує журнал і має лишитись недоторканим.
    const isDump = ti.command.split(/\|\||&&|[|;\n]/).some((segment) => {
      const first = segment.trim().split(/\s+/)[0] ?? "";
      const bin = (first.replace(/\\/g, "/").split("/").pop() ?? "").toLowerCase();
      return DUMPERS.has(bin);
    });
    if (isDump) {
      emit(
        { ...ti, command: SUMMARY_CMD },
        `Rewritten by hook (log-filter): the raw ${LOG} never enters the context window — running "${SUMMARY_CMD}" instead.`,
      );
    }
  }

  if (ev.tool_name === "Read" && typeof ti.file_path === "string" && norm(ti.file_path).endsWith(LOG)) {
    const summary = join(root, ".agent-log", "summary.txt");
    refresh(summary, join(root, ".agent-log", "actions.jsonl"));
    emit(
      { ...ti, file_path: summary },
      `Rewritten by hook (log-filter): Read redirected from ${LOG} to .agent-log/summary.txt — the summary enters the context window, not the log.`,
    );
  }
} catch {
  /* фільтр ніколи не ламає виклик інструмента */
}
process.exit(0);
