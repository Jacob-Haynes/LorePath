"""Runs LorePath's Lua files against a fake WoW API and checks the core logic.

    pip install lupa
    python3 tools/test/run_tests.py
"""
import os
import sys

from lupa import LuaRuntime

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = ["Data/Quests.lua", "Data/QuestText.lua", "Data/CommunityText.lua", "Core.lua", "UI.lua", "Detail.lua", "QuestLog.lua", "Share.lua", "Settings.lua", "Main.lua"]

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

# Hover every rendered quest tile (builds its tooltip) and Ctrl+click one (waypoint)
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

# The quest text tests below read quests you haven't started, so show spoilers for them.
ns.SetSetting("showSpoilers", True)

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

# --- No spoilers: not started = "Find what awaits you", in your log = no ending, done = everything ---
ns.SetSetting("showSpoilers", False)
g.LorePathDB["questCache"][6] = lua.table_from({"done": "Garrick is dead. The end."})
char["completed"][6] = None
char["log"][6] = None
ns.RefreshCompleted()
ns.ShowDetail(6)
texts = detail_texts()
reveal = g.LorePathDetailFrame["revealButton"]
check(any(s == "Find what awaits you." for s in texts) and not any("Garrick has gathered" in s for s in texts),
      "a quest you haven't started shows 'Find what awaits you.' instead of its story")
check(reveal.IsShown(reveal) and not any("The end." in s for s in texts), "with a Reveal button, and no ending")
reveal["__scripts"]["OnClick"](reveal)
texts = detail_texts()
check(any("Garrick has gathered" in s for s in texts) and any("The end." in s for s in texts) and not reveal.IsShown(reveal),
      "Reveal shows its description and ending")
ns.ShowDetail(783)
ns.ShowDetail(6)
check(any(s == "Find what awaits you." for s in detail_texts()), "revealing lasts only until you look at another quest")

char["log"][6] = True
ns.RefreshDetail()
texts = detail_texts()
check(not any(s == "Find what awaits you." for s in texts) and any(s in ("Description", "Objectives") for s in texts)
      and not any("The end." in s for s in texts) and any("Find out when you turn it in." in s for s in texts),
      "a quest in your log shows its objectives and description but not how it ends")
char["log"][6] = None
char["completed"][6] = True
ns.RefreshCompleted()
ns.RefreshDetail()
texts = detail_texts()
check(any("Garrick has gathered" in s for s in texts) and any("The end." in s for s in texts) and not reveal.IsShown(reveal),
      "a completed quest shows everything")
char["completed"][6] = None
ns.RefreshCompleted()

g.SlashCmdList["LOREPATH"]("spoilers")
check(g.LorePathDB["showSpoilers"] is True, "/lp spoilers turns spoilers on")
ns.RefreshDetail()
check(any("Garrick has gathered" in s for s in detail_texts()), "with spoilers on, quests you haven't started show their story")
g.SlashCmdList["LOREPATH"]("spoilers")
check(g.LorePathDB["showSpoilers"] is False, "and /lp spoilers again hides them")
g.LorePathDB["questCache"][6] = None
ns.HideDetail()

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

# --- Open in quest log (issue #19) ---
log_button = g.LorePathDetailFrame["logButton"]
check(log_button is not None and not log_button.IsShown(log_button), "a quest you're not on has no 'Open in quest log' button")
check(ns.OpenInQuestLog(783) is False, "OpenInQuestLog refuses a quest that isn't in your log")
char["log"][783] = True
ns.RefreshDetail()
check(log_button.IsShown(log_button), "a quest in your log shows 'Open in quest log' in its details")
# Recorders are Lua functions: LorePath checks type(fn) == "function", which Python callables fail.
rec = lua.eval("""function()
    local r = { opened = {}, selected = {}, toggled = 0 }
    r.open = function(id) table.insert(r.opened, id) end
    r.select = function(id) table.insert(r.selected, id) end
    r.toggle = function() r.toggled = r.toggled + 1 end
    return r
end""")
def opened():
    return list(r["opened"].values())
