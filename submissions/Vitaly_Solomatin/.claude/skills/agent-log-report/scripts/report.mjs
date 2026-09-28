#!/usr/bin/env node
// Summarize .agent-log/actions.jsonl -> Markdown (default) or JSON.
// Lines: PreToolUse = proposed · PostToolUse / PostToolUseFailure = executed · a PreToolUse line whose id
// has no executed line = proposed but not executed (blocked by a hook, a permission rule or the human).
// Usage: node scripts/report.mjs [--format table|json] [--since ISO] [--file PATH]
// Exit codes: 0 ok · 2 log not found · 3 bad arguments
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : def;
};
if (args.includes("--help")) {
  console.log(
    [
      "Usage: node scripts/report.mjs [OPTIONS]",
      "",
      "Summarize .agent-log/actions.jsonl (one JSON object per line).",
      "",
      "Options:",
      "  --format FORMAT   table (default) | json",
      "  --since ISO       only entries with ts >= ISO timestamp",
      "  --file PATH       log path (default: .agent-log/actions.jsonl)",
      "",
      "Exit codes: 0 ok, 2 log file not found, 3 bad arguments",
    ].join("\n"),
  );
  process.exit(0);
}
const format = opt("--format", "table");
if (!["table", "json"].includes(format)) {
  console.error(`Error: --format must be table or json (got "${format}")`);
  process.exit(3);
}
const since = opt("--since", null);
const file = resolve(process.cwd(), opt("--file", ".agent-log/actions.jsonl"));
if (!existsSync(file)) {
  console.error(`Error: log not found at ${file}. Are the hooks in .claude/settings.json active?`);
  process.exit(2);
}

const entries = [];
let invalid = 0;
for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
  if (!line.trim()) continue;
  try {
    const e = JSON.parse(line);
    if (since && e.ts && e.ts < since) continue;
    entries.push(e);
  } catch {
    invalid++;
  }
}
const executedIds = new Set(entries.filter((e) => e.event !== "PreToolUse" && e.id).map((e) => e.id));
const byTool = new Map();
const files = new Set();
const blocked = [];
const failures = [];
let first = null;
let last = null;
for (const e of entries) {
  const tool = e.tool ?? "unknown";
  const s = byTool.get(tool) ?? { proposed: 0, executed: 0, blocked: 0, failed: 0 };
  if (e.event === "PreToolUse") {
    s.proposed++;
    if (e.id && !executedIds.has(e.id)) {
      s.blocked++;
      blocked.push({ ts: e.ts, tool, what: e.cmd ?? e.path ?? e.pattern ?? "" });
    }
  } else {
    s.executed++;
    if (e.exit !== 0) {
      s.failed++;
      failures.push({ ts: e.ts, tool, exit: e.exit, what: e.cmd ?? e.path ?? "" });
    }
  }
  byTool.set(tool, s);
  if (e.path) files.add(e.path);
  if (e.ts) {
    first ??= e.ts;
    last = e.ts;
  }
}
const rows = [...byTool.entries()].sort((a, b) => b[1].proposed + b[1].executed - (a[1].proposed + a[1].executed));
const executed = entries.filter((e) => e.event !== "PreToolUse").length;
const summary = { file, executed, proposedOnly: blocked.length, failed: failures.length, invalid, first, last, tools: Object.fromEntries(rows), files: [...files].sort(), blocked, failures };

if (format === "json") {
  console.log(JSON.stringify(summary, null, 2));
  process.exit(0);
}
console.log("| Tool | Proposed | Executed | Blocked | Failed |\n|---|---:|---:|---:|---:|");
for (const [t, s] of rows) console.log(`| ${t} | ${s.proposed} | ${s.executed} | ${s.blocked} | ${s.failed} |`);
console.log(
  `\n**Total:** ${executed} executed, ${blocked.length} proposed but not executed, ${failures.length} failed, ${invalid} invalid lines, ${files.size} distinct files (${first ?? "-"} .. ${last ?? "-"}).`,
);
if (blocked.length) {
  console.log("\n**Proposed but not executed (blocked by a hook, a rule or the human):**\n");
  for (const b of blocked) console.log(`- ${b.ts} · ${b.tool} · \`${b.what}\``);
}
if (failures.length) {
  console.log("\n**Failed:**\n");
  for (const f of failures) console.log(`- ${f.ts} · ${f.tool} · exit ${f.exit} · \`${f.what}\``);
}
if (files.size) console.log(`\n<details><summary>Files touched (${files.size})</summary>\n\n${[...files].sort().map((f) => `- \`${f}\``).join("\n")}\n\n</details>`);
