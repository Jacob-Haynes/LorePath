#!/usr/bin/env python3
"""Where the items that start quests come from, from pfQuest's database.

Some quests start from an item (Data/Quests.lua's `si`, from AllTheThings):
Allegiance to the Old Gods starts from a Damp Note. pfQuest
(https://github.com/shagu/pfQuest, MIT; its data comes from VMaNGOS) knows
which creatures drop each item, and which objects (chests, crates) hold it,
with chances, and where those creatures and objects are. This writes the top
few sources for each item-started quest to Data/QuestStarts.lua, so LorePath
can say "Dropped by Blackfathom Tide Priestess (33%), in Blackfathom Deeps"
and set a waypoint at an outdoor source.

Usage:
    pip install lupa
    python3 tools/extract_quest_starts.py        # downloads pfQuest's files
    python3 tools/extract_quest_starts.py DIR    # or uses local copies in DIR, named like
                                                 # db_items.lua, db_enUS_units.lua

Run it again after Data/Quests.lua gains item-started quests. pfQuest's
vanilla data doesn't change, so it isn't part of the weekly sync.
"""

import collections
import os
import re
import sys
import urllib.request

from lupa import LuaRuntime

PFQUEST_DB = "https://raw.githubusercontent.com/shagu/pfQuest/master/db/"
FILES = ["items.lua", "units.lua", "objects.lua", "enUS/units.lua", "enUS/objects.lua"]
MAX_SOURCES = 3

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "Data", "QuestStarts.lua")

# pfQuest places creatures and objects by the game's zone area IDs; LorePath's
# pages and waypoints use map IDs.
AREA_TO_MAP = {
    1: 1426, 3: 1418, 4: 1419, 8: 1435, 10: 1431, 11: 1437, 12: 1429, 14: 1411,
    15: 1445, 16: 1447, 17: 1413, 28: 1422, 33: 1434, 36: 1416, 38: 1432, 40: 1436,
    41: 1430, 44: 1433, 45: 1417, 46: 1428, 47: 1425, 51: 1427, 85: 1420, 130: 1421,
    139: 1423, 141: 1438, 148: 1439, 215: 1412, 267: 1424, 331: 1440, 357: 1444,
    361: 1448, 400: 1441, 405: 1443, 406: 1442, 440: 1446, 490: 1449, 493: 1450,
    618: 1452, 1377: 1451, 1497: 1458, 1519: 1453, 1537: 1455, 1637: 1454,
    1638: 1456, 1657: 1457,
}


def fetch(name):
    with urllib.request.urlopen(PFQUEST_DB + name, timeout=120) as response:
        return response.read().decode("utf-8")


def load(local_dir):
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    lua.execute("pfDB = { items = {}, units = {}, objects = {} }")
    for name in FILES:
        if local_dir:
            with open(os.path.join(local_dir, "db_" + name.replace("/", "_")), encoding="utf-8") as f:
                src = f.read()
        else:
            src = fetch(name)
        lua.execute(src)
    return lua.globals()["pfDB"]


def quest_items():
    """From Data/Quests.lua: {questID: start item ID}, {questID: page},
    {area ID: instance page}, and the set of dungeon and raid pages."""
    with open(os.path.join(ROOT, "Data", "Quests.lua"), encoding="utf-8") as f:
        data = f.read()
    items = {int(q): int(i) for q, i in re.findall(r"^\[(\d+)\]=\{[^\n]*\bsi=(\d+)", data, re.M)}
    pages = {int(q): int(z) for q, z in re.findall(r"^\[(\d+)\]=\{z=(-?\d+),", data, re.M)}
    kinds = data.split("ns.InstanceZones = {")[1].split("\n}")[0]
    dungeons = {int(k) for k, v in re.findall(r'^\[(-?\d+)\]="(\w+)"', kinds, re.M) if v in ("dungeon", "raid")}
    info = data.split("ns.InstanceInfo = {")[1].split("\n}")[0]
    instance_areas = {}
    for page, area in re.findall(r"^\[(-?\d+)\]=\{[^\n]*\bar=(\d+)", info, re.M):
        instance_areas.setdefault(int(area), int(page))
    return items, pages, instance_areas, dungeons


