#!/usr/bin/env python3
"""Zone lore from the Warcraft Wiki (issue #5).

The summaries LorePath shows at the top of a zone's page are written by hand in
tools/lore/zones.txt, from one or more wiki articles each. Around that:

  python3 tools/wiki_lore.py fetch [--report FILE]
      Refreshes tools/lore/wiki/: a snapshot of the text of every article a
      summary uses, and the list of WoW Forever's own articles (its zones,
      instances, subzones and lore). A snapshot only changes when the article's
      text does, so its diff is what changed on the wiki. Then prints (or
      writes to FILE, as Markdown) what needs a look: summaries whose articles
      have changed, and Forever articles that are new or that no summary uses.
      The weekly workflow (.github/workflows/sync-wiki-lore.yml) runs this and
      opens a PR with the snapshots and that report.

  python3 tools/wiki_lore.py status
      The same report from the committed snapshots, without fetching.

  python3 tools/wiki_lore.py build
      Writes Data/Lore.lua from tools/lore/zones.txt. Entries with no text yet
      are left out.

The Warcraft Wiki's text is CC BY-SA 4.0, and so are summaries made from it:
Data/Lore.lua says so in its header, and Data/WarcraftWiki-LICENSE.txt has
the notice. LorePath's code stays MIT.

zones.txt format: an entry starts with "== <map ID> <name>" (the name is for
people), then one "source: <article title> @ <revision>" line for each article
the summary was written from (the revision it was written from; leave it empty
until there's text), then a blank line and the summary. Paragraphs are
separated by blank lines. Lines starting with "#" are comments.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZONES = os.path.join(ROOT, "tools", "lore", "zones.txt")
SNAPSHOTS = os.path.join(ROOT, "tools", "lore", "wiki")
FOREVER_LIST = os.path.join(SNAPSHOTS, "_forever-articles.txt")
OUT = os.path.join(ROOT, "Data", "Lore.lua")
QUESTS = os.path.join(ROOT, "Data", "Quests.lua")

WIKI = "https://warcraft.wiki.gg"
API = WIKI + "/api.php"
# The wiki asks scripts to say who they are; requests are batched and spaced out.
USER_AGENT = "LorePath-lore-fetch/1.0 (+https://github.com/Jacob-Haynes/LorePath)"
BATCH = 20  # the most titles TextExtracts and categories take per request
PAUSE = 2.0  # seconds between requests

# WoW Forever's own articles, watched for new ones. (Not "Forever quests":
# there are over a thousand; a quest article is used when a summary needs it.)
FOREVER_CATEGORIES = ["Forever zones", "Forever instances", "Forever subzones", "Forever lore articles"]


# ---------------------------------------------------------------------------
# zones.txt
# ---------------------------------------------------------------------------

def parse_zones(text):
    """Entries in file order: {id, name, sources: [(title, revision or None)], text}."""
    entries, entry, body = [], None, []
    in_header = False

    def finish():
        if entry is not None:
            paragraphs, current = [], []
            for line in body:
                if line.strip():
                    current.append(line.strip())
                elif current:
                    paragraphs.append(" ".join(current))
                    current = []
            if current:
                paragraphs.append(" ".join(current))
            entry["text"] = "\n\n".join(paragraphs)
            entries.append(entry)

    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            continue
        if line.startswith("== "):
            finish()
            parts = line[3:].split(None, 1)
            try:
                map_id = int(parts[0])
            except (IndexError, ValueError):
                raise SystemExit(f"zones.txt line {number}: expected '== <map ID> <name>'")
            entry, body = {"id": map_id, "name": parts[1] if len(parts) > 1 else "", "sources": []}, []
            in_header = True
            continue
        if entry is None:
            if line.strip():
                raise SystemExit(f"zones.txt line {number}: text before the first entry")
            continue
        if in_header and line.startswith("source:"):
            value = line.split(":", 1)[1]
            title, _, revision = value.partition("@")
            title, revision = title.strip(), revision.strip()
            if not title:
                raise SystemExit(f"zones.txt line {number}: a source needs an article title")
            if revision and not revision.isdigit():
                raise SystemExit(f"zones.txt line {number}: '{revision}' isn't a revision number")
            entry["sources"].append((title, int(revision) if revision else None))
        else:
            in_header = False
            body.append(line)
    finish()

    seen = set()
    for e in entries:
        if e["id"] in seen:
            raise SystemExit(f"zones.txt: map {e['id']} has two entries")
        seen.add(e["id"])
        if not e["sources"]:
            raise SystemExit(f"zones.txt: map {e['id']} ({e['name']}) has no source")
        if e["text"] and any(rev is None for _, rev in e["sources"]):
            raise SystemExit(f"zones.txt: map {e['id']} ({e['name']}) has text but a source with no revision")
    return entries


def read_zones():
    with open(ZONES, encoding="utf-8") as f:
        return parse_zones(f.read())


def lua_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def render_lua(entries):
    lines = [
        "-- Generated by tools/wiki_lore.py from tools/lore/zones.txt. Do not edit by hand.",
        "-- Zone lore summarised from the Warcraft Wiki (https://warcraft.wiki.gg), whose text is",
        "-- CC BY-SA 4.0; these summaries are under the same licence (see Data/WarcraftWiki-LICENSE.txt).",
        "-- Each entry names the articles it was summarised from.",
        "local _, ns = ...",
        "ns.ZoneLore = {",
    ]
    for e in sorted((e for e in entries if e["text"]), key=lambda e: e["id"]):
        articles = ",".join(lua_string(title) for title, _ in e["sources"])
        lines.append(f"[{e['id']}]={{articles={{{articles}}},text={lua_string(e['text'])}}},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build():
    entries = read_zones()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render_lua(entries))
    written = sum(1 for e in entries if e["text"])
    print(f"Wrote {OUT}: {written} of {len(entries)} zones have lore.")


# ---------------------------------------------------------------------------
# Snapshots (tools/lore/wiki/)
# ---------------------------------------------------------------------------

def snapshot_path(title):
    return os.path.join(SNAPSHOTS, re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_") + ".txt")


def article_url(title):
    return f"{WIKI}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def render_snapshot(title, revision, part, text):
    return (f"title: {title}\nrevision: {revision}\npart: {part}\nurl: {article_url(title)}\n\n"
            f"{text.strip()}\n")


def read_snapshot(title):
    """{title, revision, part, text}, or None if there's no snapshot."""
    try:
        with open(snapshot_path(title), encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return None
    head, _, text = content.partition("\n\n")
    fields = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    return {"title": fields.get("title", title), "revision": int(fields.get("revision", 0)),
            "part": fields.get("part", ""), "text": text.strip()}


def read_forever_list():
    """{category: [titles]} from the committed list."""
    lists = {}
    try:
        with open(FOREVER_LIST, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or ": " not in line:
                    continue
                category, title = line.rstrip("\n").split(": ", 1)
                lists.setdefault(category, []).append(title)
    except FileNotFoundError:
        pass
    return lists


def render_forever_list(lists):
    lines = ["# WoW Forever's own articles on the Warcraft Wiki, by category. Written by",
             "# tools/wiki_lore.py fetch; a new line here is a new Forever article."]
    for category in FOREVER_CATEGORIES:
        for title in sorted(lists.get(category, [])):
            lines.append(f"{category}: {title}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The wiki
# ---------------------------------------------------------------------------

_last_request = [0.0]


def api_get(params):
    wait = _last_request[0] + PAUSE - time.time()
    if wait > 0:
        time.sleep(wait)
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                _last_request[0] = time.time()
                return json.load(response)
        except urllib.error.HTTPError as err:
            if err.code not in (429, 503) or attempt == 3:
                raise
            delay = int(err.headers.get("Retry-After") or 30)
            print(f"  the wiki asked us to wait {delay}s", file=sys.stderr)
            time.sleep(delay)


def fetch_category(category):
    titles, params = [], {"action": "query", "list": "categorymembers", "cmtitle": "Category:" + category,
                          "cmnamespace": 0, "cmlimit": 500}
    while True:
        data = api_get(params)
        titles += [m["title"] for m in data["query"]["categorymembers"]]
        if "continue" not in data:
            return titles
        params.update(data["continue"])


def fetch_pages(titles, forever):
    """{asked title: {title, revision, part, text}} for the titles that exist. An
    article that's WoW Forever's own is kept whole (they're short, and a quest's
    story is past its first heading); for the rest, the opening section."""
    pages = {}
    for start in range(0, len(titles), BATCH):
        batch = titles[start:start + BATCH]
        data = api_get({"action": "query", "prop": "revisions|extracts", "rvprop": "ids", "redirects": 1,
                        "exintro": 1, "explaintext": 1, "exlimit": BATCH, "titles": "|".join(batch)})
        query = data.get("query", {})
        renamed = {}
        for step in query.get("normalized", []) + query.get("redirects", []):
            renamed[step["from"]] = step["to"]
        found = {p["title"]: p for p in query.get("pages", []) if not p.get("missing")}
        for asked in batch:
            title = asked
            while title in renamed:
                title = renamed[title]
            page = found.get(title)
            if page:
                pages[asked] = {"title": title, "revision": page["revisions"][0]["revid"],
                                "part": "intro", "text": page.get("extract", "")}
    for asked, page in pages.items():
        if page["title"] in forever or asked in forever:
            # TextExtracts gives a whole article only one at a time.
            data = api_get({"action": "query", "prop": "extracts", "explaintext": 1, "titles": page["title"]})
            page["text"] = data["query"]["pages"][0].get("extract", "")
            page["part"] = "whole"
    return pages


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

def lore_pages():
    """LorePath's zone, dungeon and raid pages (map IDs) from its quest data."""
    with open(QUESTS, encoding="utf-8") as f:
        return {int(z) for z in re.findall(r"\bz=(-?\d+)", f.read())}


def report(entries, forever_lists, new_forever=None, missing=()):
    """Markdown: what needs a look, from the committed (or just fetched) snapshots."""
    out = []
    stale = []
    for e in entries:
        if not e["text"]:
            continue
        for title, revision in e["sources"]:
            snap = read_snapshot(title)
            if snap and snap["revision"] != revision:
                stale.append((e, title, revision, snap["revision"]))
    out.append("### Summaries to update")
    if stale:
        out.append("Their articles' text has changed since they were written. Update the summary in "
                   "`tools/lore/zones.txt`, set the source's revision to the new one, and run "
                   "`python3 tools/wiki_lore.py build`.")
        out.append("")
        for e, title, old, new in stale:
            out.append(f"- **{e['name']}** ({e['id']}): [{title}]({article_url(title)}), "
                       f"[what changed]({WIKI}/index.php?diff={new}&oldid={old}) (revision {old} to {new})")
    else:
        out.append("None: every summary was written from its articles' current text.")
    out.append("")

    if missing:
        out.append("### Sources that weren't found")
        out.append("Renamed or deleted on the wiki? Fix the title in `tools/lore/zones.txt`.")
        out.append("")
        out += [f"- {title}" for title in missing]
        out.append("")

    used = {title for e in entries for title, _ in e["sources"]}
    if new_forever:
        out.append("### New Forever articles")
        out.append("New on the wiki since the last check. Worth a summary, or a line in one?")
        out.append("")
        for category, title in new_forever:
            out.append(f"- [{title}]({article_url(title)}) ({category})")
        out.append("")

    unused = [(c, t) for c in FOREVER_CATEGORIES for t in sorted(forever_lists.get(c, [])) if t not in used]
    if unused:
        out.append("<details><summary>" + f"{len(unused)} Forever articles no summary uses yet" + "</summary>")
        out.append("")
        for category, title in unused:
            out.append(f"- [{title}]({article_url(title)}) ({category})")
        out.append("")
        out.append("</details>")
        out.append("")

    pages = lore_pages()
    with_text = {e["id"] for e in entries if e["text"]}
    out.append(f"{len(pages & with_text)} of LorePath's {len(pages)} zone, dungeon and raid pages have a summary.")
    return "\n".join(out) + "\n", stale


def fetch(report_file):
    entries = read_zones()
    os.makedirs(SNAPSHOTS, exist_ok=True)

    old_lists = read_forever_list()
    lists = {category: fetch_category(category) for category in FOREVER_CATEGORIES}
    with open(FOREVER_LIST, "w", encoding="utf-8") as f:
        f.write(render_forever_list(lists))
    old_titles = {t for titles in old_lists.values() for t in titles}
    new_forever = [] if not old_lists else [
        (c, t) for c in FOREVER_CATEGORIES for t in sorted(lists[c]) if t not in old_titles]
    forever = {t for titles in lists.values() for t in titles}

    titles = sorted({title for e in entries for title, _ in e["sources"]})
    # Forever quest articles a summary uses aren't in the watched categories.
    forever |= {t for t in titles if "(Forever)" in t}
    forever |= set(fetch_forever_members(titles))
    pages = fetch_pages(titles, forever)
    changed = 0
    for title in titles:
        page = pages.get(title)
        if not page:
            continue
        old = read_snapshot(title)
        # Keep the snapshot (and its revision) unless the text itself changed,
        # so edits elsewhere in a long article don't show up as changes.
        if old and old["text"] == page["text"].strip() and old["part"] == page["part"]:
            continue
        with open(snapshot_path(title), "w", encoding="utf-8") as f:
            f.write(render_snapshot(title, page["revision"], page["part"], page["text"]))
        changed += 1
    missing = [t for t in titles if t not in pages]

    text, stale = report(entries, lists, new_forever, missing)
    print(f"Fetched {len(pages)} articles ({changed} changed) and {len(forever)} Forever article titles.",
          file=sys.stderr)
    if report_file:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)


def fetch_forever_members(titles):
    """Which of these titles are in any "Forever ..." category (quests, NPCs too)."""
    members = []
    for start in range(0, len(titles), BATCH):
        batch = titles[start:start + BATCH]
        data = api_get({"action": "query", "prop": "categories", "cllimit": "max", "redirects": 1,
                        "titles": "|".join(batch)})
        for page in data.get("query", {}).get("pages", []):
            if any(c["title"].startswith("Category:Forever ") for c in page.get("categories", [])):
                members.append(page["title"])
    return members


def status():
    text, _ = report(read_zones(), read_forever_list())
    print(text)


def main(argv):
    args = argv[1:]
    if args == ["build"]:
        build()
    elif args == ["status"]:
        status()
    elif args[:1] == ["fetch"] and (len(args) == 1 or (len(args) == 3 and args[1] == "--report")):
        fetch(args[2] if len(args) == 3 else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