r = rec()
g.QuestMapFrame_OpenToQuestDetails = r["open"]
log_button["__scripts"]["OnClick"](log_button)
check(opened() == [783], f"the button opens the modern quest log at that quest ({opened()})")
g.QuestMapFrame_OpenToQuestDetails = None
g.C_QuestLog.SetSelectedQuest = r["select"]
g.ToggleQuestLog = r["toggle"]
check(ns.OpenInQuestLog(783) is True and list(r["selected"].values()) == [783] and r["toggled"] == 1,
      "without the modern quest log, it selects the quest and opens the log")
g.ToggleQuestLog = None
check(ns.OpenInQuestLog(783) is False, "with no quest log function at all, it says so instead of erroring")
r = rec()
g.QuestMapFrame_OpenToQuestDetails = r["open"]
g.InCombatLockdown = lua.eval("function() return true end")
check(ns.OpenInQuestLog(783) is False and opened() == [], "it doesn't try to open the quest log in combat")
g.InCombatLockdown = lua.eval("function() return false end")
char["log"][783] = None
ns.HideDetail()

# Shift+click a quest tile: opens the quest log if you're on it, else acts like a plain click.
tile = [f for f in harness["all"].values() if f["questID"] is not None and f["sub"] is not None and f.IsShown(f)][0]
tid = tile["questID"]
char["log"][tid] = True
g.GameTooltip.lines = lua.table()
tile["__scripts"]["OnEnter"](tile)
check(any("Shift+click to open it in your quest log" in str(l) for l in g.GameTooltip.lines.values()),
      "a quest in your log mentions Shift+click in its tooltip")
harness["shift"] = True
tile["__scripts"]["OnClick"](tile)
check(opened() == [tid] and not g.LorePathDetailFrame.IsShown(g.LorePathDetailFrame),
      "Shift+clicking a quest you're on opens the quest log, not the details")
char["log"][tid] = None
tile["__scripts"]["OnClick"](tile)
harness["shift"] = False
check(opened() == [tid] and g.LorePathDetailFrame.IsShown(g.LorePathDetailFrame) and ns.detailQuest == tid,
      "Shift+clicking a quest you're not on opens its details as usual")
g.QuestMapFrame_OpenToQuestDetails = None
ns.HideDetail()

# --- The other way: from the game's quest log to LorePath ---
check(ns.questLogButton is None, "with no quest log frame loaded, no LorePath button is made")
details = harness.MockObject("Frame")
g.QuestMapFrame = lua.table_from({"DetailsFrame": details})
harness.Fire("ADDON_LOADED", "Blizzard_WorldMap")
qlb = ns.questLogButton
check(qlb is not None and same(qlb["__parent"], details), "once the quest log loads, it gets a LorePath button")
harness.Fire("ADDON_LOADED", "SomethingElse")
check(same(ns.questLogButton, qlb), "and only one")
g.C_QuestLog.GetSelectedQuest = lua.eval(f"function() return {tid} end")
check(ns.SelectedLogQuest() == tid, "the selected quest log quest is read with C_QuestLog.GetSelectedQuest")
frame.Hide(frame)
qlb["__scripts"]["OnClick"](qlb)
check(frame.IsShown(frame) and ns.focusedQuest == tid and ns.detailQuest == tid
      and g.LorePathDetailFrame.IsShown(g.LorePathDetailFrame),
      "the button opens LorePath on that quest, with its details")
g.GameTooltip.lines = lua.table()
qlb["__scripts"]["OnEnter"](qlb)
check(any("Show in LorePath" in str(l) for l in g.GameTooltip.lines.values()), "the button has a tooltip")
ns.HideDetail()
g.C_QuestLog.GetSelectedQuest = lua.eval("function() return 0 end")
g.GetQuestLogSelection = lua.eval("function() return 3 end")
g.C_QuestLog.GetInfo = lua.eval(f"function(i) if i == 3 then return {{ questID = {tid} }} end end")
check(ns.SelectedLogQuest() == tid, "a classic quest log's selection (a log index) works too")
g.GetQuestLogSelection = None
g.C_QuestLog.GetInfo = None
check(ns.SelectedLogQuest() is None and ns.ShowInLorePath(None) is False, "with nothing selected, it says so")
check(ns.ShowInLorePath(999999) is False, "a quest LorePath doesn't have isn't opened")
g.SlashCmdList["LOREPATH"](f"quest {tid}")
check(ns.detailQuest == tid, f"/lp quest {tid} opens that quest")
ns.HideDetail()
g.C_QuestLog.GetSelectedQuest = lua.eval(f"function() return {tid} end")
g.SlashCmdList["LOREPATH"]("quest")
check(ns.detailQuest == tid, "/lp quest opens the quest selected in your quest log")
g.C_QuestLog.GetSelectedQuest = lua.eval("function() return 0 end")
g.QuestMapFrame = None
ns.HideDetail()
harness.RunTimers()

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