def place(coords, instance_areas):
    """Where a creature or object mostly is: {m, x, y} outdoors, {i} inside an
    instance, or {} when pfQuest doesn't say."""
    if coords is None:
        return {}
    points = [p for p in coords.values() if p is not None and p[3] is not None]
    if not points:
        return {}
    by_area = collections.Counter(int(p[3]) for p in points)
    area = by_area.most_common(1)[0][0]
    if area in AREA_TO_MAP:
        here = [p for p in points if int(p[3]) == area]
        x = sum(float(p[1]) for p in here) / len(here)
        y = sum(float(p[2]) for p in here) / len(here)
        # The spawn nearest the middle, so the waypoint lands on a real spot.
        best = min(here, key=lambda p: (float(p[1]) - x) ** 2 + (float(p[2]) - y) ** 2)
        return {"m": AREA_TO_MAP[area], "x": round(float(best[1]), 1), "y": round(float(best[2]), 1)}
    if area in instance_areas:
        return {"i": instance_areas[area]}
    return {}


def lua_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def chance_text(chance):
    return f"{chance:g}" if chance >= 1 else f"{chance:.2g}"


def main():
    local_dir = sys.argv[1] if len(sys.argv) > 1 else None
    pf = load(local_dir)
    items, units, objects = pf["items"]["data"], pf["units"]["data"], pf["objects"]["data"]
    unit_names, object_names = pf["units"]["enUS"], pf["objects"]["enUS"]
    quests, pages, instance_areas, dungeons = quest_items()

    out, counts = {}, collections.Counter()
    for qid, item in sorted(quests.items()):
        entry = items[item]
        if entry is None:
            counts["item not in pfQuest"] += 1
            continue
        sources = []
        for kind, table, names in (("u", units, unit_names), ("o", objects, object_names)):
            found = entry[kind.upper()]
            if found is None:
                continue
            for source_id, chance in found.items():
                name = names[source_id]
                if not name:
                    continue
                if pages.get(qid) in dungeons:
                    # A dungeon or raid quest's item drops inside, even when the
                    # creature also lives outdoors (Blackfathom Tide Priestesses).
                    where = {"i": pages[qid]}
                else:
                    where = place(table[source_id] and table[source_id]["coords"], instance_areas)
                sources.append((float(chance), kind, int(source_id), str(name), where))
        if not sources:
            counts["no source"] += 1
            continue
        sources.sort(key=lambda s: (-s[0], s[2]))
        out[qid] = sources[:MAX_SOURCES]
        counts["with sources"] += 1
        counts["with a location"] += any(s[4] for s in out[qid])

    lines = [
        "-- Generated by tools/extract_quest_starts.py. Do not edit by hand.",
        "-- Source: pfQuest's database (https://github.com/shagu/pfQuest, MIT; data from VMaNGOS).",
        "-- Where a quest's starting item comes from: k \"u\" a creature that drops it, \"o\" an object",
        "-- that holds it; n English name, c chance in %; m/x/y where it mostly is (map ID, %),",
        "-- or i the instance page it's inside.",
        "local _, ns = ...",
        "ns.QuestStarts = {",
    ]
    for qid in sorted(out):
        parts = []
        for chance, kind, _, name, where in out[qid]:
            fields = [f'k="{kind}"', f"n={lua_string(name)}", f"c={chance_text(chance)}"]
            fields += [f"{k}={where[k]:g}" if isinstance(where[k], float) else f"{k}={where[k]}" for k in ("m", "x", "y", "i") if k in where]
            parts.append("{" + ",".join(fields) + "}")
        lines.append(f"[{qid}]={{{','.join(parts)}}},")
    lines.append("}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(quests)} item-started quests: " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
