// Checks for the share page's code handling (worker.js). Run by
// tools/test/run_tests.py with node, or with macOS's jsc where node isn't installed.
import { readCodes, issueFor, page, MAX_CODES } from "./worker.js";

let failed = 0;
function check(ok, what) {
  (typeof console !== "undefined" ? console.log : print)((ok ? "PASS " : "FAIL ") + what);
  if (!ok) failed++;
}

const good = 'LP1:{"v":1,"q":{"874":{"d":"Hello $N.\\nGo `now`.","x":550,"r":[[81,2500]],"s":{"k":"u","n":3233,"m":1413,"x":45.1,"y":12.3}}}}';

let r = readCodes("Here you go:\n" + good + "\n");
check(r.codes && r.codes.length === 1 && r.quests === 1, "a pasted code is read, with text around it");
check(r.codes && r.codes[0].startsWith("LP1:") && !r.codes[0].includes("`"), "it's re-encoded with no backticks, so the issue's code block holds");
check(r.codes && JSON.parse(r.codes[0].slice(4)).q["874"].d === "Hello $N.\nGo `now`.", "and decodes back to the same text");

r = readCodes(good + "\n" + good.replace("874", "875"));
check(r.codes && r.codes.length === 2 && r.quests === 2, "several codes, one per line, are each read");
r = readCodes(good + good.replace("874", "876"));
check(r.codes && r.codes.length === 2, "so are codes pasted back to back");

check(readCodes("hello").error, "text with no code is refused");
check(readCodes("LP1:{not json").error, "a broken code is refused");
check(readCodes('LP1:{"v":2,"q":{"1":{}}}').error, "an unknown version is refused");
check(readCodes('LP1:{"v":1,"q":{"abc":{"d":"x"}}}').error, "a quest ID that isn't a number is refused");
check(readCodes('LP1:{"v":1,"q":{"1":{"evil":"x"}}}').error, "an unknown field is refused");
check(readCodes('LP1:{"v":1,"q":{"1":{"d":' + JSON.stringify("x".repeat(4001)) + "}}}").error, "over-long text is refused");
check(readCodes('LP1:{"v":1,"q":{"1":{"m":-5}}}').error, "a negative reward is refused");
check(readCodes(Array(MAX_CODES + 1).fill(good).join("\n")).error, "too many codes at once are refused");

const issue = issueFor(readCodes(good).codes[0], 2, 3);
check(issue.labels.length === 1 && issue.labels[0] === "quest-text", "the issue has the quest-text label the workflow looks for");
check(issue.title === "Quest text from a player (2 of 3)" && issue.body.split("\n").some((l) => l.startsWith("LP1:{")), "and the code on a line of its own, as the merge tool reads it");

check(page('abc"><script>').includes('data-sitekey="abcscript"'), "the page can't be broken by its site key setting");

if (failed) {
  throw new Error(failed + " worker checks failed");
}
