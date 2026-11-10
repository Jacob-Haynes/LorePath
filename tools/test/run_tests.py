"""Runs LorePath's Lua files against a fake WoW API and checks the core logic.

    pip install lupa
    python3 tools/test/run_tests.py
"""
import os
import sys

from lupa import LuaRuntime

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = ["Data/Quests.lua", "Data/QuestText.lua", "Data/CommunityText.lua", "Core.lua", "UI.lua", "Detail.lua", "Settings.lua", "Main.lua"]

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

done, total, *_ = ns.GetZoneProgress(1429)
elwynn_rp = len([qid for qid in ns.GetZoneQuests(1429).values() if ns.Quests[qid]["rp"]])
check(total == zone_quests - elwynn_rp and done >= 1, f"zone progress counts {done}/{total} (repeatables left out: {elwynn_rp})")

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
harness["ctrl"] = True
tiles[0]["__scripts"]["OnClick"](tiles[0])
harness["ctrl"] = False
check(harness["waypoint"] is not None, "Ctrl+clicking a quest tile sets a waypoint")
check(g.LorePathDetailFrame is None or not g.LorePathDetailFrame.IsShown(g.LorePathDetailFrame),
      "Ctrl+click doesn't open the detail panel")

check(sorted(ns.Quests[92818]["rw"].values()) == [251390, 251458], "recipe rewards (ATT r()) are kept: 92818 rewards both recipe items")

# --- Quest detail panel ---
same = lua.eval("function(a, b) return rawequal(a, b) end")
def detail_texts():
    panel = g.LorePathDetailFrame
    out = []
    for f in harness["all"].values():
        if f["__kind"] != "FontString" or not f.IsShown(f) or f["__text"] is None:
            continue
        p = f["__parent"]
        while p is not None and not same(p, panel):
            p = p["__parent"]
        if p is not None:
            out.append(str(f["__text"]))
    return out
def tile_for(qid):
    return [f for f in harness["all"].values() if f["questID"] == qid and f["sub"] is not None and f.IsShown(f)][0]
harness["waypoint"] = None
t0 = tile_for(rewarded[0]["questID"])
t0["__scripts"]["OnClick"](t0)
panel = g.LorePathDetailFrame
check(panel is not None and panel.IsShown(panel) and ns.detailQuest == t0["questID"], "clicking a quest opens the detail panel on it")
check(harness["waypoint"] is None, "a plain click no longer sets a waypoint")
texts = detail_texts()
check(any(("Q" + str(t0["questID"])) in s for s in texts), "the panel shows the quest's name")
check(any("Requires level" in s for s in texts) and any("Starts in" in s for s in texts), "the panel shows its level and where it starts")
items = [f for f in harness["all"].values() if f["itemID"] is not None and f.IsShown(f)]
check(len(items) == len(list(ns.Quests[t0["questID"]]["rw"].values())), f"each reward item is listed ({len(items)})")
check(not any("experience" in s or "Gold and XP" in s for s in texts), "gold and XP aren't shown in the panel")
t0 = tile_for(t0["questID"])
t0["__scripts"]["OnClick"](t0)
check(not panel.IsShown(panel) and ns.detailQuest is None, "clicking the same quest again closes the panel")

# In your log: gold, XP and reputation rewards are saved (not shown).
qid = t0["questID"]
char["log"][qid] = True
g.GetQuestLogRewardMoney = lua.eval("function(id) return 1250 end")
g.GetQuestLogRewardXP = lua.eval("function(id) return 1400 end")
g.GetNumQuestLogRewardFactions = lua.eval("function(id) return 1 end")
g.GetQuestLogRewardFactionInfo = lua.eval("function(i, id) return 72, 250 end")
g.C_QuestLog.SetSelectedQuest = lua.eval("function(id) end")
g.C_QuestLog.GetSelectedQuest = lua.eval("function() return 0 end")
g.GetQuestLogQuestText = lua.eval("function() return 'In-log text.', 'In-log objectives.' end")
ns.CaptureLogQuest(qid)
saved = g.LorePathDB["questCache"][qid]
check(saved["money"] == 1250 and saved["xp"] == 1400, "a quest in your log has its gold and XP saved")
check(saved["rep"] is not None and saved["rep"][1][1] == 72 and saved["rep"][1][2] == 250, "and its reputation rewards")
ns.ShowDetail(qid)
check(not any("experience" in s or "reputation with" in s for s in detail_texts()), "none of which the panel shows")
char["log"][qid] = None
g.LorePathDB["questCache"][qid] = None

# Text and rewards seen at a quest giver are kept for later.
g.GetQuestID = lua.eval(f"function() return {qid} end")
g.GetQuestText = lua.eval("function() return 'The Defias have taken the mine.' end")
g.GetObjectiveText = lua.eval("function() return 'Slay 10 Defias.' end")
g.GetRewardMoney = lua.eval("function() return 300 end")
g.GetRewardXP = lua.eval("function() return 900 end")
harness.Fire("QUEST_DETAIL")
check(g.LorePathDB["questCache"][qid]["xp"] == 900, "QUEST_DETAIL saves the quest's text and rewards")
texts = detail_texts()
check(any("Defias have taken the mine" in s for s in texts), "the panel then shows the saved description")

