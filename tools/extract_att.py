#!/usr/bin/env python3
"""Build LorePath's quest data from AllTheThings' WoW Forever database.

AllTheThings (https://github.com/ATTWoWAddon/AllTheThings) is MIT-licensed. Its
WoW Forever data lives in db/Camelot ("camelot" is the game type Forever uses).

This script loads ATT's zone and instance files inside a sandboxed Lua runtime (no os/io/load),
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
    map_icons = {}  # mapID -> ATT's icon (a texture file ID), for the zone list
    skipped = {"removed": 0, "unavailable": 0}

    def walk(node, continent, zone):
        if lua_type(node) != "table":
            return
        kind = node["__kind"]
        if kind == "Map":
            map_id = int(node["__id"])
            if isinstance(node["icon"], (int, float)):
                map_icons.setdefault(map_id, int(node["icon"]))
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
        givers = lua_list(node["qgs"]) or ([number(node["qg"])] if number(node["qg"]) else [])
        if givers:
            rec["qg"] = givers[0]  # the NPC who gives the quest (the first one ATT lists)
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
                elif child["__kind"] in ("Recipe", "Mount", "Toy") and number(child["itemID"]):
                    # r(spellID, {itemID=...}): the recipe (or mount/toy) item the quest gives you.
                    rewards.append(number(child["itemID"]))
        if rewards:
            rec["rw"] = rewards
        quests[qid] = rec

    walk(categories["Zones"], None, None)

    # Profession quests that live only in Professions.lua (issue #8).
    profession_added = extract_professions(att_root, lua, lua_type, add_quest, quests, zones)

    # Dungeons and raids (issue #2): see extract_instances below.
    instance_zones, instance_info = extract_instances(att_root, lua, lua_type, add_quest, quests)

    try:
        # "<short hash> (<commit date>)", so a release can be traced to its data.
        att_commit = subprocess.check_output(
            ["git", "-C", att_root, "log", "-1", "--format=%h (%cs)"], text=True).strip()
    except Exception:
        att_commit = "unknown"

    out_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Data"))
    out_path = os.path.join(out_dir, "Quests.lua")
    write_lua(out_path, quests, zones, att_commit)
    append_instance_tables(out_path, instance_zones, instance_info)
    # Icons for the zone list (issue #15): zones and continents that have quests.
    wanted = set(zones) | {c for c in zones.values() if c}
    zone_icons = {k: v for k, v in map_icons.items() if k in wanted}
    append_zone_icons(out_path, zone_icons)
    # Re-copy ATT's licence on every run, in case it changes.
    shutil.copyfile(os.path.join(att_root, "LICENSE"), os.path.join(out_dir, "AllTheThings-LICENSE.txt"))

    print(f"Wrote {len(quests)} quests in {len(zones)} zones to {out_path}")
    print(f"Profession quests: {sum(1 for q in quests.values() if q.get('sk'))} "
          f"({profession_added} from Professions.lua)")
    print(f"Repeatable: {sum(1 for q in quests.values() if q.get('rp'))}")
    print(f"Skipped: {skipped}")
    print(f"Instances: {len(instance_zones)} pages "
          f"({sum(1 for k in instance_zones.values() if k == 'raid')} raids), "
          f"{sum(1 for q in quests.values() if q['z'] in instance_zones)} quests")
    print(f"Zone icons: {len(zone_icons)} of {len(wanted)} zones and continents; "
          f"instance icons: {sum(1 for e in instance_info.values() if 'ic' in e)} of {len(instance_info)}")
    print(f"Size: {os.path.getsize(out_path) / 1024:.0f} KB (ATT commit {att_commit})")


# ============================================================================
# Profession quests (db/Camelot/Categories/Professions.lua)
# ============================================================================
#
# Most profession quests are in Zones.lua already. Professions.lua holds a few
# more (Blacksmithing and Leatherworking specialisations). They go on the page of
# the zone where they start, and keep their profession (requireSkill, which may
# be set on a header above them) and skill level (learnedAt).

def extract_professions(att_root, lua, lua_type, add_quest, quests, zones):
    path = os.path.join(att_root, "db", "Camelot", "Categories", "Professions.lua")
    with open(path, encoding="utf-8-sig") as f:
        root = lua.execute(LOADER, f.read())["Professions"]
    added = 0

    def visit(node, skill):
        nonlocal added
        if lua_type(node) != "table":
            return
        if node["__kind"] == "Profession":
            skill = number(node["__id"]) or skill
        own = number(node["requireSkill"])
        skill = own or skill
        if node["__kind"] == "Quest":
            qid = int(node["__id"])
            coord = first_coord(node["coords"])
            if qid in quests or not coord or coord[0] not in zones:
                return
            if own is None and skill:
                node["requireSkill"] = skill
            add_quest(node, zones[coord[0]], coord[0])
            if qid in quests:
                added += 1
            return
        kids = node["g"]
        if kids is not None and lua_type(kids) == "table":
            for _, child in kids.items():
                visit(child, skill)

    visit(root, None)
    return added


# ============================================================================
# Dungeons and raids (db/Camelot/Categories/Instances.lua)
# ============================================================================
#
# Instances.lua is a list of inst(journalInstanceID, {...}) nodes. Each instance
# gets its own page in LorePath, keyed by:
#   - the instance's own uiMapID (ATT's `mapID`, e.g. 291 for the Deadmines), or
#   - -journalInstanceID for WoW Forever's new instances, which ATT gives no mapID
#     (the game names them from the Encounter Journal or their area ID).
# A dungeon or a raid is decided by ATT's own `isRaid` flag on the inst() node.
# Quests under a top-level header instead of an instance (Tier 0.5 Sets, the
# Dungeon Set 2 chain that spans several dungeons) get one page keyed by -headerID.

# English names for the header pages (from ATT's LocalizationDB).
HEADER_NAMES = {-318: "Tier 0.5 Sets"}


def instance_maps(node, lua_type):
    """Every map ID an instance's own tree uses (its floors and wings)."""
    found = set()
    def visit(n):
        if lua_type(n) != "table":
            return
        if isinstance(n["mapID"], (int, float)):
            found.add(int(n["mapID"]))
        found.update(lua_list(n["maps"]) or [])
        if n["__kind"] != "Quest":
            kids = n["g"]
            if kids is not None and lua_type(kids) == "table":
                for _, child in kids.items():
                    visit(child)
    visit(node)
    return found


