#!/usr/bin/env python3
"""Add players' captured quest text to LorePath's community text.

LorePath saves the text of every quest you see as you play (descriptions,
objectives, progress and completion text). This script takes those saved files
and adds any quest text LorePath doesn't ship yet to Data/CommunityText.lua, so
every LorePath user gets it in the next release.

It reads LorePath's saved-variables file (LorePath.lua: LorePathDB.questCache),
from your own game or a player's. It's in the game's folder at
WTF/Account/<account>/SavedVariables/LorePath.lua.

Usage:
    pip install lupa
    python3 tools/merge_quest_text.py FILE [FILE ...]            # merge
    python3 tools/merge_quest_text.py --dry-run FILE [FILE ...]  # just report

Rules:
  - Only quests in Data/Quests.lua are kept.
  - Text already in Data/CommunityText.lua is never overwritten; only missing
    fields are added. Use --replace to let newer text replace existing fields.
  - Character names found in the file are replaced with $N, colour codes and
    links are stripped, and implausibly long text is rejected.
  - Quest text that the bundled vanilla text (Data/QuestText.lua) already has
    word for word isn't duplicated.
  - Saved gold, XP and reputation rewards are carried over too (m, x, r), within
    sane limits. LorePath doesn't display them yet.

The files run in a sandboxed Lua state with no libraries, so a submitted file
can't do anything but define data.
"""

import argparse
import os
import re
import sys

from lupa import LuaRuntime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "Data", "CommunityText.lua")
FIELDS = ("t", "o", "d", "p", "c")  # title, objectives, description, progress, completion
REWARDS = ("m", "x", "r")  # gold (copper), XP, reputation {{factionID, amount}, ...}; saved, not shown yet
MAX_LEN = 4000

HEADER = [
    "-- Quest text collected by LorePath's players (see issue #14), for quests the",
    "-- bundled vanilla text doesn't cover, such as WoW Forever's own. Updated with",
    "-- tools/merge_quest_text.py from players' saved files; edit with care.",
    "-- Fields: t title, o objectives, d description, p progress, c completion;",
    "-- rewards m gold (copper), x XP, r reputation {{factionID, amount}}.",
    "-- $N/$C/$R/$G/$B are filled in game.",
    "local _, ns = ...",
    "ns.CommunityText = {",
]

# Runs a saved-variables file with no libraries at all: it can only build tables.
SANDBOX = """
local src = ...
local env = {}
local chunk, err = load(src, "saved", "t", env)
if not chunk then error(err) end
chunk()
return env
"""


def lua_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def load_lua_data(lua, path, global_name):
    with open(path, encoding="utf-8-sig") as f:
        env = lua.execute(SANDBOX, f.read())
    return env[global_name] if env is not None else None


def ids_in(path):
    with open(path, encoding="utf-8") as f:
        return {int(m) for m in re.findall(r"^\[(\d+)\]=\{", f.read(), re.M)}


def load_table(lua, path, name):
    """Loads one of LorePath's own data files (local _, ns = ...)."""
    if not os.path.exists(path):
        return {}
    ns = lua.table()
    chunk = lua.eval("function(src, ns) return assert(load(src, '@data'))('LorePath', ns) end")
    with open(path, encoding="utf-8") as f:
        chunk(f.read(), ns)
    out = {}
    for qid, entry in (ns[name] or lua.table()).items():
        out[int(qid)] = {k: entry[k] for k in FIELDS if entry[k]}
        for k in REWARDS:
            value = reward_value(k, entry[k])
            if value is not None:
                out[int(qid)][k] = value
    return out


def reward_value(kind, value):
    """A sane gold/XP number or reputation list, or None."""
    if kind in ("m", "x"):
        return int(value) if isinstance(value, (int, float)) and 0 < value < 10_000_000 else None
    if value is None or not hasattr(value, "values"):
        return None
    out = []
    for pair in value.values():
        if pair is None or not hasattr(pair, "values"):
            continue
        faction, amount = pair[1], pair[2]
        if isinstance(faction, (int, float)) and isinstance(amount, (int, float)) and 0 < faction < 100_000 and -100_000 < amount < 100_000:
            out.append((int(faction), int(amount)))
    return out or None