# --- Dragging the graph from anywhere (issue #20) ---
gs = frame["graphScroll"]
ns.HideDetail()
g.LorePathDB["collapsed"] = lua.table()
ns.Refresh()
def press(btn, x=500, y=500):
    harness["cx"], harness["cy"], harness["mouseDown"] = x, y, True
    btn["__scripts"]["OnMouseDown"](btn, "LeftButton")
def move(x, y):
    harness["cx"], harness["cy"] = x, y
    gs["__scripts"]["OnUpdate"](gs)
def release(btn):
    harness["mouseDown"] = False
    gs["__scripts"]["OnUpdate"](gs)
    btn["__scripts"]["OnClick"](btn)
def at(h, v):
    gs["__hrange"], gs["__vrange"], gs["__hs"], gs["__vs"] = 2000, 2000, h, v
pan_tile = [f for f in harness["all"].values() if f["questID"] is not None and f["sub"] is not None and f.IsShown(f)][0]
at(100, 100)
press(pan_tile)
move(503, 498)
check((gs["__hs"], gs["__vs"]) == (100, 100), "a press on a quest that moves a few pixels doesn't pan yet")
move(400, 450)
check((gs["__hs"], gs["__vs"]) == (200, 50), f"dragging from a quest pans the graph (to {gs['__hs']}, {gs['__vs']})")
g.GameTooltip.lines = lua.table()
other_tile = [f for f in harness["all"].values() if f["questID"] is not None and f["sub"] is not None and f.IsShown(f) and f is not pan_tile][0]
other_tile["__scripts"]["OnEnter"](other_tile)
check(len(list(g.GameTooltip.lines.values())) == 0, "quests passed over while dragging don't pop up tooltips")
release(pan_tile)
check(ns.detailQuest is None and gs["pan"] is None, "letting go after a drag doesn't open the quest's details")
press(pan_tile)
move(502, 501)
release(pan_tile)
check(ns.detailQuest == pan_tile["questID"], "a press and release without dragging still opens the details")
ns.HideDetail()

sec = [f for f in harness["all"].values() if f["key"] is not None and f["stepButton"] is not None and f.IsShown(f)][0]
was = sec["collapsed"]
at(0, 0)
press(sec)
move(520, 530)
release(sec)
check(sec["collapsed"] == was and (gs["__hs"], gs["__vs"]) == (0, 30), "dragging from a storyline header pans instead of collapsing it")
step = sec["stepButton"]
title_before = frame["zoneTitle"]["__text"]
focus_before = ns.focusedQuest
press(step)
move(460, 500)
release(step)
check(frame["zoneTitle"]["__text"] == title_before and ns.focusedQuest == focus_before, "dragging from a header's Next link pans instead of jumping")
at(0, 0)
press(gs)
move(450, 560)
release_canvas = gs["__scripts"]["OnMouseUp"]
harness["mouseDown"] = False
release_canvas(gs)
check((gs["__hs"], gs["__vs"]) == (50, 60) and gs["pan"] is None, "dragging empty space still pans")
# A plain click on the header still collapses or expands it.
press(sec)
release(sec)
sec =[f for f in harness["all"].values() if f["key"] == sec["key"] and f.IsShown(f)][0]
check(sec["collapsed"] != was, "a plain click on a storyline header still collapses or expands it")
g.LorePathDB["collapsed"] = lua.table()
ns.Refresh()
harness["cx"], harness["cy"] = 0, 0

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

