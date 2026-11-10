"""Runs LorePath's Lua files against a fake WoW API and checks the core logic.

    pip install lupa
    python3 tools/test/run_tests.py
"""
import os
import sys

from lupa import LuaRuntime

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = ["Data/Quests.lua", "Core.lua", "UI.lua", "Settings.lua", "Main.lua"]

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute("unpack = table.unpack")  # WoW runs Lua 5.1, which has a global unpack
harness = lua.execute(open(os.path.join(ROOT, "tools/test/harness.lua")).read())
ns = lua.table()
load_file = lua.eval("function(src, name, ns) return assert(load(src, '@' .. name))('LorePath', ns) end")
for path in FILES:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        load_file(f.read(), path, ns)

failures = []
def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)

g = lua.globals()
char = harness["char"]

# Load like the game does: saved variables are empty on first run, then the events fire.
harness.Fire("ADDON_LOADED", "LorePath")
harness.Fire("PLAYER_LOGIN")
check(g.LorePathDB["showMinimapButton"] is True and g.LorePathDB["scale"] == 1.0, "first load fills in default settings")
check(harness["registeredCategory"] is not None and harness["settingsCategory"]["name"] == "LorePath",
      "settings page is registered under Options > AddOns as 'LorePath'")
minimap_button = harness["frames"]["LorePathMinimapButton"]
check(minimap_button is not None and minimap_button.IsShown(minimap_button), "minimap button is created and shown")

# --- Eligibility: Human Warrior Alliance ---
ns.RefreshPlayer()
ns.RefreshCompleted()
check(ns.IsEligible(783), "Alliance quest 783 (A Threat Within) is eligible for a Human")
horde = [qid for qid, q in ns.Quests.items() if q["f"] == 1]
check(horde and not ns.IsEligible(horde[0]), "a Horde-only quest is not eligible for an Alliance character")

# --- Status ---
S = ns.STATUS
check(ns.GetStatus(783) == S.AVAILABLE, "783 is available with nothing done")
check(ns.GetStatus(33) == S.BLOCKED, "33 (needs 5261) is blocked at the start")
char["completed"][5261] = True
ns.RefreshCompleted()
check(ns.GetStatus(33) == S.AVAILABLE, "33 becomes available once 5261 is done")
char["log"][33] = True
check(ns.GetStatus(33) == S.ACTIVE, "33 shows as active while in the log")
char["log"][33] = None
char["completed"][33] = True
ns.RefreshCompleted()
check(ns.GetStatus(33) == S.DONE, "33 shows as done once turned in")

# Level lock: find an Alliance-eligible quest with no prereqs and min level 20+ in Elwynn's neighbours
high = None
for qid, q in ns.Quests.items():
    if q["l"] and q["l"] >= 20 and not q["pre"] and ns.IsEligible(qid):
        high = qid
        break
check(high is not None and ns.GetStatus(high) == S.LEVEL, f"a level-{ns.Quests[high]['l']} quest is level-locked at level 10")

# --- Storylines in Elwynn Forest ---
storylines, others = ns.BuildStorylines(1429)
n_story = len(list(storylines.values()))
n_other = len(list(others.values()))
total_nodes = sum(len(list(s["nodes"].values())) for s in storylines.values())
zone_quests = len(list(ns.GetZoneQuests(1429).values()))
print(f"Elwynn: {zone_quests} quests for a Human Warrior -> {n_story} storylines ({total_nodes} quests) + {n_other} other")
check(total_nodes + n_other == zone_quests, "every zone quest lands in exactly one storyline or 'other'")
check(n_story >= 3, "Elwynn has several storylines")
for s in list(storylines.values())[:5]:
    nodes = list(s["nodes"].values())
    kind = ns.GetNextStep(s)
    print(f"  storyline from {s['first']}: {len(nodes)} quests, {s['cols']} columns x {s['rows']} rows, next step: {kind}")
    # parents always to the left
    col_of = {n["id"]: n["col"] for n in nodes}
    ok = all(col_of[p] < col_of[c] for c, ps in s["parents"].items() if c in col_of for p in ps.values() if p in col_of)
    check(ok, f"  storyline {s['first']}: every prerequisite sits in an earlier column")

done, total = ns.GetZoneProgress(1429)
check(total == zone_quests and done >= 1, f"zone progress counts {done}/{total}")