def outside_coord(coords, inside):
    """Like first_coord, but prefers a point outside the instance: many dungeon
    quests are given at the entrance or in town, which is where "Show on map"
    should point."""
    if coords is None:
        return None
    best = None
    for map_id in sorted(coords.keys()):
        points = coords[map_id]
        if points is None:
            continue
        for _, point in points.items():
            if point is not None and point[1] is not None and point[2] is not None:
                coord = int(map_id), round(float(point[1]), 1), round(float(point[2]), 1)
                if coord[0] not in inside:
                    return coord
                best = best or coord
                break
    return best


def extract_instances(att_root, lua, lua_type, add_quest, quests):
    """Adds every instance quest to `quests` (with the same filters as zone quests,
    via add_quest). Quests already found in Zones.lua keep their zone page.
    Returns ({pageKey: "dungeon"|"raid"}, {pageKey: {ej, ar, n}})."""
    path = os.path.join(att_root, "db", "Camelot", "Categories", "Instances.lua")
    with open(path, encoding="utf-8-sig") as f:
        root = lua.execute(LOADER, f.read())["Instances"]

    pages, info = {}, {}
    # Every instance's maps, for the header pages that span several instances.
    all_inside = set()
    for _, node in root["g"].items():
        if lua_type(node) == "table" and node["__kind"] == "Instance":
            all_inside |= instance_maps(node, lua_type)

    def collect(node, page, inside):
        """Walks one page's tree, adding its quests. Returns how many were added."""
        added = 0
        if lua_type(node) != "table":
            return 0
        if node["__kind"] == "Quest":
            qid = int(node["__id"])
            if qid not in quests:
                add_quest(node, None, page)
                if qid in quests:
                    rec = quests[qid]
                    rec.pop("m", None), rec.pop("x", None), rec.pop("y", None)
                    coord = outside_coord(node["coords"], inside)
                    if coord:
                        rec["m"], rec["x"], rec["y"] = coord
                    elif node["qgs"] is not None or node["qg"] is not None or node["providers"] is not None:
                        # ATT maps no points inside instances, so a quest whose
                        # giver (an NPC, item or object) is listed but has no point
                        # outside was picked up inside. With no giver listed at
                        # all, ATT just doesn't say (some are handed out in town),
                        # so those aren't marked.
                        rec["di"] = 1
                    added += 1
            return added  # quests inside a quest's g are objectives/rewards, not quests
        kids = node["g"]
        if kids is not None and lua_type(kids) == "table":
            for _, child in kids.items():
                added += collect(child, page, inside)
        return added

    for _, node in root["g"].items():
        if lua_type(node) != "table":
            continue
        kind = node["__kind"]
        node_id = int(node["__id"])
        if kind == "Instance":
            if node["u"] is not None:
                continue
            awp = number(node["awp"])
            if awp and awp > FOREVER_BUILD:
                continue
            map_id = node["mapID"]
            page = int(map_id) if isinstance(map_id, (int, float)) else -node_id
            entry = {"ej": node_id}
            if isinstance(node["icon"], (int, float)):
                entry["ic"] = int(node["icon"])
            area = number(node["zoneTextAreaID"]) or (lua_list(node["zoneTextAreaIDs"]) or [None])[0]
            if area:
                entry["ar"] = area
            inside = instance_maps(node, lua_type) | {page}
            page_kind = "raid" if node["isRaid"] else "dungeon"
        else:
            page = node_id  # a negative header ID
            entry = {"n": HEADER_NAMES.get(node_id, f"Header {node_id}")}
            inside = all_inside
            page_kind = "dungeon"
        if collect(node, page, inside) > 0:
            pages[page] = page_kind
            info[page] = entry
    # Header pages (Tier 0.5 Sets) gather chains given in towns too, so a missing
    # start point there doesn't mean the quest was picked up inside.
    for rec in quests.values():
        if rec.get("di") and "n" in info.get(rec["z"], {}):
            del rec["di"]
    return pages, info


