// LorePath's share page (issue #14): a Cloudflare Worker that lets players send
// the quest text /lp share gives them without a GitHub account.
//
//   GET  /        the page: paste your code(s), pass a Turnstile check, send.
//   POST /submit  checks each code and opens one "Share quest text" issue per
//                 code (labelled quest-text), exactly like the issue form does,
//                 so .github/workflows/community-text.yml takes it from there.
//
// Settings (see share/README.md): REPO and TURNSTILE_SITE_KEY in wrangler.toml;
// secrets GITHUB_TOKEN (fine-grained, Issues: read and write on REPO only) and
// TURNSTILE_SECRET, set with `wrangler secret put`.
//
// Nothing is stored here. A code is checked, re-encoded from the parsed JSON
// (so only quest data gets through, never arbitrary text) and becomes a public
// issue.

export const PREFIX = "LP1:";
export const MAX_CODES = 10; // per submission
export const MAX_CODE = 64000; // characters, under GitHub's 65,536 per issue body
const MAX_BODY = 800000; // bytes in a request
const MAX_TEXT = 4000; // per text field, as tools/merge_quest_text.py
const TEXT_FIELDS = ["t", "o", "d", "p", "c"];
const START_KINDS = ["u", "o", "i"];

function isCount(n) {
  return Number.isInteger(n) && n >= 0 && n < 1e9;
}

function checkEntry(e) {
  if (!e || typeof e !== "object" || Array.isArray(e)) return "a quest entry isn't an object";
  for (const key of Object.keys(e)) {
    const v = e[key];
    if (TEXT_FIELDS.includes(key)) {
      if (typeof v !== "string" || v.length > MAX_TEXT) return `field ${key} isn't quest text`;
    } else if (key === "m" || key === "x") {
      if (!isCount(v)) return `field ${key} isn't a number`;
    } else if (key === "r") {
      if (!Array.isArray(v) || v.length > 20 || !v.every((p) => Array.isArray(p) && p.length === 2 && isCount(p[0]) && Number.isInteger(p[1]) && Math.abs(p[1]) < 1e7)) {
        return "field r isn't a reputation list";
      }
    } else if (key === "s") {
      if (!v || typeof v !== "object" || !START_KINDS.includes(v.k)) return "field s isn't a quest start";
      for (const [sk, sv] of Object.entries(v)) {
        if (sk === "k") continue;
        if (!["n", "m", "i", "x", "y"].includes(sk) || typeof sv !== "number" || !Number.isFinite(sv)) return "field s isn't a quest start";
      }
    } else {
      return `unknown field ${key}`;
    }
  }
  return null;
}

// Every share code in `text` (one per line, as the game gives them), checked.
// Returns { codes: [re-encoded code, ...], quests: count } or { error }.
export function readCodes(text) {
  if (typeof text !== "string") return { error: "No share code found." };
  const found = [];
  for (const line of text.split(/\r?\n/)) {
    let at = line.indexOf(PREFIX);
    if (at < 0) continue;
    // Codes pasted back to back on one line: split them at each prefix.
    const pieces = line.slice(at).split(PREFIX).slice(1);
    for (const piece of pieces) found.push(piece.trim().replace(/^`+|`+$/g, ""));
  }
  if (found.length === 0) return { error: "No share code found. It starts with LP1: — copy it with /lp share in game." };
  if (found.length > MAX_CODES) return { error: `That's ${found.length} codes; send at most ${MAX_CODES} at a time.` };
  const codes = [];
  let quests = 0;
  for (const [i, raw] of found.entries()) {
    const which = found.length > 1 ? `Code ${i + 1}: ` : "";
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return { error: `${which}it doesn't decode. Copy it again with /lp share and paste the whole thing.` };
    }
    if (!payload || payload.v !== 1 || !payload.q || typeof payload.q !== "object" || Array.isArray(payload.q)) {
      return { error: `${which}it isn't a LorePath share code.` };
    }
    const ids = Object.keys(payload.q);
    if (ids.length === 0) return { error: `${which}it has no quests in it.` };
    for (const id of ids) {
      if (!/^[1-9][0-9]{0,6}$/.test(id)) return { error: `${which}it has a quest ID that isn't a number.` };
      const problem = checkEntry(payload.q[id]);
      if (problem) return { error: `${which}quest ${id}: ${problem}.` };
    }
    // Re-encoded from what was parsed, with backticks escaped so the issue's
    // code block can't be closed early.
    const code = PREFIX + JSON.stringify({ v: 1, q: payload.q }).replace(/`/g, "\\u0060");
    if (code.length > MAX_CODE) return { error: `${which}it's too long for one issue. LorePath splits big collections into several codes: send each one.` };
    codes.push(code);
    quests += ids.length;
  }
  return { codes, quests };
}

// The issue for one code, in the issue form's layout.
export function issueFor(code, part, parts) {
  const of = parts > 1 ? ` (${part} of ${parts})` : "";
  return {
    title: "Quest text from a player" + of,
    body: "### Share code\n\n```\n" + code + "\n```\n\n_Sent from the LorePath share page._\n",
    labels: ["quest-text"],
  };
}

async function verifyTurnstile(env, token, ip) {
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token || "");
  if (ip) form.append("remoteip", ip);
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
  const out = await res.json().catch(() => ({}));
  return out.success === true;
}

