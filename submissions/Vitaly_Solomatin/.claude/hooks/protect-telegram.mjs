#!/usr/bin/env node
// Claude Code PreToolUse hook (matcher: Bash|WebFetch).
// The agent must not talk to the Telegram Bot API — directly or through the app — so a runaway loop
// of test messages or getUpdates polls can never get the bot rate-limited or banned. The owner does that
// by hand (UI buttons, `make`), the agent only reads code and runs tests against a mocked Bot API.
// Blocked:
//   - any request to api.telegram.org (curl, wget, python/node one-liners, WebFetch ...)
//   - app endpoints that call Telegram: /settings/telegram/candidates (getUpdates),
//     /settings/telegram/recipients/{chat_id}/test (sendMessage)
//   - the CLI check `python -m app.notify test` (sendMessage to every recipient)
// Allowed: searching the code for these strings (grep/rg/git/...), and everything else, including pytest,
// whose Telegram client runs on httpx.MockTransport and never reaches the network.
// Exit code 2 = the tool call is BLOCKED and stderr is fed back to the agent as the reason.
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

// Що саме робить виклик у Telegram. Регістр не важливий: URL і шляхи бувають у будь-якому.
const TELEGRAM_TARGETS = [
  /api\.telegram\.org/i,
  /\/settings\/telegram\/candidates\b/i,
  /\/settings\/telegram\/recipients\/[^\s/'"]+\/test\b/i,
  /\bapp\.notify\s+test\b/i,
];

// Команди, що лише шукають чи показують текст: `grep -rn api.telegram.org backend` — читання коду, не виклик.
// Дивимось на перше слово КОЖНОГО сегмента конвеєра: `grep … | curl …` уже не лише пошук.
const SEARCH_ONLY = new Set(["grep", "egrep", "fgrep", "rg", "git", "ls", "find", "wc", "head", "tail", "cat", "sed", "awk"]);

const block = (what) => {
  process.stderr.write(
    `Blocked by hook (protect-telegram): ${what}. The agent must not call the Telegram Bot API — ` +
      `directly, through app endpoints that reach Telegram, or via \`app.notify test\` — to avoid rate limits ` +
      `or a bot ban. Ask the user to do it by hand (UI buttons «Надіслати тест» / «Знайти чати»). ` +
      `If you were only writing code that mentions these strings, use the Edit/Write tools instead of a shell script.\n`,
  );
  process.exit(2);
};

if (ev.tool_name === "WebFetch") {
  const url = String(input.url ?? "");
  if (TELEGRAM_TARGETS.some((re) => re.test(url))) block(`WebFetch ${url}`);
  process.exit(0);
}

if (ev.tool_name === "Bash") {
  const command = String(input.command ?? "");
  if (TELEGRAM_TARGETS.some((re) => re.test(command))) {
    const searchOnly = command.split(/\|\||&&|[|;\n]/).every((segment) => {
      const first = segment.trim().split(/\s+/)[0] ?? "";
      if (first === "") return true;
      const bin = (first.replace(/\\/g, "/").split("/").pop() ?? "").toLowerCase();
      return SEARCH_ONLY.has(bin);
    });
    if (!searchOnly) block("this command reaches the Telegram Bot API");
  }
}
process.exit(0);