# --- Zone list icons (issue #15) ---
ZI, II, ZoneIcon = ns.ZoneIcons, ns.InstanceInfo, ns.ui.ZoneIcon
check(ZI[1429] is not None and ZoneIcon(1429) == ZI[1429], f"Elwynn Forest uses AllTheThings' icon for it ({ZI[1429]})")
check(ZoneIcon(2521) == "Interface\\Icons\\Spell_Nature_Cyclone", "Zephras Isle uses its hand-picked icon")
check(ZI[2652] is None and ZoneIcon(2652) == ZI[1414], "a zone with no icon of its own uses its continent's")
with_ic = next(k for k in sorted(II.keys()) if II[k]["ic"] is not None)
without_ic = next(k for k in sorted(II.keys()) if II[k]["ic"] is None and ns.InstanceZones[k] == "dungeon")
check(ZoneIcon(with_ic) == II[with_ic]["ic"], "an instance uses AllTheThings' icon for it")
check(ZoneIcon(without_ic) == "Interface\\Icons\\INV_Misc_Key_03", "an instance without one uses the generic dungeon icon")
g.SlashCmdList["LOREPATH"]("here")
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Refresh()
zrows = [f for f in harness["all"].values() if f["zoneID"] is not None and f.IsShown(f)]
check(len(zrows) > 0 and all(r["icon"].IsShown(r["icon"]) and r["icon"]["__texture"] == ZoneIcon(r["zoneID"]) for r in zrows),
      f"every zone list row shows its zone's icon ({len(zrows)} rows)")
heads = {f["continent"]: f for f in harness["all"].values() if f["continent"] is not None and f["zoneID"] is None and f.IsShown(f)}
check(heads["Eastern Kingdoms"]["icon"]["__texture"] == ZI[1415] and heads["Dungeons"]["icon"]["__texture"] == "Interface\\Icons\\INV_Misc_Key_03"
      and heads["Raids"]["icon"]["__texture"] == "Interface\\Icons\\INV_Misc_Head_Dragon_01",
      "headings show their continent's icon, or a dungeon or raid icon")
check(frame["zoneIcon"]["__texture"] == ZoneIcon(1429), "the zone name above the graph has the zone's icon")
elwynn = [r for r in zrows if r["zoneID"] == 1429][0]
check(not elwynn["check"].IsShown(elwynn["check"]), "an unfinished zone has no tick on its icon")
for qid in ns.GetZoneQuests(1429).values():
    char["completed"][qid] = True
ns.Refresh()
elwynn = [f for f in harness["all"].values() if f["zoneID"] == 1429 and f.IsShown(f)][0]
check(elwynn["check"].IsShown(elwynn["check"]), "a finished zone gets a tick on its icon")
char["completed"] = lua.table()
ns.Refresh()

# --- Class and profession views (issue #8) ---
check(ns.Quests[5141]["sk"] == 165 and ns.Quests[5141]["sl"] == 225 and ns.Quests[5283]["sk"] == 164,
      "the extractor reads Professions.lua: Leatherworking (5141) and Blacksmithing (5283) quests")
cls = list(ns.GetZoneQuests("class").values())
zones_in_class = {ns.Quests[i]["z"] for i in cls}
check(len(cls) > 20 and all(1 in list(ns.Quests[i]["cl"].values()) for i in cls) and len(zones_in_class) > 3,
      f"the Class page has every Warrior quest, from {len(zones_in_class)} zones ({len(cls)} quests)")
sls, _ = ns.BuildStorylines("class")
travelling = [st for st in sls.values() if len({ns.Quests[n["id"]]["z"] for n in st["nodes"].values()}) > 1]
check(len(travelling) > 0, f"class chains that travel between zones are one storyline ({len(travelling)} of them)")
check(ns.GetMapName("class") == "Warrior quests", "the Class page is named after your class")