# Bundled quest text (pfQuest) fills gaps; what the game showed you wins.
check(ns.FillQuestText("Hello $N, $glad:lass;!$BBye $c") == "Hello adventurer, lad!\nBye warrior",
      "quest text placeholders are filled in: " + repr(ns.FillQuestText("Hello $N, $glad:lass;!$BBye $c")))
check(ns.QuestText[6] is not None and "Garrick Padfoot" in ns.QuestText[6]["o"], "quest 6 (Garrick Padfoot) has bundled text")
g.LorePathDB["questCache"][6] = None
ns.ShowDetail(6)
texts = detail_texts()
check(any("bounty" in s.lower() and "$N" not in s for s in texts), "a quest you haven't seen shows its bundled description, placeholders filled")
check(any("bundled quest database" in s for s in texts), "and says the text is from the bundled database")
g.LorePathDB["questCache"][6] = lua.table_from({"text": "What the game said."})
ns.RefreshDetail()
texts = detail_texts()
check(any("What the game said." in s for s in texts) and not any("Garrick has gathered" in s for s in texts),
      "text saved from the game replaces the bundled description")
char["completed"][6] = True
ns.RefreshCompleted()
ns.RefreshDetail()
texts = detail_texts()
check(any("What the game said." in s for s in texts), "a completed quest still shows its saved text")
char["completed"][6] = None
ns.RefreshCompleted()

# The turn-in screen's closing text is kept and shown.
g.GetQuestID = lua.eval("function() return 6 end")
g.GetRewardText = lua.eval("function() return 'Good work, $N. Here is your bounty.' end")
harness.Fire("QUEST_COMPLETE")
check(g.LorePathDB["questCache"][6]["done"] is not None, "QUEST_COMPLETE saves the quest's closing text")
texts = detail_texts()
check(any("Good work, adventurer" in s for s in texts), "the panel shows it under Completion")

# Accepting a quest saves its log text, so it's still there after you turn it in.
g.C_QuestLog.SetSelectedQuest = lua.eval("function(id) end")
g.C_QuestLog.GetSelectedQuest = lua.eval("function() return 0 end")
g.GetQuestLogQuestText = lua.eval("function() return 'Log description.', 'Log objectives.' end")
char["log"][783] = True
harness.Fire("QUEST_ACCEPTED", 783)
harness.RunTimers()
check(g.LorePathDB["questCache"][783]["text"] == "Log description.", "QUEST_ACCEPTED saves the quest log's text")
char["log"][783] = None

# A Forever-only quest you've done, with nothing saved, explains the gap.
forever_done = next(qid for qid in ns.Quests.keys() if qid >= 90000 and ns.QuestText[qid] is None and ns.IsEligible(qid))
char["completed"][forever_done] = True
ns.RefreshCompleted()
ns.ShowDetail(forever_done)
check(any("completed this before LorePath" in s for s in detail_texts()), "a done Forever quest with no text says why it's missing")
char["completed"][forever_done] = None
ns.RefreshCompleted()

# The quest link tooltip gives the goal and requirements, even for a completed Forever quest.
g.C_TooltipInfo = lua.eval("""{ GetHyperlink = function(link)
    if link == "quest:" .. FOREVER_ID then
        return { lines = { { leftText = "Harmony in Balance" }, { leftText = " " },
            { leftText = "Slay 8 Vuldren Juveniles in Thendal Grove" }, { leftText = " " },
            { leftText = "Requirements:" }, { leftText = " - 8 x Juvenile Vuldren" } } }
    end
end }""".replace("FOREVER_ID", str(forever_done)))
char["completed"][forever_done] = True
ns.RefreshCompleted()
ns.ShowDetail(forever_done)
texts = detail_texts()
check(any("Slay 8 Vuldren Juveniles" in s for s in texts) and any(s == "- 8 x Juvenile Vuldren" for s in texts),
      "a completed Forever quest shows its goal and requirements from the quest link tooltip")
check(not any("bundled quest database" in s for s in texts), "tooltip text is the game's own, not labelled as bundled")
char["completed"][forever_done] = None
ns.RefreshCompleted()
g.C_TooltipInfo = None

# Community text (Forever quests other players collected) fills gaps; your own saved text wins.
cid = next(k for k, v in ns.CommunityText.items() if v["d"] is not None and v["c"] is not None)
g.LorePathDB["questCache"][cid] = None
ns.ShowDetail(cid)
texts = detail_texts()
check(any(ns.FillQuestText(ns.CommunityText[cid]["d"])[:40] in s for s in texts), f"quest {cid} shows its community description")
check(any(ns.FillQuestText(ns.CommunityText[cid]["c"])[:30] in s for s in texts), "and its community completion text")
check(not any("bundled quest database" in s for s in texts), "community text isn't labelled as the bundled vanilla text")
g.LorePathDB["questCache"][cid] = lua.table_from({"text": "My own saved text."})
ns.RefreshDetail()
check(any("My own saved text." in s for s in detail_texts()), "your own saved text replaces community text")
g.LorePathDB["questCache"][cid] = None