# --- Waypoint ---
ns.ShowQuestStart(783)
wp = harness["waypoint"]
check(wp is not None and wp["m"] == 1429 and abs(wp["x"] - 0.481) < 1e-6, "waypoint set at 783's start (Elwynn 48.1, 42.9)")
check(harness["superTracked"] is True and harness["openedMap"] == 1429, "waypoint is super-tracked and the map opens on Elwynn")

# --- UI: open the window and render, with the mock frame API ---
g.SlashCmdList["LOREPATH"]("")
frame = harness["frames"]["LorePathFrame"]
check(frame is not None and frame.IsShown(frame), "/lp opens the window")
title = frame["zoneTitle"]["__text"]
check(title is not None and title.startswith("Elwynn Forest"), f"opens on the current zone: {title!r}")
g.SlashCmdList["LOREPATH"]("")
check(not frame.IsShown(frame), "/lp again closes it")
g.SlashCmdList["LOREPATH"]("here")
harness.RunTimers()
check(frame.IsShown(frame), "/lp here reopens it")

# Hover every rendered quest tile (builds its tooltip) and click one (waypoint)
tiles = [f for f in harness["all"].values() if f["questID"] is not None and f.IsShown(f)]
errors = 0
for tile in tiles:
    g.GameTooltip.lines = lua.table()
    try:
        tile["__scripts"]["OnEnter"](tile)
    except Exception as e:
        errors += 1
        print("tooltip error:", e)
# One tile per Elwynn quest the character can see (derived from the data, so ATT syncs don't break it).
check(zone_quests > 0 and len(tiles) == zone_quests and errors == 0,
      f"all {len(tiles)} Elwynn quest tiles (of {zone_quests} zone quests) build a tooltip without errors")
rewarded = [t for t in tiles if ns.Quests[t["questID"]]["rw"] is not None]
g.GameTooltip.lines = lua.table()
rewarded[0]["__scripts"]["OnEnter"](rewarded[0])
lines = list(g.GameTooltip.lines.values())
check(any("Rewards" in str(l) for l in lines), "a quest with rewards lists them in its tooltip: " + " | ".join(str(l) for l in lines[:8]))
harness["waypoint"] = None
tiles[0]["__scripts"]["OnClick"](tiles[0])
check(harness["waypoint"] is not None, "clicking a quest tile sets a waypoint")

# Horde character in The Barrens
char["race"], char["class"], char["faction"], char["level"], char["map"] = 2, 1, "Horde", 15, 1413
char["completed"] = lua.table()
g.SlashCmdList["LOREPATH"]("here")
harness.RunTimers()
title = frame["zoneTitle"]["__text"]
check(title is not None and title.startswith("The Barrens"), f"Horde character opens on The Barrens: {title!r}")
check(not ns.IsEligible(783), "Alliance quest 783 is no longer eligible for an orc")
check(ns.IsEligible(92706), "Forever quest 92706 (neutral) is eligible for an orc")
storylines, others = ns.BuildStorylines(1413)
barrens_others = len(list(others.values()))
print(f"Barrens for an Orc Warrior: {len(list(storylines.values()))} storylines + {barrens_others} other")
check(barrens_others > 0, "the Barrens has standalone ('other') quests for an orc")
# --- Minimap button ---
frame.Hide(frame)
minimap_button["__scripts"]["OnClick"](minimap_button, "LeftButton")
check(frame.IsShown(frame), "left-clicking the minimap button opens the window")
minimap_button["__scripts"]["OnClick"](minimap_button, "LeftButton")
check(not frame.IsShown(frame), "left-clicking again closes it")
frame.Show(frame)
harness["openedSettings"] = None
minimap_button["__scripts"]["OnClick"](minimap_button, "RightButton")
check(harness["openedSettings"] == 77, "right-clicking the minimap button opens LorePath's settings page")
check(not frame.IsShown(frame), "opening settings closes the window so it doesn't cover the page")
g.LorePath_OnAddonCompartmentClick("LorePath", "LeftButton")
check(frame.IsShown(frame), "the addon compartment entry opens the window")

