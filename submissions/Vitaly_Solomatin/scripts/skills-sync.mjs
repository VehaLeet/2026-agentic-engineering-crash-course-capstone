#!/usr/bin/env node
// Copy every skill from the shared .agents/skills/ folder (read by Cursor, Codex, Copilot, Gemini CLI, Amp)
// into .claude/skills/ (the only project folder Claude Code reads). Idempotent; run: pnpm skills:sync
// Why a copy and not a symlink: symlinks on Windows need Developer Mode / admin, copies work everywhere.
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";

const src = join(process.cwd(), ".agents", "skills");
const dst = join(process.cwd(), ".claude", "skills");
if (!existsSync(src)) {
  console.error("No .agents/skills/ folder found.");
  process.exit(2);
}
mkdirSync(dst, { recursive: true });
let n = 0;
for (const name of readdirSync(src)) {
  const from = join(src, name);
  if (!statSync(from).isDirectory() || !existsSync(join(from, "SKILL.md"))) continue;
  const to = join(dst, name);
  rmSync(to, { recursive: true, force: true });
  cpSync(from, to, { recursive: true });
  n++;
  console.log(`synced  ${name}`);
}
console.log(`${n} skill(s) -> .claude/skills/`);