# QUEST_PROGRESS keeps what the quest giver says mid-quest.
g.GetQuestID = lua.eval(f"function() return {cid} end")
g.GetProgressText = lua.eval("function() return 'Have you got them yet, $N?' end")
harness.Fire("QUEST_PROGRESS")
check(g.LorePathDB["questCache"][cid]["prog"] == "Have you got them yet, $N?", "QUEST_PROGRESS saves the progress text")
check(any("Have you got them yet, adventurer?" in s for s in detail_texts()), "the panel shows it under Progress")
g.LorePathDB["questCache"][cid] = None

# Saved text puts $N back in place of the character's name, so it can be shared.
g.UnitName = lua.eval("function() return 'Notah' end")
g.GetQuestID = lua.eval(f"function() return {cid} end")
g.GetQuestText = lua.eval("function() return 'Thank you, Notah. Notahville awaits.' end")
harness.Fire("QUEST_DETAIL")
check(g.LorePathDB["questCache"][cid]["text"] == "Thank you, $N. Notahville awaits.",
      "captured text stores $N instead of your name (whole words only): " + str(g.LorePathDB["questCache"][cid]["text"]))
g.LorePathDB["questCache"][cid] = None
g.UnitName = None

# Storyline links jump to the earlier quest and show it.
with_pre = next(i for i in [f["questID"] for f in harness["all"].values() if f["questID"] is not None and f["sub"] is not None and f.IsShown(f)]
                if ns.Quests[i]["pre"] is not None and ns.Quests[ns.Quests[i]["pre"][1]] is not None)
ns.ShowDetail(with_pre)
pre = ns.Quests[with_pre]["pre"][1]
links = [f for f in harness["all"].values() if f["questID"] == pre and f["sub"] is None and f.IsShown(f) and f["__scripts"]["OnClick"] is not None and f["text"] is not None and f["icon"] is None]
check(len(links) >= 1, "the panel lists the quest it comes after")
links[0]["__scripts"]["OnClick"](links[0])
check(ns.detailQuest == pre and ns.focusedQuest == pre, "clicking it shows that quest in the graph and the panel")
ns.HideDetail()

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
# Pooled rows keep .continent after turning into zone rows, so match headings only.
heading = [f for f in harness["all"].values() if f["continent"] == "Kalimdor" and f["zoneID"] is None and f.IsShown(f)][0]
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
# Level-locked tiles always show the level (it's why they're locked), so pick an open one.
tile = [f for f in harness["all"].values() if f["questID"] is not None and f.IsShown(f)
        and ns.GetStatus(f["questID"]) not in (S.LEVEL, S.MISSED)][0]
check("Lv" not in tile["sub"]["__text"], "turning off quest levels removes the level from tiles: " + tile["sub"]["__text"])
ns.SetSetting("showLevels", True)

harness["openedMap"] = None
ns.SetSetting("openMapOnWaypoint", False)
ns.ShowQuestStart(92706)
check(harness["openedMap"] is None and harness["waypoint"]["m"] == 1413, "with 'open the map' off, a waypoint is set without opening the map")
ns.SetSetting("openMapOnWaypoint", True)

# --- "First finish: X" jumps to the quest it's waiting on ---
blocked = None
for z in ns.GetZones().values():
    sls, _ = ns.BuildStorylines(z["id"])
    for st in sls.values():
        res = ns.GetNextStep(st)
        res = res if isinstance(res, tuple) else (res,)
        kind, nid, det = (res + (None, None, None))[:3]
        if kind == "blocked" and det is not None and ns.Quests[det] is not None:
            blocked = (z["id"], st, det)
            break
    if blocked:
        break
check(blocked is not None, "found a storyline waiting on a quest outside it")
if blocked:
    zone_id, st, det = blocked
    ns.FocusQuest(st["first"])
    key = "s" + str(st["first"])
    sec = [f for f in harness["all"].values() if f["key"] == key and f.IsShown(f)][0]
    check(sec["next"]["__text"] == "Show on map", "the header button is labelled 'Show on map'")
    step = sec["stepButton"]
    check(step["targetQuest"] == det, f"the step text targets the blocking quest {det}")
    step["__scripts"]["OnClick"](step)
    det_zone = ns.Quests[det]["z"]
    title = frame["zoneTitle"]["__text"]
    check(title == ns.GetMapName(det_zone), f"clicking it switches to the blocking quest's zone ({title})")
    shown = [f for f in harness["all"].values() if f["questID"] == det and f.IsShown(f) and f["flash"] is not None]
    check(len(shown) == 1 and shown[0]["flash"].IsShown(shown[0]["flash"]), "the blocking quest is shown and highlighted")
    harness.RunTimers()
    check(not shown[0]["flash"].IsShown(shown[0]["flash"]), "the highlight fades after a moment")

    # Back returns along the trail of jumps; picking a zone yourself clears it.
    back = frame["backButton"]
    start_zone = ns.Quests[st["first"]]["z"]
    check(back.IsShown(back), "a Back button appears after jumping")
    back["__scripts"]["OnClick"](back)
    check(frame["zoneTitle"]["__text"] == ns.GetMapName(start_zone), "Back returns to the zone you jumped from")
    while back.IsShown(back):
        back["__scripts"]["OnClick"](back)
    check(frame["zoneTitle"]["__text"] == "The Barrens", "Back again walks the trail back to where you started")
    step["__scripts"]["OnClick"](step)
    check(back.IsShown(back), "jumping again shows Back")
    row = [f for f in harness["all"].values() if f["zoneID"] == 1413 and f.IsShown(f)][0]
    row["__scripts"]["OnClick"](row)
    check(not back.IsShown(back), "choosing a zone in the list clears the Back trail")

    # The zone list scrolls to bring a far-away selected zone into view.
    ls = frame["listScroll"]
    ls["__vrange"], ls["__vs"] = 10000, 0
    rows = sorted([f for f in harness["all"].values() if f["zoneID"] is not None and f.IsShown(f)], key=lambda f: f["top"])
    far = rows[-1]
    far_quest = next(qid for qid, q in ns.Quests.items() if q["z"] == far["zoneID"] and ns.IsEligible(qid))
    ns.FocusQuest(far_quest)
    vs = ls["__vs"]
    far = [f for f in harness["all"].values() if f["zoneID"] == far["zoneID"] and f.IsShown(f)][0]
    check(vs > 0 and far["top"] >= vs and far["top"] + 20 <= vs + ls.GetHeight(ls),
          f"jumping to a zone low in the list scrolls it into view (row at {far['top']}, scrolled to {vs})")

