#!/usr/bin/env python3
"""Build LorePath's quest data from AllTheThings' WoW Forever database.

AllTheThings (https://github.com/ATTWoWAddon/AllTheThings) is MIT-licensed. Its
WoW Forever data lives in db/Camelot ("camelot" is the game type Forever uses).

This script loads ATT's zone file inside a sandboxed Lua runtime (no os/io/load),
walks the zone tree, and writes the quest records LorePath needs to
Data/Quests.lua.

Usage:
    pip install lupa
    git clone --depth 1 --filter=blob:none --sparse https://github.com/ATTWoWAddon/AllTheThings.git att
    (cd att && git sparse-checkout set db/Camelot)
    python3 tools/extract_att.py att

Run it again whenever ATT updates its Forever data.
"""

import os
import shutil
import subprocess
import sys

from lupa import LuaRuntime

FOREVER_BUILD = 16001  # quests added after this build (awp) or removed by it (rwp) are skipped

LOADER = r"""
local src = ...
local env = {
  pairs = pairs, ipairs = ipairs, type = type, tostring = tostring, tonumber = tonumber,
  select = select, next = next, table = table, string = string, math = math,
  unpack = table.unpack, setmetatable = setmetatable,
}
-- ANY stands in for ATT helpers this script does not model: every index or call
-- returns ANY and writes are ignored, so helper lookups never fail.
ANY = setmetatable({}, {
  __index = function() return ANY end,
  __call = function() return ANY end,
  __newindex = function() end,
})
local handlers = {}
local ns = setmetatable({}, {__index = function(_, k)
  if k == "AddEventHandler" then
    return function(event, fn) handlers[event] = fn end
  end
  if type(k) == "string" and k:sub(1, 6) == "Create" then
    local kind = k:sub(7)
    return function(id, a, b)
      local t
      if type(a) == "table" and a ~= ANY then t = a
      elseif type(b) == "table" and b ~= ANY then t = b
      else t = {} end
      -- A header given a plain list uses that list as its children.
      if t.g == nil and t[1] ~= nil then
        local kids = {}
        for i, v in ipairs(t) do kids[i] = v end
        t = {g = kids}
      end
      t.__kind = kind
      t.__id = id
      if type(a) ~= "table" then t.__arg2 = a end
      return t
    end
  end
  return ANY
end})
local chunk = assert(load(src, "Zones.lua", "t", env))
chunk("AllTheThings", ns)
local categories = {}
for _, fn in pairs(handlers) do fn(categories) end
return categories
"""


def lua_list(table):
    """Lua array/table of numbers -> sorted Python list of ints."""
    if table is None:
        return None
    values = [int(v) for v in table.values() if isinstance(v, (int, float))]
    return sorted(set(values)) or None


def first_coord(coords):
    """ATT coords {[mapID] = {{x, y}, ...}} -> (mapID, x, y) of the first point."""
    if coords is None:
        return None
    for map_id in sorted(coords.keys()):
        points = coords[map_id]
        if points is None:
            continue
        for _, point in points.items():
            if point is not None and point[1] is not None and point[2] is not None:
                return int(map_id), round(float(point[1]), 1), round(float(point[2]), 1)
    return None