async function openIssue(env, issue) {
  const res = await fetch(`https://api.github.com/repos/${env.REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "lorepath-share",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(issue),
  });
  if (!res.ok) throw new Error(`GitHub said ${res.status}`);
  const out = await res.json();
  return out.html_url;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json; charset=utf-8" } });
}

async function submit(request, env) {
  if (!env.GITHUB_TOKEN || !env.TURNSTILE_SECRET || !env.REPO) {
    return json({ error: "The share page isn't set up yet. Please use a GitHub issue for now." }, 503);
  }
  const length = Number(request.headers.get("Content-Length") || 0);
  if (length > MAX_BODY) return json({ error: "That's too much to send at once." }, 413);
  const text = await request.text();
  if (text.length > MAX_BODY) return json({ error: "That's too much to send at once." }, 413);
  let input;
  try {
    input = JSON.parse(text);
  } catch {
    return json({ error: "Something went wrong sending that. Please try again." }, 400);
  }
  if (!(await verifyTurnstile(env, input.token, request.headers.get("CF-Connecting-IP")))) {
    return json({ error: "The check that you're not a bot didn't pass. Please try again." }, 403);
  }
  const read = readCodes(input.codes);
  if (read.error) return json({ error: read.error }, 400);
  const links = [];
  try {
    for (const [i, code] of read.codes.entries()) {
      links.push(await openIssue(env, issueFor(code, i + 1, read.codes.length)));
    }
  } catch (e) {
    return json({ error: "Couldn't pass it on to GitHub just now. Please try again later.", links }, 502);
  }
  return json({ quests: read.quests, links });
}

export function page(siteKey) {
  const key = String(siteKey || "").replace(/[^A-Za-z0-9_-]/g, "");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Share quest text</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<style>
:root { --bg: #f7f3ea; --fg: #2b2418; --muted: #6b5f4b; --card: #fffdf8; --line: #d8ccb4; --accent: #8a5a12; --ok: #2f6b2f; --bad: #9b2c2c; }
@media (prefers-color-scheme: dark) { :root { --bg: #17140f; --fg: #ece3d0; --muted: #a89a80; --card: #221d16; --line: #3d3427; --accent: #e0b062; --ok: #8fcf8f; --bad: #f09a9a; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 720px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 8px; color: var(--accent); }
p { margin: 0 0 12px; }
ol { padding-left: 20px; margin: 0 0 16px; }
.muted { color: var(--muted); font-size: 0.92rem; }
textarea { width: 100%; min-height: 220px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: var(--fg); font: 13px/1.4 ui-monospace, Menlo, Consolas, monospace; resize: vertical; }
.row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; }
button { padding: 10px 20px; border: 0; border-radius: 8px; background: var(--accent); color: var(--bg); font-weight: 600; font-size: 1rem; cursor: pointer; }
button:disabled { opacity: 0.5; cursor: default; }
#status { min-height: 1.5em; }
.ok { color: var(--ok); } .bad { color: var(--bad); }
a { color: var(--accent); }
code { font-family: ui-monospace, Menlo, Consolas, monospace; }
</style>
</head>
<body>
<main>
<h1>Share quest text</h1>
<p>LorePath saves the story of every quest you see. Sharing it puts that text into the next release, so players who missed it can read it too. No account needed.</p>
<ol>
<li>In game, type <code>/lp share</code> (or press <strong>Share quest text</strong> in LorePath's settings).</li>
<li>Click the code, press <strong>Ctrl+C</strong>, and paste it below. Got several codes? Paste each one on its own line.</li>
<li>Press <strong>Send</strong>.</li>
</ol>
<form id="form">
<label for="codes" class="muted">Share code (starts with <code>LP1:</code>)</label>
<textarea id="codes" name="codes" spellcheck="false" autocomplete="off" placeholder='LP1:{"v":1,"q":{...}}' required></textarea>
<div class="row">
<div class="cf-turnstile" data-sitekey="${key}"></div>
</div>
<div class="row">
<button id="send" type="submit">Send</button>
<span id="status" role="status" aria-live="polite"></span>
</div>
</form>
<p class="muted">The code holds only quest text, rewards and where quests start. Your character's name, class and race are already replaced with <code>$N</code>, <code>$C</code> and <code>$R</code>. It becomes a public issue on LorePath's GitHub page, where a maintainer reviews it before it goes into a release. This page doesn't keep anything.</p>
</main>
<script>
const form = document.getElementById("form");
const status = document.getElementById("status");
const send = document.getElementById("send");
function say(text, kind) { status.textContent = text; status.className = kind || ""; }
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const codes = document.getElementById("codes").value;
  const token = (form.querySelector('[name="cf-turnstile-response"]') || {}).value || "";
  if (!codes.includes("LP1:")) { say("That doesn't look like a share code: it starts with LP1:", "bad"); return; }
  if (!token) { say("Please complete the check above first.", "bad"); return; }
  send.disabled = true;
  say("Sending…");
  try {
    const res = await fetch("/submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ codes, token }) });
    const out = await res.json();
    if (!res.ok) throw new Error(out.error || "Something went wrong.");
    status.className = "ok";
    status.textContent = "Thank you! " + out.quests + (out.quests === 1 ? " quest" : " quests") + " sent. ";
    out.links.forEach((url, i) => {
      const a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = out.links.length > 1 ? "Follow it (" + (i + 1) + ")" : "Follow its progress";
      status.append(a, " ");
    });
    document.getElementById("codes").value = "";
  } catch (e) {
    say(e.message, "bad");
  } finally {
    send.disabled = false;
    if (window.turnstile) window.turnstile.reset();
  }
});
</script>
</body>
</html>`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" && request.method === "GET") {
      return new Response(page(env.TURNSTILE_SITE_KEY), {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'",
          "X-Content-Type-Options": "nosniff",
          "Referrer-Policy": "no-referrer",
        },
      });
    }
    if (url.pathname === "/submit" && request.method === "POST") {
      return submit(request, env);
    }
    return new Response("Not found", { status: 404 });
  },
};