# --- 1.0.0: WarcraftDB link, Reset to defaults, error safety ---
ns.ShowDetail(783)
box = g.LorePathDetailFrame["linkBox"]
check(box is not None and box["__text"] == "https://forever.warcraftdb.com/data/quest/783", "the panel shows the quest's WarcraftDB address to copy")
box["__scripts"]["OnTextChanged"](box, True)
check(box["__text"] == "https://forever.warcraftdb.com/data/quest/783", "typing in it can't change the address")
ns.HideDetail()

g.LorePathDB["collapsed"] = lua.table_from({"s7": True})
g.LorePathDB["collapsedContinents"] = lua.table_from({"Kalimdor": True})
g.LorePathDB["listHidden"] = True
g.LorePathDB["showLevels"] = False
g.LorePathDB["questCache"][42] = lua.table_from({"text": "keep me"})
ns.ResetToDefaults()
empty = lambda t: t is None or len(list(t.items())) == 0
check(empty(g.LorePathDB["collapsed"]) and empty(g.LorePathDB["collapsedContinents"]) and g.LorePathDB["listHidden"] is None,
      "Reset to defaults clears collapsed storylines, headings and the hidden zone list")
check(g.LorePathDB["showLevels"] is True and frame["listInset"].IsShown(frame["listInset"]), "and puts settings back, showing the zone list again")
check(g.LorePathDB["questCache"][42]["text"] == "keep me", "it keeps your saved quest text")
g.LorePathDB["questCache"][42] = None

real_capture = ns.CaptureQuestDetail
ns.CaptureQuestDetail = lua.eval("function() error('boom') end")
before_chat = len(list(harness["chat"].values()))
harness.Fire("QUEST_DETAIL")
ns.CaptureQuestDetail = real_capture
caught = list(harness["errors"].values())
check(len(caught) == 1 and "boom" in caught[0], "an error in one event is caught and reported, not thrown")
check(any("Something went wrong" in str(m) for m in list(harness["chat"].values())[before_chat:]), "and mentioned once in chat")
harness["errors"] = lua.table()
harness.Fire("QUEST_ACCEPTED", 783)
harness.RunTimers()
check(len(list(harness["errors"].values())) == 0, "other events keep working afterwards")

g.SlashCmdList["LOREPATH"]("config")
check(harness["openedSettings"] == 77, "/lp config opens the settings page")

# --- Reputation requirements ---
# 6031 (Timbermaw Hold, neutral, level 40) needs Friendly (3000) with faction 576.
char["level"], char["map"] = 60, 1414
rep = char["reputation"]
def fresh_status(qid):
    ns.RefreshPlayer()  # clears the cached standings, like a refresh after UPDATE_FACTION
    return ns.GetStatus(qid)
check(ns.Quests[6031]["mr"][1] == 576 and ns.Quests[6031]["mr"][2] == 3000, "extractor kept 6031's minReputation as mr={576,3000}")
check(fresh_status(6031) == S.AVAILABLE and ns.GetLockReason(6031) is None,
      "unknown faction standing doesn't lock or hide the quest")
check(ns.IsEligible(6031) and 6031 in list(ns.GetZoneQuests(1414).values()), "a reputation quest stays in its zone list")
rep[576] = 2999
check(fresh_status(6031) == S.LEVEL and ns.GetLockReason(6031) == "minrep", "below Friendly: 6031 is not yet available")
rep[576] = 3000
check(fresh_status(6031) == S.AVAILABLE, "exactly Friendly: 6031 is available")
rep[576] = 42000
check(fresh_status(6031) == S.AVAILABLE, "well above the minimum: still available")
check(ns.StandingName(-42000) == "Hated" and ns.StandingName(-1) == "Unfriendly" and ns.StandingName(0) == "Neutral"
      and ns.StandingName(9000) == "Honored" and ns.StandingName(20999) == "Honored" and ns.StandingName(42000) == "Exalted",
      "raw values map to standing names with WoW's thresholds")

