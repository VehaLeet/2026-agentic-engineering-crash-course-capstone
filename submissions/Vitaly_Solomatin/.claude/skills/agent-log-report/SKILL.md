---
name: agent-log-report
description: Summarize the agent observability log (.agent-log/actions.jsonl) into a Markdown table of tool calls, touched files, failures and blocked actions. Use when the user asks what the agent did, wants a session report or an audit of agent actions, or mentions the agent log / actions.jsonl.
license: MIT
compatibility: Requires Node.js 20+. Reads .agent-log/actions.jsonl at the project root (written by the hooks in .claude/settings.json).
metadata:
  author: fwdays-agentic-engineering-crash-course
  version: "1.0"
---

# Agent log report

Produce a human-readable report of everything the agent did in this repo, from `.agent-log/actions.jsonl`
(one JSON object per line, written by the PostToolUse / PostToolUseFailure hooks).

## Workflow

1. Run the bundled script from the project root — never parse the JSONL by hand:
   ```bash
   node .agents/skills/agent-log-report/scripts/report.mjs --format table
   ```
   Options: `--since <ISO date>` limits the window, `--format json` gives machine output, `--help` prints usage.
2. Paste the script output verbatim under a `## Agent activity report` heading.
3. Below the table add at most 5 bullets: risky actions (writes outside `app/`, `lib/`, `docs/`; shell commands with `rm`, `curl`, `sudo`, `git push`), and every line with a non-zero `exit`.
4. Do NOT modify the log file. Do NOT run any other command unless the user asks.

## Gotchas

- If the file is missing or empty, say so and suggest checking the hooks in `.claude/settings.json` (`pnpm hooks:selftest`); do not create the log.
- Lines that are not valid JSON are counted as `invalid` and never crash the report.
- The `tool` column is whatever the hook wrote: `Read`, `Edit`, `Write`, `Bash`, `Glob`, `Grep`, MCP tools such as `mcp__context7__query-docs`.