# Professions: a Leatherworker with 200 skill.
g.GetProfessions = lua.eval("function() return 1, nil end")
g.GetProfessionInfo = lua.eval("function(i) if i == 1 then return 'Leatherworking', 133611, LW_RANK, 300, 0, 0, 165 end end")
lua.execute("LW_RANK = 200")
ns.RefreshPlayer()
lw = list(ns.GetZoneQuests("prof:165").values())
check(5141 in lw and all(ns.ProfessionOf(ns.Quests[i]) == 165 for i in lw), f"the Leatherworking page has its quests ({len(lw)})")
check(ns.GetStatus(5141) == S.LEVEL and ns.GetLockReason(5141) == "skill", "a skill that's too low locks the quest")
check(ns.SkillText(ns.Quests[5141]) == "Leatherworking 225", "and it says which profession and skill it needs")
lua.execute("LW_RANK = 230")
ns.RefreshPlayer()
check(ns.GetStatus(5141) == S.AVAILABLE, "with enough skill it's available")
groups = [ (gr["name"], list(gr["pages"].values())) for gr in ns.GetSpecialGroups().values()]
check(groups[0][0] == "Class" and groups[1] == ("Professions", ["prof:165"]),
      f"the zone list gets Class and Professions groups, with only your professions: {groups}")
ns.SetSetting("showAllProfessions", True)
groups = dict((gr["name"], list(gr["pages"].values())) for gr in ns.GetSpecialGroups().values())
check(groups["Professions"][0] == "prof:165" and "prof:164" in groups["Professions"] and len(groups["Professions"]) > 5,
      f"'Show professions you don't have' lists the rest after yours: {groups['Professions']}")
bs = list(ns.GetZoneQuests("prof:164").values())
check(5283 in bs and ns.GetStatus(5283) == S.LEVEL and ns.GetLockReason(5283) == "skill",
      "a profession you don't have shows its quests, locked")
check(not ns.IsEligible(5283), "but they still don't appear in their zone")

# In the window.
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Refresh()
heads = sorted([f for f in harness["all"].values() if f["continent"] is not None and f["zoneID"] is None and f.IsShown(f)], key=lambda f: f["top"])
check([h["continent"] for h in heads[:2]] == ["Class", "Professions"], f"Class and Professions head the zone list: {[h['continent'] for h in heads[:3]]}")
check(heads[0]["icon"]["__texture"] == "Interface\\Icons\\ClassIcon_Warrior", "the Class heading has your class icon")
def page_row(page):
    rows = [f for f in harness["all"].values() if f["zoneID"] == page and f.IsShown(f)]
    return rows[0] if rows else None
lw_row, bs_row = page_row("prof:165"), page_row("prof:164")
check(lw_row is not None and lw_row["icon"]["__texture"] == 133611 and lw_row["text"]["__text"] == "Leatherworking",
      "your profession is listed with the client's icon")
check(bs_row is not None and bs_row["icon"]["__texture"] == "Interface\\Icons\\Trade_BlackSmithing" and bs_row["top"] > lw_row["top"],
      "a profession you don't have is listed after yours, with its own icon")
class_row = page_row("class")
class_row["__scripts"]["OnClick"](class_row)
check(frame["zoneTitle"]["__text"] == "Warrior quests" and frame["zoneIcon"]["__texture"] == "Interface\\Icons\\ClassIcon_Warrior",
      "clicking Class shows the Warrior quests page")
ctile = [f for f in harness["all"].values() if f["questID"] is not None and f["sub"] is not None and f.IsShown(f)][0]
g.GameTooltip.lines = lua.table()
ctile["__scripts"]["OnEnter"](ctile)
check(any(str(l).startswith("Zone: ") for l in g.GameTooltip.lines.values()), "quests on the Class page say which zone they're in")
ns.FocusQuest(ctile["questID"])
check(frame["zoneTitle"]["__text"] == "Warrior quests", "jumping to a quest that's on the Class page stays there")
bs_row = page_row("prof:164")
bs_row["__scripts"]["OnClick"](bs_row)
t5283 = [f for f in harness["all"].values() if f["questID"] == 5283 and f["sub"] is not None and f.IsShown(f)]
check(len(t5283) == 1 and "Needs Blacksmithing 225" in t5283[0]["sub"]["__text"], f"a locked profession quest's tile says what it needs")
ns.SetSetting("showAllProfessions", False)
g.GetProfessions = lua.eval("function() return nil end")
ns.RefreshPlayer()
g.SlashCmdList["LOREPATH"]("here")