# A quest with a maxReputation (none in the current Forever data, so give one to
# a plain Kalimdor quest for the test).
capped = next(qid for qid, q in sorted(ns.Quests.items()) if q["z"] == 1414 and not q["pre"] and not q["mr"]
              and not q["sk"] and not q["bc"] and ns.IsEligible(qid) and (q["l"] or 1) <= 60)
ns.Quests[capped]["xr"] = lua.eval("{609, 9000}")
rep[609] = 8999
ns.RefreshPlayer()
done0, total0, *_ = ns.GetZoneProgress(1414)
check(fresh_status(capped) == S.AVAILABLE, "below the maximum: available")
rep[609] = 9000
ns.RefreshPlayer()
done1, total1, *_ = ns.GetZoneProgress(1414)
check(ns.GetStatus(capped) == S.MISSED and ns.GetLockReason(capped) == "maxrep", "at the maximum (Honored): no longer available")
check(total1 == total0 - 1, f"a quest closed by reputation isn't counted as missing ({total0} -> {total1})")
char["completed"][capped] = True
ns.RefreshCompleted()
check(ns.GetStatus(capped) == S.DONE, "a quest done before your reputation went up still shows as done")
char["completed"][capped] = None
ns.RefreshCompleted()

# UI: the tile and tooltip explain the lock, without talking about levels.
rep[576] = 1500
g.SlashCmdList["LOREPATH"]("here")
harness.RunTimers()
def tile_for(qid):
    for f in harness["all"].values():
        if f["questID"] == qid and f.IsShown(f):
            return f
t = tile_for(6031)
sub = t and t["sub"]["__text"] or ""
check(t is not None and "Needs Friendly with Timbermaw Hold" in sub and "level" not in sub, f"rep-locked tile's second line: {sub!r}")
g.GameTooltip.lines = lua.table()
t["__scripts"]["OnEnter"](t)
lines = [str(l) for l in g.GameTooltip.lines.values()]
check("Requires Friendly with Timbermaw Hold" in lines and "Your reputation is too low" in lines
      and "Your level is too low" not in lines, "rep-locked tooltip: " + " | ".join(lines[:5]))
t = tile_for(capped)
sub = t and t["sub"]["__text"] or ""
check(t is not None and "Closed at Honored with Cenarion Circle" in sub, f"rep-closed tile's second line: {sub!r}")

# UPDATE_FACTION redraws with the new standing.
rep[576] = 3000
harness.Fire("UPDATE_FACTION")
check(len(list(harness["timers"].values())) > 0, "UPDATE_FACTION queues a refresh")
harness.RunTimers()
sub = tile_for(6031)["sub"]["__text"]
check("Needs" not in sub, f"after gaining Friendly the tile no longer shows the requirement: {sub!r}")

# Older clients: GetFactionInfoByID when C_Reputation is missing.
saved = g.C_Reputation
g.C_Reputation = None
g.GetFactionInfoByID = harness["LegacyGetFactionInfoByID"]
rep[576] = 100
check(fresh_status(6031) == S.LEVEL and ns.ReputationText(ns.Quests[6031]["mr"]) == "Friendly with Timbermaw Hold",
      "falls back to GetFactionInfoByID")
g.GetFactionInfoByID = None
check(fresh_status(6031) == S.AVAILABLE and ns.ReputationText(ns.Quests[6031]["mr"]) == "Friendly with faction 576",
      "with no reputation API at all, the quest stays available")
g.C_Reputation = saved
ns.Quests[capped]["xr"] = None


# --- Repeatable quests ---
check(len([q for q in ns.Quests.values() if q["rp"] == 1]) > 200, "the extractor keeps repeatable quests, flagged rp=1")
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
char["completed"], char["log"] = lua.table(), lua.table()
for k in list(rep.keys()):
    rep[k] = None
ns.RefreshPlayer()
ns.RefreshCompleted()
# A repeatable quest with no prerequisites or locks that a level-60 Human Warrior can take.
rp_id = next(qid for qid, q in sorted(ns.Quests.items()) if q["rp"] == 1 and not q["pre"] and not q["mr"] and not q["xr"]
             and not q["sk"] and ns.IsEligible(qid) and (q["l"] or 1) <= 60)
rp_zone = ns.Quests[rp_id]["z"]
check(ns.GetStatus(rp_id) == S.REPEATABLE, f"repeatable quest {rp_id} shows as REPEATABLE")
char["completed"][rp_id] = True
ns.RefreshCompleted()
check(ns.GetStatus(rp_id) == S.REPEATABLE, "a repeatable is never DONE, even if the client flags it completed")
char["log"][rp_id] = True
check(ns.GetStatus(rp_id) == S.ACTIVE, "a repeatable in your log shows as ACTIVE")
char["log"][rp_id] = None
char["completed"][rp_id] = None
ns.RefreshCompleted()
lowlevel = next(qid for qid, q in sorted(ns.Quests.items()) if q["rp"] == 1 and not q["pre"] and not q["mr"] and not q["xr"]
                and not q["sk"] and ns.IsEligible(qid) and (q["l"] or 1) > 1)