def append_instance_tables(path, pages, info):
    """Writes ns.InstanceZones and ns.InstanceInfo at the end of Data/Quests.lua."""
    lines = [
        "-- Instance pages: \"dungeon\" or \"raid\" (from ATT's isRaid). Keys are the instance's",
        "-- uiMapID, or -journalInstanceID when ATT has no map, or -headerID for a header page.",
        "ns.InstanceZones = {",
    ]
    lines += [f'[{k}]="{pages[k]}",' for k in sorted(pages)]
    lines.append("}")
    lines.append("-- ej Encounter Journal instance ID, ar area ID (for the name), n English name, ic icon file ID.")
    lines.append("ns.InstanceInfo = {")
    for k in sorted(info):
        e = info[k]
        body = ",".join(f'{f}="{e[f]}"' if f == "n" else f"{f}={e[f]}" for f in ("ej", "ar", "n", "ic") if f in e)
        lines.append(f"[{k}]={{{body}}},")
    lines.append("}")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def append_zone_icons(path, icons):
    """Writes ns.ZoneIcons (mapID -> texture file ID, from ATT) at the end of Data/Quests.lua."""
    lines = ["-- Zone list icons: mapID -> texture file ID (ATT's map icons).", "ns.ZoneIcons = {"]
    lines += [f"[{k}]={icons[k]}," for k in sorted(icons)]
    lines.append("}")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def fmt(value):
    if isinstance(value, list):
        return "{" + ",".join(fmt(v) for v in value) + "}"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def write_lua(path, quests, zones, att_commit):
    key_order = ["z", "l", "m", "x", "y", "qg", "f", "rc", "cl", "pre", "prn", "alt", "nx", "bc", "rp", "sk", "sl", "mr", "xr", "rw", "di"]
    lines = [
        "-- Generated by tools/extract_att.py. Do not edit by hand.",
        f"-- Source: AllTheThings WoW Forever data (db/Camelot), commit {att_commit}.",
        "-- AllTheThings is MIT-licensed; see Data/AllTheThings-LICENSE.txt.",
        "--",
        "-- Quest fields: z zone mapID, l min level, m/x/y quest start (mapID, x, y in %), qg quest giver NPC ID,",
        "-- f faction (1 Horde, 2 Alliance), rc race IDs, cl class IDs, pre prerequisites,",
        "-- prn how many prerequisites are needed (default all), alt alternative quests,",
        "-- nx quests a breadcrumb leads to, bc breadcrumb, rp repeatable, sk/sl profession skill line/level,",
        "-- mr/xr min/max reputation {factionID, standing} (0 Neutral, 3000 Friendly, 9000 Honored,",
        "-- 21000 Revered, 42000 Exalted), rw reward item IDs, di picked up inside a dungeon or raid.",
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