# --- Quest search (issue #18) ---
# Unloaded names on a real client: only the bundled titles, plus one Forever quest the client names.
forever_only = next(qid for qid in sorted(ns.Quests.keys()) if qid >= 90000 and ns.IsEligible(qid)
                    and ns.QuestText[qid] is None and ns.CommunityText[qid] is None and not ns.Quests[qid]["rp"])
real_title = g.C_QuestLog.GetTitleForQuestID
g.C_QuestLog.GetTitleForQuestID = lua.eval(f"function(id) if id == {forever_only} then return 'Zzyx Forever Tale' end end")
def search(text, limit=None):
    ids, total = ns.SearchQuests(text, limit)
    return list(ids.values()), total
ids, total = search("garrick")
check(6 in ids, f"searching 'garrick' finds Bounty on Garrick Padfoot (6): {ids[:5]}")
check(6 in search("padfoot GARRICK")[0], "words match in any order, ignoring case")
check(search("6")[0][:1] == [6], "a quest ID finds that quest first")
check(search("")[1] == 0 and search("   ")[1] == 0, "an empty search finds nothing")
check(search("zzyx forever")[0] == [forever_only], "a Forever quest is found by the name the client gives it")
check(search("xyzzyq")[1] == 0, "a nonsense search finds nothing")
horde_titled = next(qid for qid, q in sorted(ns.Quests.items()) if q["f"] == 1 and ns.QuestText[qid] is not None)
check(horde_titled not in search(ns.QuestText[horde_titled]["t"])[0], "a Horde-only quest isn't found by an Alliance character")
ids, total = search("the")
check(len(ids) == 50 and total > 50, f"results stop at 50, with the full count kept ({total})")
ids, total = search("bounty")
names = [str(ns.GetQuestNameOrID(i)).lower() for i in ids]
starts = [n.startswith("bounty") for n in names]
check(starts[0] and starts == sorted(starts, reverse=True), "names that start with the search come first: " + " | ".join(names[:4]))
rp_titled = next(qid for qid, q in sorted(ns.Quests.items()) if q["rp"] == 1 and ns.IsEligible(qid) and ns.QuestText[qid] is not None)
ns.SetSetting("showRepeatable", False)
check(rp_titled not in search(ns.QuestText[rp_titled]["t"])[0], "repeatable quests aren't found while they're hidden")
ns.SetSetting("showRepeatable", True)
check(rp_titled in search(ns.QuestText[rp_titled]["t"])[0], "and are found when shown")

# In the window: results replace the zone list; clicking one jumps to it.
def result_rows():
    return sorted([f for f in harness["all"].values() if f["resultQuest"] is not None and f.IsShown(f)], key=lambda f: f["top"])
def zone_rows_shown():
    return [f for f in harness["all"].values() if f["zoneID"] is not None and f.IsShown(f)]
g.LorePathDB["listHidden"] = True
ns.ApplyListVisibility()
g.SlashCmdList["LOREPATH"]("search garrick")
box = frame["searchBox"]
check(frame.IsShown(frame) and box["__text"] == "garrick", "/lp search garrick opens the window with the search filled in")
check(frame["listInset"].IsShown(frame["listInset"]) and g.LorePathDB["listHidden"] is None, "and shows the zone list if it was hidden")
rows = result_rows()
check(len(rows) > 0 and any(r["resultQuest"] == 6 for r in rows) and len(zone_rows_shown()) == 0,
      f"the zone list shows {len(rows)} quest results instead of zones")
row6 = next(r for r in rows if r["resultQuest"] == 6)
check(not any(r["icon"].IsShown(r["icon"]) or r["check"].IsShown(r["check"]) for r in rows),
      "search results don't keep a zone's icon or tick from the rows they reuse")