char["level"] = 1
ns.RefreshPlayer()
check(ns.GetStatus(lowlevel) == S.LEVEL, f"a repeatable too high for you ({lowlevel}, level {ns.Quests[lowlevel]['l']}) is level-locked")
char["level"] = 60
ns.RefreshPlayer()

# Progress: the repeatable counts neither way.
zq = list(ns.GetZoneQuests(rp_zone).values())
d0, t0, *_ = ns.GetZoneProgress(rp_zone)
non_rp = [qid for qid in zq if not ns.Quests[qid]["rp"] and ns.GetStatus(qid) != S.MISSED]
check(t0 == len(non_rp), f"zone progress total ({t0}) leaves out repeatables")
char["log"][rp_id] = True
d1, t1, *_ = ns.GetZoneProgress(rp_zone)
check((d1, t1) == (d0, t0), "picking up a repeatable doesn't change zone progress")
char["log"][rp_id] = None

# Chains continue past a repeatable prerequisite (91736 is repeatable, 91738 needs it).
check(ns.Quests[91736]["rp"] == 1 and 91736 in list(ns.Quests[91738]["pre"].values()), "91738 has repeatable prerequisite 91736")
check(ns.MissingPrereq(91738) is None, "a repeatable prerequisite counts as satisfied")
check(ns.GetStatus(91738) not in (S.BLOCKED,), f"91738 isn't blocked by its repeatable prerequisite ({ns.GetStatus(91738)})")

# GetNextStep skips repeatables unless nothing else is left; storyline x / y leaves them out.
fake = lua.eval("function(a, b) return { first = a, nodes = { { id = a, col = 0, row = 0 }, { id = b, col = 1, row = 0 } }, parents = { [b] = { a } } } end")
plain = next(qid for qid, q in sorted(ns.Quests.items()) if not q["rp"] and not q["pre"] and not q["mr"] and not q["sk"]
             and not q["bc"] and ns.IsEligible(qid) and (q["l"] or 1) <= 60 and qid != rp_id)
st = fake(rp_id, plain)
kind, nid = ns.GetNextStep(st)
check(kind == "available" and nid == plain, f"Next skips an available repeatable for a normal quest ({kind}, {nid})")
char["completed"][plain] = True
ns.RefreshCompleted()
check(ns.GetNextStep(st) == "complete", "a storyline whose only unfinished quest is repeatable is complete")
char["completed"][plain] = None
ns.RefreshCompleted()
kind, nid = ns.GetNextStep(fake(rp_id, lowlevel))
check(kind == "available" and nid == rp_id, "a storyline of only repeatables points Next at one")

# UI: blue box, "Repeatable" second line, tooltip; then the three toggles.
g.SlashCmdList["LOREPATH"]("here") if not frame.IsShown(frame) else None
ns.FocusQuest(rp_id)
t = tile_for(rp_id)
check(t is not None and "Repeatable" in t["sub"]["__text"], f"repeatable tile's second line: {t and t['sub']['__text']!r}")
g.GameTooltip.lines = lua.table()
t["__scripts"]["OnEnter"](t)
lines = [str(l) for l in g.GameTooltip.lines.values()]
check(any(l.startswith("Repeatable") for l in lines), "repeatable tooltip says so: " + " | ".join(lines[:4]))
def zone_rp_tiles():
    return len([f for f in harness["all"].values() if f["questID"] is not None and f.IsShown(f) and ns.Quests[f["questID"]]["rp"]])
def zone_tiles():
    return len([f for f in harness["all"].values() if f["questID"] is not None and f.IsShown(f)])
g.LorePathDB["collapsed"] = lua.table()
g.LorePathDB["hideCompleted"] = False
ns.Refresh()
shown_rp, shown_all = zone_rp_tiles(), zone_tiles()
check(shown_rp > 0, f"{shown_rp} repeatable tiles show in {ns.GetMapName(rp_zone)}")
def hidden_ok(how):
    sls, others = ns.BuildStorylines(rp_zone)
    ids = [n["id"] for s_ in sls.values() for n in s_["nodes"].values()] + list(others.values())
    check(g.LorePathDB["showRepeatable"] is False and zone_rp_tiles() == 0 and zone_tiles() == shown_all - shown_rp
          and not any(ns.Quests[i]["rp"] for i in ids),
          f"{how} hides repeatables from storylines and 'Other quests' ({shown_all} -> {zone_tiles()} tiles)")
    for s_ in sls.values():
        nodes = list(s_["nodes"].values())
        col_of = {n["id"]: n["col"] for n in nodes}
        if not all(col_of[p] < col_of[c] for c, ps in s_["parents"].items() if c in col_of for p in ps.values() if p in col_of):
            check(False, f"{how}: storyline {s_['first']} layout is broken")
def shown_ok(how):
    check(g.LorePathDB["showRepeatable"] is True and zone_rp_tiles() == shown_rp and zone_tiles() == shown_all,
          f"{how} shows them again")
box = frame["repeatToggle"]
panel_box = [f for f in harness["all"].values() if f["__template"] == "UICheckButtonTemplate" and f is not box
             and f["__checked"] is not None]