def read_submission(lua, path):
    """Returns ({questID: {field: text}}, character names, format) for one file."""
    lorepath = load_lua_data(lua, path, "LorePathDB")
    if lorepath is not None and lorepath["questCache"] is not None:
        quests = {}
        for qid, e in lorepath["questCache"].items():
            quests[qid] = {"o": e["obj"], "d": e["text"], "p": e["prog"], "c": e["done"],
                           "m": e["money"], "x": e["xp"], "r": e["rep"]}
        names = set()
        if lorepath["characters"] is not None:
            names.update(str(n) for n in lorepath["characters"].keys())
        return quests, names, "LorePath"
    return None, set(), None


def cleaner(names):
    name_re = None
    if names:
        name_re = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b")

    def clean(value):
        if not isinstance(value, str):
            return None
        value = re.sub(r"\|c[0-9a-fA-F]{8}|\|r|\|H[^|]*\|h|\|h", "", value)  # colours and links
        value = value.replace("\r", "").strip()
        if not value or len(value) > MAX_LEN:
            return None
        if name_re:
            value = name_re.sub("$N", value)
        return value
    return clean


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="LorePath.lua saved-variables files")
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    parser.add_argument("--replace", action="store_true", help="let submitted text replace existing fields")
    args = parser.parse_args()

    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    known = ids_in(os.path.join(ROOT, "Data", "Quests.lua"))
    community = load_table(lua, OUT, "CommunityText")
    bundled = load_table(lua, os.path.join(ROOT, "Data", "QuestText.lua"), "QuestText")

    total_new_quests, total_fields = 0, 0
    for path in args.files:
        try:
            quests, names, kind = read_submission(lua, path)
        except Exception as e:  # a broken or hostile file
            print(f"{path}: couldn't read it ({str(e).splitlines()[0][:120]}), skipped")
            continue
        if quests is None:
            print(f"{path}: not a LorePath saved file, skipped")
            continue
        clean = cleaner(names)
        new_quests, fields, skipped = 0, 0, 0
        for key, entry in quests.items():
            try:
                qid = int(key)
            except (TypeError, ValueError):
                continue
            if qid not in known:
                skipped += 1
                continue
            target = community.get(qid, {})
            had = len(target)
            for field in FIELDS:
                value = clean(entry.get(field))
                if not value or bundled.get(qid, {}).get(field) == value:
                    continue
                if field not in target or (args.replace and target[field] != value):
                    target[field] = value
                    fields += 1
            for field in REWARDS:
                value = reward_value(field, entry.get(field))
                if value is not None and (field not in target or (args.replace and target[field] != value)):
                    target[field] = value
                    fields += 1
            if target:
                community[qid] = target
                new_quests += had == 0 and len(target) > 0
        total_new_quests += new_quests
        total_fields += fields
        notes = []
        if skipped:
            notes.append(f"{skipped} quests not in LorePath skipped")
        if names:
            notes.append("names replaced with $N: " + ", ".join(sorted(names)))
        print(f"{path}: {kind} file, {new_quests} new quests, {fields} new fields"
              + ("; " + "; ".join(notes) if notes else ""))

    if args.dry_run:
        print(f"Dry run: would add {total_new_quests} quests and {total_fields} fields.")
        return
    lines = list(HEADER)
    for qid in sorted(community):
        entry = community[qid]
        parts = [f"{k}={lua_string(entry[k])}" for k in FIELDS if k in entry]
        parts += [f"{k}={entry[k]}" for k in ("m", "x") if k in entry]
        if "r" in entry:
            parts.append("r={" + ",".join(f"{{{f},{a}}}" for f, a in entry["r"]) + "}")
        lines.append(f"[{qid}]={{{','.join(parts)}}},")
    lines.append("}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Added {total_new_quests} quests and {total_fields} fields; {len(community)} quests in Data/CommunityText.lua.")


if __name__ == "__main__":
    main()