check("Elwynn Forest" in row6["sub"]["__text"], f"a result shows its zone and status: {row6['sub']['__text']!r}")
g.GameTooltip.lines = lua.table()
row6["__scripts"]["OnEnter"](row6)
check(any("Bounty on Garrick" in str(l) for l in g.GameTooltip.lines.values()), "a result has the quest's tooltip")
row6["__scripts"]["OnClick"](row6)
check(frame["zoneTitle"]["__text"].startswith("Elwynn Forest") and ns.focusedQuest == 6, "clicking a result jumps to the quest")
check(len(result_rows()) > 0, "the results stay up after jumping, to try another")
box.SetText(box, "xyzzyq")
box["__scripts"]["OnTextChanged"](box, True)
headers = [f for f in harness["all"].values() if f.IsShown(f) and f["text"] is not None and f["text"]["__text"] == "No quests match"]
check(len(result_rows()) == 0 and len(headers) == 1, "a search with no matches says so")
box["__scripts"]["OnEscapePressed"](box)
check(box["__text"] == "" and len(result_rows()) == 0 and len(zone_rows_shown()) > 0, "Escape clears the search and brings the zones back")
g.C_QuestLog.GetTitleForQuestID = real_title
harness.RunTimers()

# --- Sharing quest text (issue #14) ---
import json, subprocess, tempfile
F = next(qid for qid in sorted(ns.Quests.keys()) if qid >= 90000 and ns.QuestText[qid] is None and ns.CommunityText[qid] is None)
cid = next(k for k, v in sorted(ns.CommunityText.items()) if v["d"] is not None)
saved_cache = g.LorePathDB["questCache"]
g.LorePathDB["characters"] = lua.table_from({"Notah": True, "Altie": True})
g.LorePathDB["questCache"] = lua.eval("{}")
cache = g.LorePathDB["questCache"]
cache[F] = lua.eval("""{ text = "Hello Altie, the |cffff0000storm|r comes.", obj = "Kill 5 | things", done = "Well done, $N.",
                         prog = "Back so soon?", money = 150, xp = 900, rep = { { 72, 250 } } }""")
cache[6] = lua.table_from({"text": ns.QuestText[6]["d"]})            # already bundled, word for word
cache[cid] = lua.table_from({"text": ns.CommunityText[cid]["d"]})    # already community text
codes, count = ns.BuildShareCodes()
codes = list(codes.values())
check(count == 1 and len(codes) == 1 and codes[0].startswith("LP1:"), f"/lp share's code holds only the new quest ({count} quest, {len(codes)} code)")
check("|" not in codes[0], "the code has no raw | (the edit box would eat colour and link codes)")
payload = json.loads(codes[0][4:])
e = payload["q"][str(F)]
check(e["d"] == "Hello $N, the storm comes." and e["o"] == "Kill 5 | things", f"names on any of your characters become $N, colour codes go: {e['d']!r}")
check(e["c"] == "Well done, $N." and e["p"] == "Back so soon?" and e["t"] == f"Q{F}", "it carries the closing and progress text, and the title")
check(e["m"] == 150 and e["x"] == 900 and e["r"] == [[72, 250]], "and gold, XP and reputation")
check(str(6) not in payload["q"] and str(cid) not in payload["q"], "text LorePath already has isn't shared again")

# Many quests split into codes that each fit in one issue.
many = [qid for qid in sorted(ns.Quests.keys()) if ns.QuestText[qid] is None and ns.CommunityText[qid] is None][:30]
for qid in many:
    cache[qid] = lua.table_from({"text": f"Story of quest {qid}, told at some length to fill the code."})
codes, count = ns.BuildShareCodes(400)
codes = list(codes.values())
shared = set()
for c in codes:
    shared |= set(json.loads(c[4:])["q"].keys())
check(len(codes) > 1 and all(len(c) <= 400 for c in codes) and shared == {str(q) for q in set(many) | {F}},
      f"a big collection splits into {len(codes)} codes under the limit, covering every quest once")

# The window.
g.SlashCmdList["LOREPATH"]("share")
share = g.LorePathShareFrame
box = share["box"]
check(share.IsShown(share) and box["__text"] == list(ns.BuildShareCodes()[0].values())[0], "/lp share opens a window showing the code")
box["__scripts"]["OnTextChanged"](box, True)
check(box["__text"] == box["code"], "typing in it can't change the code")
check("quests" in share["info"]["__text"] and "Share quest text" in share["info"]["__text"], "it explains where to send it")
g.LorePathDB["questCache"] = lua.eval("{}")
before_chat = len(list(harness["chat"].values()))
check(ns.OpenShare() is False and any("Nothing new to share" in str(m) for m in list(harness["chat"].values())[before_chat:]),
      "with nothing new, /lp share says so")