check(box.GetChecked(box) is True, "the header 'Repeatable' box starts ticked")
# 1. header tick box
box.SetChecked(box, False)
box["__scripts"]["OnClick"](box)
hidden_ok("unticking the header box")
check(any(f.GetChecked(f) is False for f in panel_box), "the settings page box follows the header box")
box.SetChecked(box, True)
box["__scripts"]["OnClick"](box)
shown_ok("ticking the header box")
# 2. /lp repeatable
g.SlashCmdList["LOREPATH"]("repeatable")
hidden_ok("/lp repeatable")
check(box.GetChecked(box) is False, "the header box follows /lp repeatable")
g.SlashCmdList["LOREPATH"]("repeatable")
shown_ok("/lp repeatable again")
check(box.GetChecked(box) is True, "and is ticked again")
# 3. settings page check box
cb = None
for f in harness["all"].values():
    if f["__template"] == "UICheckButtonTemplate" and f is not box and f["__scripts"]["OnClick"] is not None:
        f.SetChecked(f, False)
        f["__scripts"]["OnClick"](f)
        if g.LorePathDB["showRepeatable"] is False:
            cb = f
            break
        f.SetChecked(f, True)
        f["__scripts"]["OnClick"](f)
check(cb is not None, "the settings page has a 'Show repeatable quests' box")
if cb is not None:
    hidden_ok("unticking 'Show repeatable quests' in settings")
    check(box.GetChecked(box) is False, "the header box follows the settings page")
    cb.SetChecked(cb, True)
    cb["__scripts"]["OnClick"](cb)
    shown_ok("ticking it in settings")
check(ns.DEFAULTS["showRepeatable"] is True, "'Show repeatable quests' is on by default")

# A real storyline with a repeatable in it: the header's "x / y" leaves it out.
found = None
for z in ns.GetZones().values():
    for st in ns.BuildStorylines(z["id"])[0].values():
        ids = [n["id"] for n in st["nodes"].values()]
        if any(ns.Quests[i]["rp"] for i in ids) and not all(ns.Quests[i]["rp"] for i in ids):
            found = (st, ids)
            break
    if found:
        break
check(found is not None, "some storyline contains a repeatable quest")
if found:
    st, ids = found
    ns.FocusQuest(st["first"])
    sec = [f for f in harness["all"].values() if f["key"] == "s" + str(st["first"]) and f.IsShown(f)][0]
    expected = len([i for i in ids if not ns.Quests[i]["rp"] and ns.GetStatus(i) != S.MISSED])
    n_rp = len([i for i in ids if ns.Quests[i]["rp"]])
    check(f"/ {expected}|r" in sec["count"]["__text"] and f"+{n_rp} repeatable" in sec["count"]["__text"],
          f"storyline {st['first']} counts {expected} of its {len(ids)} quests, plus {n_rp} repeatable: {sec['count']['__text']!r}")
    # The zone list and the zone summary show the repeatables too, so a page of dailies doesn't look empty.
    zd, zt, zr = ns.GetZoneProgress(ns.Quests[st["first"]]["z"])
    zrow = [f for f in harness["all"].values() if f["zoneID"] == ns.Quests[st["first"]]["z"] and f.IsShown(f)][0]
    check(zr > 0 and f"+{zr}" in zrow["count"]["__text"], f"the zone list row shows +{zr} repeatable: {zrow['count']['__text']!r}")
    check(f"{zr} repeatable" in frame["zoneSummary"]["__text"], "the zone summary mentions the repeatables")
# --- Dungeons and raids (issue #2) ---
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
char["completed"], char["log"] = lua.table(), lua.table()
g.EJ_GetInstanceInfo = lua.eval("function(id) local n = { [63] = 'The Deadmines', [238] = 'The Stockade' }; return n[id] end")
ns.RefreshPlayer()
ns.RefreshCompleted()
IZ = ns.InstanceZones
check(IZ[291] == "dungeon" and IZ[225] == "dungeon" and IZ[248] == "raid",
      "the data marks the Deadmines and the Stockade as dungeons, Onyxia's Lair as a raid")
dm = list(ns.GetZoneQuests(291).values())
check(166 in dm and ns.Quests[166]["z"] == 291 and ns.IsEligible(166),
      f"The Defias Brotherhood (166) is on the Deadmines page and eligible for a Human ({len(dm)} Deadmines quests)")
check(ns.Quests[166]["m"] == 1436, "166 starts outside the instance, in Westfall (its quest giver), for 'Show on map'")
check(ns.GetStatus(166) == S.BLOCKED and ns.MissingPrereq(166) == 155,
      "an instance quest is blocked by its zone prerequisite (155 in Westfall)")
zones_by_id = {z["id"]: z for z in ns.GetZones().values()}
check(zones_by_id.get(291) is not None and zones_by_id[291]["instance"] == "dungeon"
      and zones_by_id.get(1429) is not None and zones_by_id[1429]["instance"] is None,
      "GetZones lists instance pages, tagged 'dungeon', next to outdoor zones")
done, total, *_ = ns.GetZoneProgress(291)
check(total == len(dm) and done == 0, f"GetZoneProgress works for an instance page ({done}/{total})")
check(ns.GetMapName(291) == "The Deadmines", "instance pages are named from the Encounter Journal")
check(ns.GetMapName(-318) == "Tier 0.5 Sets", "a header page uses its stored name")