def number(value):
    if isinstance(value, (int, float)):
        return int(value)
    # lvl can be a {min, max} table
    if value is not None and hasattr(value, "values"):
        nums = [v for v in value.values() if isinstance(v, (int, float))]
        return int(nums[0]) if nums else None
    return None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    att_root = sys.argv[1]
    zones_path = os.path.join(att_root, "db", "Camelot", "Categories", "Zones.lua")
    with open(zones_path, encoding="utf-8-sig") as f:
        source = f.read()

    lua = LuaRuntime(unpack_returned_tuples=True)
    lua_type = lua.eval("type")
    categories = lua.execute(LOADER, source)

    quests = {}
    zones = {}  # zone mapID -> continent mapID (or 0)
    skipped = {"removed": 0, "unavailable": 0}

    def walk(node, continent, zone):
        if lua_type(node) != "table":
            return
        kind = node["__kind"]
        if kind == "Map":
            map_id = int(node["__id"])
            if node["isContinent"]:
                continent = map_id
            elif zone is None:
                zone = map_id
        if kind == "Quest":
            add_quest(node, continent, zone)
        children = node["g"]
        if children is not None and lua_type(children) == "table":
            for _, child in children.items():
                walk(child, continent, zone)

    def add_quest(node, continent, zone):
        qid = int(node["__id"])
        if node["u"] is not None:
            skipped["unavailable"] += 1
            return
        rwp, awp = number(node["rwp"]), number(node["awp"])
        if (rwp and rwp <= FOREVER_BUILD) or (awp and awp > FOREVER_BUILD):
            skipped["removed"] += 1
            return
        if qid in quests:
            return
        zone_id = zone or continent
        if zone_id is None:
            return
        zones.setdefault(zone_id, continent or 0)

        rec = {"z": zone_id}
        level = number(node["lvl"])
        if level and level > 1:
            rec["l"] = level
        coord = first_coord(node["coords"])
        if coord:
            rec["m"], rec["x"], rec["y"] = coord
        faction = number(node["r"])
        if faction in (1, 2):
            rec["f"] = faction  # 1 = Horde, 2 = Alliance
        for key, field in (("rc", "races"), ("cl", "c"), ("pre", "sourceQuests"),
                           ("alt", "altQuests"), ("nx", "nextQuests")):
            values = lua_list(node[field])
            if values:
                rec[key] = values
        needed = number(node["sqreq"])
        if needed:
            rec["prn"] = needed
        if node["isBreadcrumb"]:
            rec["bc"] = 1
        if node["repeatable"]:
            rec["rp"] = 1  # daily/weekly/repeatable: the game never marks it done
        for key, field in (("mr", "minReputation"), ("xr", "maxReputation")):
            rep = node[field]  # {factionID, standing}: 0 Neutral, 3000 Friendly, ... 42000 Exalted
            if rep is not None and lua_type(rep) == "table" and rep[1] is not None and rep[2] is not None:
                rec[key] = [int(rep[1]), int(rep[2])]
        skill = number(node["requireSkill"])
        if skill:
            rec["sk"] = skill
            skill_level = number(node["learnedAt"])
            if skill_level:
                rec["sl"] = skill_level
        rewards = []
        children = node["g"]
        if children is not None and lua_type(children) == "table":
            for _, child in children.items():
                if lua_type(child) != "table":
                    continue
                if child["__kind"] == "Item":
                    rewards.append(int(child["__id"]))
                elif child["__kind"] == "ItemSource" and isinstance(child["__arg2"], (int, float)):
                    rewards.append(int(child["__arg2"]))
        if rewards:
            rec["rw"] = rewards
        quests[qid] = rec

    walk(categories["Zones"], None, None)

    try:
        # "<short hash> (<commit date>)", so a release can be traced to its data.
        att_commit = subprocess.check_output(
            ["git", "-C", att_root, "log", "-1", "--format=%h (%cs)"], text=True).strip()
    except Exception:
        att_commit = "unknown"

    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Data"))
    out_path = os.path.join(out_dir, "Quests.lua")
    write_lua(out_path, quests, zones, att_commit)
    # Re-copy ATT's licence on every run, in case it changes.
    shutil.copyfile(os.path.join(att_root, "LICENSE"), os.path.join(out_dir, "AllTheThings-LICENSE.txt"))

    print(f"Wrote {len(quests)} quests in {len(zones)} zones to {out_path}")
    print(f"Repeatable: {sum(1 for q in quests.values() if q.get('rp'))}")
    print(f"Skipped: {skipped}")
    print(f"Size: {os.path.getsize(out_path) / 1024:.0f} KB (ATT commit {att_commit})")


def fmt(value):
    if isinstance(value, list):
        return "{" + ",".join(fmt(v) for v in value) + "}"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def write_lua(path, quests, zones, att_commit):
    key_order = ["z", "l", "m", "x", "y", "f", "rc", "cl", "pre", "prn", "alt", "nx", "bc", "rp", "sk", "sl", "mr", "xr", "rw"]
    lines = [
        "-- Generated by tools/extract_att.py. Do not edit by hand.",
        f"-- Source: AllTheThings WoW Forever data (db/Camelot), commit {att_commit}.",
        "-- AllTheThings is MIT-licensed; see Data/AllTheThings-LICENSE.txt.",
        "--",
        "-- Quest fields: z zone mapID, l min level, m/x/y quest start (mapID, x, y in %),",
        "-- f faction (1 Horde, 2 Alliance), rc race IDs, cl class IDs, pre prerequisites,",
        "-- prn how many prerequisites are needed (default all), alt alternative quests,",
        "-- nx quests a breadcrumb leads to, bc breadcrumb, rp repeatable, sk/sl profession skill line/level,",
        "-- mr/xr min/max reputation {factionID, standing} (0 Neutral, 3000 Friendly, 9000 Honored,",
        "-- 21000 Revered, 42000 Exalted), rw reward item IDs.",
        "local _, ns = ...",
        "ns.ZoneContinents = {",
    ]
    for zone_id in sorted(zones):
        lines.append(f"[{zone_id}]={zones[zone_id]},")
    lines.append("}")
    lines.append("ns.Quests = {")
    for qid in sorted(quests):
        rec = quests[qid]
        body = ",".join(f"{k}={fmt(rec[k])}" for k in key_order if k in rec)
        lines.append(f"[{qid}]={{{body}}},")
    lines.append("}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