# The GitHub side reads the code back (tools/merge_quest_text.py).
sys.path.insert(0, os.path.join(ROOT, "tools"))
import merge_quest_text as mqt
issue_body = "### Share code\n\n" + "LP1:" + json.dumps(payload) + "\n"
quests = mqt.read_share_codes(issue_body)
check(quests[str(F)]["d"] == "Hello $N, the storm comes." and quests[str(F)]["c"] == "Well done, $N.", "the merge tool reads a share code from an issue body")
try:
    mqt.read_share_codes("LP1:{not json")
    bad = False
except ValueError:
    bad = True
check(bad, "a broken code is rejected")
with tempfile.TemporaryDirectory() as tmp:
    sub, rep = os.path.join(tmp, "issue.txt"), os.path.join(tmp, "report.md")
    with open(sub, "w") as f:
        f.write(issue_body)
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "merge_quest_text.py"), "--dry-run", "--replace", "--report", rep, sub],
                         capture_output=True, text=True)
    report = open(rep).read() if os.path.exists(rep) else out.stderr
check(out.returncode == 0 and "1 new quests" in report, f"a dry run reports what the code adds: {report.strip()[:120]}")
g.LorePathDB["questCache"] = saved_cache

# --- Zone list colours by completion ---
PC = ns.ui.ProgressColor
def rgb(c):
    return tuple(round(v, 2) for v in c.values())
check(rgb(PC(0, 10)) == (0.62, 0.62, 0.62) and rgb(PC(0, 0)) == (0.62, 0.62, 0.62), "a zone you haven't started is grey")
check(rgb(PC(10, 10)) == (0.42, 0.83, 0.37), "a finished zone is green, as before")
check(rgb(PC(1, 100))[:2] == (1.0, 0.26), "just started is red")
check(rgb(PC(40, 100)) == (1.0, 0.55, 0.15), "40% is orange")
check(rgb(PC(80, 100)) == (1.0, 0.82, 0.2), "80% is WoW's gold")
near = rgb(PC(99, 100))
check(0.8 <= near[0] < 1.0 and abs(near[0] - 0.42) > 0.3, f"nearly done leans towards green, but stays clearly short of it: {near}")
greens = [rgb(PC(d, 100))[1] for d in range(1, 100)]
check(greens == sorted(greens), "colours move steadily from red towards green")
g.SlashCmdList["LOREPATH"]("here")
char["completed"] = lua.table()
elwynn_ids = list(ns.GetZoneQuests(1429).values())
for qid in elwynn_ids[: len(elwynn_ids) // 2]:
    char["completed"][qid] = True
ns.Refresh()
row = [f for f in harness["all"].values() if f["zoneID"] == 1429 and f.IsShown(f)][0]
done, total, _ = ns.GetZoneProgress(1429)
check(rgb(row["text"]["__color"]) == rgb(PC(done, total)) and rgb(row["text"]["__color"]) != (0.62, 0.62, 0.62),
      f"a zone row's name takes its colour ({done}/{total}: {rgb(row['text']['__color'])})")
other = [f for f in harness["all"].values() if f["zoneID"] is not None and f["zoneID"] != 1429 and f.IsShown(f)
         and ns.GetZoneProgress(f["zoneID"])[0] == 0][0]
check(rgb(other["text"]["__color"]) == (0.62, 0.62, 0.62), "zones you haven't started stay grey")
char["completed"] = lua.table()
ns.Refresh()

unexpected = list(harness["errors"].values())
check(len(unexpected) == 0, "no errors were caught anywhere else in the run: " + " | ".join(unexpected)[:300])
print("chat:", list(harness["chat"].values())[-3:])
print()
print("FAILED:" if failures else "All checks passed.", *failures, sep="\n  ")
sys.exit(1 if failures else 0)