ns.Refresh()
headings = {f["continent"]: f for f in harness["all"].values() if f["continent"] is not None and f.IsShown(f)}
check("Dungeons" in headings and "Raids" in headings, "the zone list has Dungeons and Raids headings")
check(headings["Dungeons"]["toggle"].IsShown(headings["Dungeons"]["toggle"])
      and headings["Dungeons"]["text"]["__text"] == "DUNGEONS", "the Dungeons heading is styled like a continent heading")
check(all(headings[c]["top"] < headings["Dungeons"]["top"] < headings["Raids"]["top"]
          for c in headings if c not in ("Dungeons", "Raids")), "Dungeons and Raids come after the continents")
def row_for(zone_id):
    rows = [f for f in harness["all"].values() if f["zoneID"] == zone_id and f.IsShown(f)]
    return rows[0] if rows else None
check(row_for(291) is not None and row_for(291)["top"] > headings["Dungeons"]["top"]
      and row_for(291)["top"] < headings["Raids"]["top"], "the Deadmines is listed under Dungeons")
headings["Dungeons"]["__scripts"]["OnClick"](headings["Dungeons"])
check(row_for(291) is None and row_for(1429) is not None, "collapsing Dungeons hides its instances, not the zones")

# Zone -> instance: Stormwind's storyline from 392 waits on 391 in the Stockade.
def step_for(first):
    sec = [f for f in harness["all"].values() if f["key"] == "s" + str(first) and f.IsShown(f)][0]
    return sec["stepButton"]
row_for(1453)["__scripts"]["OnClick"](row_for(1453))
g.LorePathDB["collapsed"] = lua.table()
ns.Refresh()
step = step_for(392)
check(step["targetQuest"] == 391 and ns.Quests[391]["z"] == 225, "Stormwind's 392 storyline says First finish: 391 (Stockade)")
step["__scripts"]["OnClick"](step)
check(frame["zoneTitle"]["__text"] == "The Stockade", "clicking it opens the Stockade page")
check(row_for(225) is not None and row_for(225)["selected"].IsShown(row_for(225)["selected"]),
      "the collapsed Dungeons heading opens to show the selected instance")
shown = [f for f in harness["all"].values() if f["questID"] == 391 and f.IsShown(f)]
check(len(shown) == 1 and shown[0]["flash"].IsShown(shown[0]["flash"]), "391 is shown and highlighted on the instance page")
back = frame["backButton"]
back["__scripts"]["OnClick"](back)
check(frame["zoneTitle"]["__text"] == ns.GetMapName(1453) and not back.IsShown(back), "Back returns to Stormwind")

# Instance -> zone: the Deadmines' 92753 storyline waits on 92752 in Stormwind.
ns.FocusQuest(92753)
check(frame["zoneTitle"]["__text"] == "The Deadmines", "jumping to a Deadmines quest opens the Deadmines page")
step = step_for(92753)
check(step["targetQuest"] == 92752 and ns.Quests[92752]["z"] == 1453, "its step points at 92752 in Stormwind")
step["__scripts"]["OnClick"](step)
check(frame["zoneTitle"]["__text"] == ns.GetMapName(1453), "clicking it goes back out to Stormwind")
back["__scripts"]["OnClick"](back)
check(frame["zoneTitle"]["__text"] == "The Deadmines", "Back returns to the Deadmines")
harness.RunTimers()

# Opening on the current zone: inside the Deadmines on a floor map LorePath doesn't know.
char["map"] = 292
g.IsInInstance = lua.eval("function() return true end")
g.EJ_GetInstanceForMap = lua.eval("function(m) if m == 292 then return 63 end return 0 end")
g.SlashCmdList["LOREPATH"]("here")
check(frame["zoneTitle"]["__text"] == "The Deadmines", "inside the Deadmines, /lp here opens its page")
check(ns.CurrentInstancePage(291) == 291, "standing on the instance's own map finds its page")
g.EJ_GetInstanceForMap = None
g.GetRealZoneText = lua.eval("function() return 'Stormwind Stockade' end")
C_Map = g.C_Map
C_Map.GetAreaInfo = lua.eval("function(id) if id == 717 then return 'Stormwind Stockade' end end")
check(ns.CurrentInstancePage(9999) == 225, "without the Encounter Journal, the instance is matched by its area name")
g.IsInInstance = lua.eval("function() return false end")
check(ns.CurrentInstancePage(9999) is None, "outside an instance, no instance page is picked")
char["map"] = 1429
g.SlashCmdList["LOREPATH"]("here")
check(frame["zoneTitle"]["__text"] == "Elwynn Forest", "back outside, /lp here opens the outdoor zone again")
g.IsInInstance, g.GetRealZoneText, C_Map.GetAreaInfo = None, None, None

unexpected = list(harness["errors"].values())
check(len(unexpected) == 0, "no errors were caught anywhere else in the run: " + " | ".join(unexpected)[:300])
print("chat:", list(harness["chat"].values())[-3:])
print()
print("FAILED:" if failures else "All checks passed.", *failures, sep="\n  ")
sys.exit(1 if failures else 0)