# --- Settings take effect ---
ns.SetSetting("scale", 1.2)
check(frame["__scale"] == 1.2, "window size setting rescales the window")
ns.SetSetting("showMinimapButton", False)
check(not minimap_button.IsShown(minimap_button), "turning off the minimap button hides it")
ns.SetSetting("showMinimapButton", True)
check(minimap_button.IsShown(minimap_button), "turning it back on shows it")

# Count the tiles shown in The Barrens with standalone quests on and off.
def shown_tiles():
    return len([f for f in harness["all"].values() if f["questID"] is not None and f.IsShown(f)])
with_others = shown_tiles()
ns.SetSetting("showOthers", False)
without_others = shown_tiles()
check(without_others == with_others - barrens_others,
      f"hiding standalone quests drops the {barrens_others} 'other' tiles ({with_others} -> {without_others})")
ns.SetSetting("showOthers", True)

# Finish a whole storyline: it collapses by default, and can be reopened.
storylines, _ = ns.BuildStorylines(1413)
first = list(storylines.values())[0]
first_n = len(list(first["nodes"].values()))
for n in first["nodes"].values():
    char["completed"][n["id"]] = True
ns.Refresh()
check(shown_tiles() == with_others - first_n, f"a finished storyline starts collapsed ({with_others} -> {shown_tiles()} tiles)")
def section(key):
    for f in harness["all"].values():
        if f["key"] == key and f.IsShown(f):
            return f
key = "s" + str(first["first"])
sec = section(key)
check(sec is not None and sec["collapsed"] is True, "its header shows as collapsed")
sec["__scripts"]["OnClick"](sec)
check(shown_tiles() == with_others, "clicking the header expands it again")
sec = section(key)
sec["__scripts"]["OnClick"](sec)
check(shown_tiles() == with_others - first_n, "clicking again collapses it, and the choice is saved")
check(g.LorePathDB["collapsed"][key] is True, "collapsed state is stored in LorePathDB")
other = section("s" + str(list(storylines.values())[1]["first"]))
other["__scripts"]["OnClick"](other)
second_n = len(list(list(storylines.values())[1]["nodes"].values()))
check(shown_tiles() == with_others - first_n - second_n, "an unfinished storyline can be collapsed too")
g.LorePathDB["collapsed"] = lua.table()
ns.Refresh()
ns.SetSetting("hideCompleted", True)
check(section(key) is None and shown_tiles() == with_others - first_n, "'Hide finished storylines' removes the finished one entirely")
ns.SetSetting("hideCompleted", False)

# Zone list: continents collapse, and the whole list can be hidden.
def zone_rows():
    return [f for f in harness["all"].values() if f["zoneID"] is not None and f.IsShown(f)]
heading = [f for f in harness["all"].values() if f["continent"] == "Kalimdor" and f.IsShown(f)][0]
before = len(zone_rows())
heading["__scripts"]["OnClick"](heading)
after = len(zone_rows())
check(after < before, f"collapsing Kalimdor hides its zones ({before} -> {after})")
heading["__scripts"]["OnClick"](heading)
check(len(zone_rows()) == before, "expanding it shows them again")
frame["listToggle"]["__scripts"]["OnClick"](frame["listToggle"])
check(not frame["listInset"].IsShown(frame["listInset"]) and g.LorePathDB["listHidden"] is True, "the list toggle hides the zone list")
frame["listToggle"]["__scripts"]["OnClick"](frame["listToggle"])
check(frame["listInset"].IsShown(frame["listInset"]), "and shows it again")

ns.SetSetting("showLevels", False)
tile = [f for f in harness["all"].values() if f["questID"] is not None and f.IsShown(f)][0]
check("Lv" not in tile["sub"]["__text"], "turning off quest levels removes the level from tiles: " + tile["sub"]["__text"])
ns.SetSetting("showLevels", True)

harness["openedMap"] = None
ns.SetSetting("openMapOnWaypoint", False)
ns.ShowQuestStart(92706)
check(harness["openedMap"] is None and harness["waypoint"]["m"] == 1413, "with 'open the map' off, a waypoint is set without opening the map")
ns.SetSetting("openMapOnWaypoint", True)

g.SlashCmdList["LOREPATH"]("config")
check(harness["openedSettings"] == 77, "/lp config opens the settings page")

print("chat:", list(harness["chat"].values())[-3:])
print()
print("FAILED:" if failures else "All checks passed.", *failures, sep="\n  ")
sys.exit(1 if failures else 0)
