"""Runs LorePath's Lua files against a fake WoW API and checks the core logic.

    pip install lupa
    python3 tools/test/run_tests.py
"""
import os
import sys

from lupa import LuaRuntime

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
FILES = ["Data/Quests.lua", "Data/QuestNotes.lua", "Data/QuestStarts.lua", "Data/QuestText.lua", "Data/CommunityText.lua", "Data/Attunements.lua", "Core.lua", "UI.lua", "Detail.lua", "QuestLog.lua", "Share.lua", "Settings.lua", "Pins.lua", "Main.lua"]

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute("unpack = table.unpack")  # WoW runs Lua 5.1, which has a global unpack
harness = lua.execute(open(os.path.join(ROOT, "tools/test/harness.lua")).read())
# Pin templates from the addon's XML, so the fake map canvas builds pins with the mixin the XML names.
import re
for xml in ("Pins.xml",):
    for tname, mixin in re.findall(r'name="(\w+)"\s+mixin="(\w+)"', open(os.path.join(ROOT, xml)).read()):
        harness["templates"][tname] = mixin
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
ns.Toggle(True)
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
# One tile per Elwynn quest the character can see (derived from the data, so ATT syncs don't break it),
# plus a linked tile for each quest on another page just before or after a storyline.
elwynn_links = sum(len(list((s["links"] or lua.table()).values())) for s in ns.BuildStorylines(1429)[0].values())
check(zone_quests > 0 and len(tiles) == zone_quests + elwynn_links and errors == 0,
      f"all {len(tiles)} Elwynn tiles ({zone_quests} zone quests, {elwynn_links} linked) build a tooltip without errors")
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

# ...and your class and race back to $C and $R, where the text is talking to you.
g.GetQuestText = lua.eval("function() return 'Well done, warrior! Few humans... Thank you, human. The blood of a warrior runs in you.' end")
harness.Fire("QUEST_DETAIL")
saved = g.LorePathDB["questCache"][cid]["text"]
check(saved == "Well done, $c! Few humans... Thank you, $r. The blood of a warrior runs in you.",
      f"saved story text puts back your class and race when addressed to you, not 'a warrior': {saved!r}")
g.LorePathDB["questCache"][cid] = None

people = lua.eval('{ { class = "Mage", race = "Orc" }, { class = "Hunter", race = "Tauren" } }')
for text, want, why in [
    ("Yes, mighty mage, I sensed your arrival.", "Yes, mighty $c, I sensed your arrival.", "a class word said to you"),
    ("Hey!  Mage!  Come here!", "Hey!  $C!  Come here!", "a capitalised one keeps its capital"),
    ("This is no task for a single mage.", "This is no task for a single $c.", "after an adjective"),
    ("The blood of a hunter streaks through your veins.", "The blood of a hunter streaks through your veins.", "not after an article"),
    ("Slay 8 Defias Mage and the Mage's apprentice.", "Slay 8 Defias Mage and the Mage's apprentice.", "nor inside a name"),
    ("Fear not the waters, orc.", "Fear not the waters, $r.", "a race said to you"),
    ("We tauren have used this pigment; an orc without her scars.", "We tauren have used this pigment; an orc without her scars.", "but not a race in general"),
]:
    got = ns.PutPlaceholders(text, people)
    check(got == want, f"placeholders: {why}: {got!r}")

# Text the bundled vanilla text already has, once its $C, $R and $G are filled in,
# isn't shared: that's how gendered wording stays out of shared text.
mo = lua.eval('{ { class = "Mage", race = "Orc" } }')
v874 = "You have hunted the beasts of the Barrens.  Your spirit is strong.  But a hunter must always be prepared.  A true hunter can stalk prey down any path.  Mountains and swamps will not sway her.\n\nNot even the sea.\n\nFind my sister, Mahren.  She hunts the great water beasts along the coast.  She will be your teacher in their ways.\n\nBut be wary in your search for her, for the Barrens' coast is held by humans."
check(ns.QuestText[874] is not None and ns.MatchesBundled(v874, ns.QuestText[874]["d"], mo), "a female orc's saved text matches the bundled text with $ghim:her;")
check(ns.MatchesBundled("Hey!  Mage!  Come here!\n\nMy raiders and I", "Hey!  $C!  Come here!$B$BMy raiders and I", mo), "and a mage's matches $C")
check(not ns.MatchesBundled("Hey!  Mage!  Come here! Different.", "Hey!  $C!  Come here!", mo), "different text doesn't match")
check(not ns.MatchesBundled("Hey!  Warrior!", "Hey!  $C!", mo), "nor another class than the account's")

# LorePath's own notes (tools/extract_att.py LOREPATH_NOTES) go after ATT's.
check("Rig Wars" in ns.QuestNotes[2842] and "conversation option" in ns.QuestNotes[2842],
      "Chief Engineer Scooty's note keeps ATT's and adds that Sovik needs his conversation option first")

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

ns.SetSetting("showSpoilers", True)
ns.RefreshDetail()
check(any("Garrick has gathered" in s for s in detail_texts()), "with spoilers on, quests you haven't started show their story")
ns.SetSetting("showSpoilers", False)
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
ns.Toggle(True)
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
def tile_count(st):
    return len(list(st["nodes"].values())) + len(list((st["links"] or lua.table()).values()))
first_n = tile_count(first)
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
second_n = tile_count(list(storylines.values())[1])
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
ns.ShowInLorePath(tid)
check(ns.detailQuest == tid, f"ShowInLorePath({tid}) opens that quest")
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
char["level"], char["map"] = 60, 1448
rep = char["reputation"]
def fresh_status(qid):
    ns.RefreshPlayer()  # clears the cached standings, like a refresh after UPDATE_FACTION
    return ns.GetStatus(qid)
check(ns.Quests[6031]["mr"][1] == 576 and ns.Quests[6031]["mr"][2] == 3000, "extractor kept 6031's minReputation as mr={576,3000}")
check(fresh_status(6031) == S.AVAILABLE and ns.GetLockReason(6031) is None,
      "unknown faction standing doesn't lock or hide the quest")
check(ns.IsEligible(6031) and 6031 in list(ns.GetZoneQuests(1448).values()), "a reputation quest stays in its zone list (Felwood)")
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
# a plain Felwood quest for the test).
capped = next(qid for qid, q in sorted(ns.Quests.items()) if q["z"] == 1448 and not q["pre"] and not q["mr"]
              and not q["sk"] and not q["bc"] and not q["rp"] and ns.IsEligible(qid) and (q["l"] or 1) <= 60
              and ns.GetStatus(qid) == S.AVAILABLE and qid in list(ns.GetZoneQuests(1448).values()))
ns.Quests[capped]["xr"] = lua.eval("{609, 9000}")
rep[609] = 8999
ns.RefreshPlayer()
done0, total0, *_ = ns.GetZoneProgress(1448)
check(fresh_status(capped) == S.AVAILABLE, "below the maximum: available")
rep[609] = 9000
ns.RefreshPlayer()
done1, total1, *_ = ns.GetZoneProgress(1448)
check(ns.GetStatus(capped) == S.MISSED and ns.GetLockReason(capped) == "maxrep", "at the maximum (Honored): no longer available")
check(total1 == total0 - 1, f"a quest closed by reputation isn't counted as missing ({total0} -> {total1})")
char["completed"][capped] = True
ns.RefreshCompleted()
check(ns.GetStatus(capped) == S.DONE, "a quest done before your reputation went up still shows as done")
char["completed"][capped] = None
ns.RefreshCompleted()

# UI: the tile and tooltip explain the lock, without talking about levels.
rep[576] = 1500
ns.Toggle(True)
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
ns.Toggle(True) if not frame.IsShown(frame) else None
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
          for c in headings if c not in ("Dungeons", "Raids", "Battlegrounds")), "Dungeons and Raids come after the continents")
check("Battlegrounds" in headings and headings["Battlegrounds"]["top"] > headings["Raids"]["top"], "Battlegrounds come after Raids")
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
ns.Toggle(True)
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
ns.Toggle(True)
check(frame["zoneTitle"]["__text"] == "Elwynn Forest", "back outside, /lp here opens the outdoor zone again")
g.IsInInstance, g.GetRealZoneText, C_Map.GetAreaInfo = None, None, None

# --- Zone list icons (issue #15) ---
ZI, II, ZoneIcon = ns.ZoneIcons, ns.InstanceInfo, ns.ui.ZoneIcon
check(ZI[1429] is not None and ZoneIcon(1429) == ZI[1429], f"Elwynn Forest uses AllTheThings' icon for it ({ZI[1429]})")
check(ZoneIcon(2521) == "Interface\\Icons\\Spell_Nature_Cyclone", "Zephras Isle uses its hand-picked icon")
saved_icon, ZI[2652] = ZI[2652], None
check(ZoneIcon(2652) == ZI[1414], "a zone with no icon of its own uses its continent's")
ZI[2652] = saved_icon
with_ic = next(k for k in sorted(II.keys()) if II[k]["ic"] is not None)
without_ic = next(k for k in sorted(II.keys()) if II[k]["ic"] is None and ns.InstanceZones[k] == "dungeon")
check(ZoneIcon(with_ic) == II[with_ic]["ic"], "an instance uses AllTheThings' icon for it")
check(ZoneIcon(without_ic) == "Interface\\Icons\\INV_Misc_Key_03", "an instance without one uses the generic dungeon icon")
ns.Toggle(True)
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
check(len(cls) > 20 and all(1 in list(ns.Quests[i]["cl"].values()) for i in cls if ns.Quests[i]["cl"] is not None)
      and all(ns.HomePage(i) == "class" for i in cls if ns.Quests[i]["cl"] is None) and len(zones_in_class) > 3,
      f"the Class page has every Warrior quest, from {len(zones_in_class)} zones ({len(cls)} quests), and Tier 0.5's shared steps")
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
ns.Toggle(True)

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
ns.Toggle(True)
box = frame["searchBox"]
box.SetText(box, "garrick")
box["__scripts"]["OnTextChanged"](box, True)
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
import contextlib, io, json, shutil, subprocess, tempfile
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

# The share code puts class and race back too, using every character on the
# account, and leaves out vanilla text the bundled text has with placeholders.
g.LorePathDB["characters"] = lua.eval('{ Notah = { class = "Mage", race = "Orc" }, Altie = true }')
g.LorePathDB["questCache"] = lua.eval("{}")
cache = g.LorePathDB["questCache"]
cache[F] = lua.eval("""{ done = "Your skill is impressive, mage; well done.", obj = "Kill 3 Dalaran Mage." }""")
cache[874] = lua.table_from({"text": v874})
codes, count = ns.BuildShareCodes()
payload = json.loads(list(codes.values())[0][4:])
e = payload["q"][str(F)]
check(e["c"] == "Your skill is impressive, $c; well done." and e["o"] == "Kill 3 Dalaran Mage.",
      f"/lp share puts $c back for a class on the account, not in objectives: {e!r}")
check("874" not in payload["q"], "and leaves out vanilla text that matches the bundled text once filled in")
cache[874] = lua.table_from({"text": v874.replace("Not even the sea.", "Not even the Forever sea.")})
payload = json.loads(list(ns.BuildShareCodes()[0].values())[0][4:])
check(payload["q"].get("874", {}).get("d", "").count("Forever sea") == 1,
      "but WoW Forever's wording, where it differs from the (classic) bundled text by even a word, is still shared")
g.LorePathDB["characters"] = lua.table_from({"Notah": True, "Altie": True})
g.LorePathDB["questCache"] = lua.eval("{}")
cache = g.LorePathDB["questCache"]
cache[F] = lua.eval("""{ text = "Hello Altie, the |cffff0000storm|r comes.", obj = "Kill 5 | things", done = "Well done, $N.",
                         prog = "Back so soon?", money = 150, xp = 900, rep = { { 72, 250 } } }""")
payload = json.loads(list(ns.BuildShareCodes()[0].values())[0][4:])

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
link = share["link"]
check(ns.SHARE_PAGE_URL == "lorepath-share.jacobhaynes49.workers.dev" and link["__text"] == ns.SHARE_PAGE_URL,
      "the share window's link box holds the share page's address")
deployed = ns.SHARE_PAGE_URL
ns.SHARE_PAGE_URL = None
ns.ShowSharePart(1)
check("no account needed" not in share["info"]["__text"] and link["__text"] == ns.SHARE_URL,
      "until the share page is deployed, the window's link box holds the GitHub issue form")
ns.SHARE_PAGE_URL = "lorepath-share.example.workers.dev"
ns.ShowSharePart(1)
check(link["__text"] == "lorepath-share.example.workers.dev" and "no account needed" in share["info"]["__text"]
      and "Share quest text" in share["info"]["__text"], "once it is, the link box holds the share page, and the issue form is still mentioned")
link["__scripts"]["OnTextChanged"](link, True)
check(link["__text"] == "lorepath-share.example.workers.dev", "typing in the link box can't change the link")
ns.SHARE_PAGE_URL = deployed
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
check(mqt.matches_bundled(v874, ns.QuestText[874]["d"]) and mqt.matches_bundled("Hey!  Mage!\n\nGo.", "Hey!  $C!$B$BGo.")
      and not mqt.matches_bundled("Hey!  Mage! Other.", "Hey!  $C!"), "the merge tool leaves out vanilla text with its placeholders filled in, too")
check(not mqt.matches_bundled(v874.replace("Not even the sea.", "Not even the Forever sea."), ns.QuestText[874]["d"]),
      "and keeps text Forever has reworded")
check(mqt.matches_bundled("Fear not, night elf.", "Fear not, $r.") and mqt.matches_bundled("Fear not, orc.", "Fear not, $r.")
      and not mqt.matches_bundled("Fear not, murloc.", "Fear not, $r."), "and fills $r with any race, two-word ones too")

# With --replace (the workflow), a code from an older LorePath that left the
# player's class in mustn't undo a placeholder already put back; new wording still wins.
with tempfile.TemporaryDirectory() as tmp:
    real_out = mqt.OUT
    mqt.OUT = os.path.join(tmp, "CommunityText.lua")
    with open(real_out, encoding="utf-8") as f:
        original = f.read()
    with open(mqt.OUT, "w", encoding="utf-8") as f:
        f.write(original)
    community = mqt.load_table(mqt.LuaRuntime(unpack_returned_tuples=True, register_eval=False), mqt.OUT, "CommunityText")
    qid = next(q for q, e in sorted(community.items()) if e.get("p") and "$c" in e["p"])
    old_p = community[qid]["p"]
    sub = os.path.join(tmp, "code.txt")
    with open(sub, "w", encoding="utf-8") as f:
        f.write("LP1:" + json.dumps({"v": 1, "q": {str(qid): {"p": old_p.replace("$c", "mage", 1), "c": "Brand new closing words."}}}) + "\n")
    argv = sys.argv
    sys.argv = ["merge_quest_text.py", "--replace", sub]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mqt.main()
    finally:
        sys.argv = argv
        merged = mqt.load_table(mqt.LuaRuntime(unpack_returned_tuples=True, register_eval=False), mqt.OUT, "CommunityText")
        mqt.OUT = real_out
check(merged[qid]["p"] == old_p and merged[qid]["c"] == "Brand new closing words.",
      f"--replace keeps quest {qid}'s $c rather than an older code's 'mage', but still takes new wording")
check(ns.MatchesBundled(old_p.replace("$c", "mage", 1), old_p, lua.eval('{ { class = "Mage" } }')),
      "in game, /lp share also leaves out text that's LorePath's community text with placeholders filled in")
check(mqt.player_words("Yes, mighty mage. Fear not the waters, orc. The blood of a hunter; we tauren; Defias Mage.") == ["mage", "orc"],
      "and its report flags class and race words that may be the player's own")
with tempfile.TemporaryDirectory() as tmp:
    sub, rep = os.path.join(tmp, "issue.txt"), os.path.join(tmp, "report.md")
    with open(sub, "w") as f:
        f.write(issue_body)
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "merge_quest_text.py"), "--dry-run", "--replace", "--report", rep, sub],
                         capture_output=True, text=True)
    report = open(rep).read() if os.path.exists(rep) else out.stderr
check(out.returncode == 0 and "1 new quests" in report, f"a dry run reports what the code adds: {report.strip()[:120]}")

# The share page (share/worker.js) checks codes and opens the issues the merge
# tool reads. Its own checks run under node, or macOS's jsc where node is missing.
js = shutil.which("node") or next((p for p in ["/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"] if os.path.exists(p)), None)
if js:
    args = [js, "test_worker.js"] if js.endswith("node") else [js, "-m", "test_worker.js"]
    run = subprocess.run(args, cwd=os.path.join(ROOT, "share"), capture_output=True, text=True)
    out = (run.stdout + run.stderr).strip()
    check(run.returncode == 0 and "FAIL" not in out, f"the share page's checks pass ({out.count('PASS')} checks)" + ("" if run.returncode == 0 else ": " + out[-600:]))
else:
    print("SKIP the share page's checks: no node or jsc to run them")

# --- Quest starts: saved, shared and used (issue #37) ---
g.LorePathDB["questCache"] = lua.eval("{}")
cache = g.LorePathDB["questCache"]
def no_start(qid):
    q = ns.Quests[qid]
    return q["m"] is None and q["di"] is None and q["qg"] is None and q["si"] is None and q["fv"] is None and ns.CommunityText[qid] is None
NOSTART = next(qid for qid in sorted(ns.Quests.keys()) if qid >= 90000 and no_start(qid) and ns.IsEligible(qid))
ITEMQ = next(qid for qid in sorted(ns.Quests.keys()) if ns.Quests[qid]["si"] is not None and ns.QuestStarts[qid] is None
             and ns.Quests[qid]["m"] is None and ns.Quests[qid]["di"] is None and ns.CommunityText[qid] is None)
KNOWN = next(qid for qid in sorted(ns.Quests.keys()) if ns.Quests[qid]["m"] is not None and ns.Quests[qid]["qg"] is not None
             and ns.Quests[qid]["si"] is None and ns.Quests[qid]["fv"] is None)
# The quest window's API, as Lua functions (LorePath only calls real functions).
quest_window = lua.eval("""(function()
    local w = { id = 0, instance = false, x = 0.4567, y = 0.1234 }
    GetQuestID = function() return w.id end
    UnitGUID = function(unit) if unit == "questnpc" then return w.guid end end
    IsInInstance = function() return w.instance end
    C_Map.GetPlayerMapPosition = function() return { GetXY = function() return w.x, w.y end } end
    return w
end)()""")
def offer(qid, guid, instance=False):
    quest_window["id"], quest_window["guid"], quest_window["instance"] = qid, guid, instance
    harness.Fire("QUEST_DETAIL")
    s = cache[qid] and cache[qid]["start"]
    return None if s is None else {k: s[k] for k in ("k", "n", "m", "x", "y", "i") if s[k] is not None}

char["map"] = 1429
s = offer(ITEMQ, None)
check(s == {"k": "i", "m": 1429, "x": 45.7, "y": 12.3}, f"a quest offered with no unit is saved as from an item, with your map and position: {s}")
s = offer(ITEMQ, "Creature-0-1-2-3-4567-0000ABCDEF")
check(s == {"k": "u", "n": 4567, "m": 1429, "x": 45.7, "y": 12.3}, f"a quest giver offering it later replaces the item: {s}")
s = offer(ITEMQ, None)
check(s["k"] == "u", "but an item doesn't replace a quest giver")
s = offer(NOSTART, "GameObject-0-1-2-3-178888-0000ABCDEF")
check(s == {"k": "o", "n": 178888, "m": 1429, "x": 45.7, "y": 12.3}, f"an object (a wanted poster) is saved with its object ID: {s}")
quest_window["x"], quest_window["y"] = 0.9, 0.9
s = offer(NOSTART, "Creature-0-1-2-3-99-0000ABCDEF", instance=True)
check(s == {"k": "u", "n": 99, "i": 1429}, f"a quest giver beats the object, and inside an instance only the instance is kept: {s}")
s = offer(KNOWN, "Player-1234-0ABCDEF0")
check(s is None, "a quest another player shares with you isn't saved as a start")
quest_window["x"], quest_window["y"] = 0.4567, 0.1234

# Secret values (1.2.0-beta3 in game): the client can give UnitGUID("questnpc")
# as a value addons may not compare or read. Faked here as a table that errors
# on any use, which issecretvalue recognises.
secret = lua.eval("""(function()
    local s = setmetatable({}, {
        __index = function() error("attempt to index a secret string value") end,
        __eq = function() error("attempt to compare a secret string value") end,
        __lt = function() error("attempt to compare a secret string value") end,
        __le = function() error("attempt to compare a secret string value") end,
        __concat = function() error("attempt to concatenate a secret string value") end,
        __len = function() error("attempt to get length of a secret string value") end,
    })
    issecretvalue = function(v) return rawequal(v, s) end
    return s
end)()""")
SECRET_Q = next(qid for qid in sorted(ns.Quests.keys()) if qid >= 90000 and no_start(qid) and qid not in (NOSTART, ITEMQ)
                and cache[qid] is None)
harness["errors"] = lua.table()
before_chat = len(list(harness["chat"].values()))
g.GetQuestText = lua.eval("function() return 'Bring me ten boar ribs.' end")
s = offer(SECRET_Q, secret)
check(len(list(harness["errors"].values())) == 0 and not any("Something went wrong" in str(m) for m in list(harness["chat"].values())[before_chat:]),
      "a quest giver the game keeps secret doesn't break the quest window")
check(s is None and cache[SECRET_Q]["text"] == "Bring me ten boar ribs.",
      "its start isn't saved (it isn't mistaken for an item), but its text still is")
g.GetQuestText = lua.eval("function() return SECRET end")
lua.globals().SECRET = secret
cache[SECRET_Q]["text"] = None
harness.Fire("QUEST_DETAIL")
check(len(list(harness["errors"].values())) == 0 and cache[SECRET_Q]["text"] is None, "secret quest text is skipped, not compared or saved")
g.GetQuestText = None
g.issecretvalue = None
offer(KNOWN, "Creature-0-1-2-3-11-0000ABCDEF")

codes, count = ns.BuildShareCodes()
starts = {int(k): v.get("s") for c in codes.values() for k, v in json.loads(c[4:])["q"].items()}
check(starts.get(NOSTART) == {"k": "u", "n": 99, "i": 1429} and starts.get(ITEMQ) == {"k": "u", "n": 4567, "m": 1429, "x": 45.7, "y": 12.3},
      f"/lp share carries the starts of quests LorePath has no start for: {starts}")
check(starts.get(KNOWN) is None, "but not of quests whose start and giver LorePath already has")

# The merge tool keeps starts, validates them, and writes them to Data/CommunityText.lua.
read = mqt.read_share_codes(list(codes.values())[0])
check(mqt.start_value(read[str(ITEMQ)]["s"]) == {"k": "u", "n": 4567, "m": 1429, "x": 45.7, "y": 12.3}, "the merge tool reads a start from a share code")
check(mqt.start_value({"k": "x", "n": 1}) is None and mqt.start_value({"k": "u", "m": 1429, "x": 140, "y": 5}) == {"k": "u"}
      and mqt.start_value({"k": "i", "n": 5, "i": 291}) == {"k": "i", "i": 291}, "and rejects bad kinds and positions")
item_s, npc_s = {"k": "i", "m": 1, "x": 1.0, "y": 2.0}, {"k": "u", "n": 7}
check(mqt.better_start(None, item_s) is item_s and mqt.better_start(item_s, npc_s) is npc_s and mqt.better_start(npc_s, item_s) is npc_s
      and mqt.better_start(npc_s, {"k": "u", "n": 8}) is npc_s, "it keeps the first start, unless a quest giver comes after an item")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "CommunityText.lua")
    with open(path, "w") as f:
        f.write("\n".join(mqt.HEADER + [mqt.entry_line(NOSTART, {"t": "A", "s": {"k": "u", "n": 99, "m": 1429, "x": 45.7, "y": 12.0}}), "}"]) + "\n")
    back = mqt.load_table(lua, path, "CommunityText")
check(back.get(NOSTART) == {"t": "A", "s": {"k": "u", "n": 99, "m": 1429, "x": 45.7, "y": 12}}, f"a start written to community data reads back the same: {back.get(NOSTART)}")
with tempfile.TemporaryDirectory() as tmp:
    sv = os.path.join(tmp, "LorePath.lua")
    with open(sv, "w") as f:
        f.write(f'LorePathDB = {{ questCache = {{ [{NOSTART}] = {{ start = {{ k = "o", n = 5, m = 1429, x = 1.5, y = 2.5 }} }} }} }}\n')
    quests, _, kind = mqt.read_submission(lua, sv)
check(kind == "LorePath" and mqt.start_value(quests[NOSTART]["s"]) == {"k": "o", "n": 5, "m": 1429, "x": 1.5, "y": 2.5},
      "and from a saved-variables file")

# Community starts fill in quests with none: start point, quest giver, Show on map.
qs = ns.Quests[NOSTART]
ns.CommunityText[NOSTART] = lua.eval('{ s = { k = "u", n = 4567, m = 1429, x = 40, y = 50 } }')
ns.CommunityText[ITEMQ] = lua.eval('{ s = { k = "i", m = 1429, x = 12.5, y = 34.5 } }')
ns.RefreshPlayer()
check(qs["m"] == 1429 and qs["x"] == 40 and qs["qg"] == 4567 and qs["cs"] is True, "a shared start gives a quest with none a start point and quest giver")
check(ns.Quests[ITEMQ]["m"] is None, "an item's start isn't used as a start point")
ns.ShowDetail(NOSTART)
texts = detail_texts()
check("Starts in Elwynn Forest (40.0, 50.0)" in texts and g.LorePathDetailFrame["mapButton"].IsShown(g.LorePathDetailFrame["mapButton"]),
      "its details show where it starts, with Show on map")
harness["waypoint"] = None
check(ns.ShowQuestStart(NOSTART) and harness["waypoint"]["m"] == 1429, "and Show on map sets the waypoint there")
ns.ShowDetail(ITEMQ)
texts = detail_texts()
check("Picked up from an item around Elwynn Forest (12.5, 34.5)." in texts, f"an item-started quest with no known source shows where players picked it up")
check(ns.ItemStartHint(KNOWN) is None, "quests without one have no hint")
ns.HideDetail()
ns.CommunityText[NOSTART] = None
ns.CommunityText[ITEMQ] = None
for key in ("m", "x", "y", "qg", "cs"):
    qs[key] = None
g.GetQuestID = None
g.UnitGUID = None
g.IsInInstance = None
g.C_Map.GetPlayerMapPosition = None
g.LorePathDB["questCache"] = saved_cache

# --- One version of each quest (Shaman Call of Earth and Call of Fire) ---
EARTH = {"durotar": [1516, 1517, 1518], "mulgore": [1519, 1520, 1521], "zephras": [92466, 92467, 92468]}
FIRE_CRUMBS = [1522, 1523, 2983, 2984]
def shaman(race):
    char["race"], char["class"], char["faction"], char["level"] = race, 7, "Horde", 30
    char["completed"], char["log"] = lua.table(), lua.table()
    ns.RefreshPlayer()
    ns.RefreshCompleted()
    return set(ns.GetZoneQuests("class").values())
def earth_shown(page):
    return {k for k, ids in EARTH.items() if any(i in page for i in ids)}
page = shaman(2)
check(earth_shown(page) == {"durotar"} and all(i in page for i in EARTH["durotar"]),
      f"an orc Shaman's Class page has one Call of Earth chain, Durotar's: {earth_shown(page)}")
check([i for i in FIRE_CRUMBS if i in page] == FIRE_CRUMBS and 1524 in page,
      "every Call of Fire breadcrumb stays: each is a different place to start")
page = shaman(6)
check(earth_shown(page) == {"mulgore"}, "a tauren Shaman gets Mulgore's chain")
page = shaman(96)
check(earth_shown(page) == {"zephras"} and all(i in page for i in EARTH["zephras"]),
      f"a Zephras Isle Shaman gets Zephras Isle's chain: {earth_shown(page)}")
FIRE_BARRENS, FIRE_ZEPHRAS = [1524, 1525, 1526, 1527], [97243, 97244, 97245, 97257]
check(all(i in page for i in FIRE_ZEPHRAS) and not any(i in page for i in FIRE_BARRENS + FIRE_CRUMBS),
      "and Zephras Isle's own Call of Fire, without the Barrens chain or the breadcrumbs that only lead into it")
page = shaman(2)
char["completed"][1519] = True
ns.RefreshCompleted()
page = set(ns.GetZoneQuests("class").values())
check(earth_shown(page) == {"mulgore"}, "the version you've actually done is the one shown")
char["completed"] = lua.table()
ns.RefreshCompleted()
page = shaman(2)
# A real WoW Forever character (race 96, 1.1.0-beta2): the game marks every
# version of Call of Earth completed, and the first step of the Barrens Call of
# Fire too, though only Zephras Isle's chains were played.
page = shaman(96)
for qid in EARTH["durotar"] + EARTH["mulgore"] + EARTH["zephras"] + [1524] + FIRE_ZEPHRAS:
    char["completed"][qid] = True
ns.RefreshCompleted()
page = set(ns.GetZoneQuests("class").values())
check(earth_shown(page) == {"zephras"} and all(i in page for i in EARTH["zephras"]),
      f"with every version marked completed, home decides: only Zephras Isle's Call of Earth ({sorted(i for ids in EARTH.values() for i in ids if i in page)})")
check(all(i in page for i in FIRE_ZEPHRAS) and not any(i in page for i in FIRE_BARRENS + FIRE_CRUMBS),
      f"and only Zephras Isle's Call of Fire, not the Barrens chain whose first step is marked done ({sorted(i for i in FIRE_BARRENS + FIRE_ZEPHRAS + FIRE_CRUMBS if i in page)})")
char["log"][1517] = True
page = set(ns.GetZoneQuests("class").values())
check(1517 in page, "a quest in your log is never hidden")
char["log"], char["completed"] = lua.table(), lua.table()
ns.RefreshCompleted()
page = shaman(2)
durotar, barrens = set(ns.GetZoneQuests(1411).values()), set(ns.GetZoneQuests(1413).values())
check(all(i in durotar for i in EARTH["durotar"]), "a zone with one version keeps it")
check([i for i in FIRE_CRUMBS if i in barrens] == FIRE_CRUMBS and 1524 in barrens,
      "The Barrens keeps all four Call of Fire breadcrumbs")
mulgore = set(ns.GetZoneQuests(1412).values())
check(not any(i in mulgore for i in EARTH["mulgore"]),
      "a class quest's zone page agrees with the Class page: an orc doesn't see Mulgore's Call of Earth on Mulgore's page")
check(861 in mulgore and 844 in barrens,
      "versions of quests that aren't class quests still show in each zone (Plainstrider Menace in Mulgore and The Barrens)")
# A Skyborne Shaman who did Zephras Isle's Call of Fire: the game doesn't mark
# the Barrens chain done, and that chain is in the data for race 96 too.
page = shaman(96)
barrens = set(ns.GetZoneQuests(1413).values())
check(not any(i in barrens for i in FIRE_BARRENS + FIRE_CRUMBS),
      f"a Skyborne Shaman doesn't see the Barrens Call of Fire on The Barrens' page ({sorted(i for i in FIRE_BARRENS + FIRE_CRUMBS if i in barrens)})")
for qid in FIRE_ZEPHRAS:
    char["completed"][qid] = True
ns.RefreshCompleted()
barrens, zephras = set(ns.GetZoneQuests(1413).values()), set(ns.GetZoneQuests(2521).values())
page = set(ns.GetZoneQuests("class").values())
check(not any(i in barrens for i in FIRE_BARRENS + FIRE_CRUMBS),
      f"nor after finishing Zephras Isle's, with the Barrens chain not marked done ({sorted(i for i in FIRE_BARRENS + FIRE_CRUMBS if i in barrens)})")
check(all(i in zephras and i in page and ns.GetStatus(i) == S.DONE for i in FIRE_ZEPHRAS)
      and not any(i in page for i in FIRE_BARRENS + FIRE_CRUMBS),
      "Zephras Isle's Call of Fire shows as done, on Zephras Isle's page and the Class page")
durotar, mulgore = set(ns.GetZoneQuests(1411).values()), set(ns.GetZoneQuests(1412).values())
check(not any(i in durotar for i in EARTH["durotar"]) and not any(i in mulgore for i in EARTH["mulgore"]),
      "and Call of Earth's Durotar and Mulgore versions stay off those zones' pages for a Skyborne Shaman")
char["completed"] = lua.table()
ns.RefreshCompleted()
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
ns.RefreshPlayer()
ns.RefreshCompleted()

# --- Zone list colours by completion ---
PC = ns.ui.ProgressColor
def rgb(c):
    return tuple(round(v, 2) for v in c.values())
check(rgb(PC(0, 10)) == (0.62, 0.62, 0.62) and rgb(PC(0, 0)) == (0.62, 0.62, 0.62), "a zone you haven't started is grey")
check(rgb(PC(10, 10)) == (0.42, 0.83, 0.37), "a finished zone is green, as before")
check(rgb(PC(1, 100))[:2] == (1.0, 0.26), "just started is red")
check(rgb(PC(33, 100)) == (1.0, 0.55, 0.15), "a third done is orange")
check(rgb(PC(67, 100)) == (1.0, 0.88, 0.2), "two thirds done is yellow")
near = rgb(PC(99, 100))
check(near[1] > near[0] and abs(near[0] - 0.42) < 0.05, f"nearly done is all but green: {near}")
greens = [rgb(PC(d, 100))[1] for d in range(1, 68)]
reds = [rgb(PC(d, 100))[0] for d in range(1, 100)]
check(greens == sorted(greens) and reds == sorted(reds, reverse=True) and reds[-1] < 0.5,
      "the gradient runs steadily: red to yellow, then the red fades out to green")
ns.Toggle(True)
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

# --- Portal icon on quests picked up inside a dungeon or raid ---
check(ns.Quests[4342]["di"] == 242 and ns.Quests[3802]["di"] == 242, "quests given inside Blackrock Depths are marked as picked up there")
check(ns.Quests[7508]["z"] == 248 and ns.Quests[7508]["di"] == 234,
      "Quel'Serrar is filed under Onyxia's Lair, but marked as picked up in Dire Maul, where Lorekeeper Lydros gives it")
check(ns.Quests[4341]["di"] is None and ns.Quests[166]["di"] is None, "quests given outside (Ironforge, Westfall) aren't")
check(not any(q["di"] for q in ns.Quests.values() if q["z"] == -318), "nor are Tier 0.5 Sets quests, which are given in towns")
check(ns.Quests[2204]["di"] is None and ns.Quests[2861]["di"] is None,
      "nor quests with no giver recorded, which may be handed out in town (Restoring the Necklace, Tabetha's Task)")
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
ns.RefreshPlayer()
def tile_of(qid):
    t = [f for f in harness["all"].values() if f["questID"] == qid and f["sub"] is not None and f.IsShown(f)]
    return t[0] if t else None
ns.FocusQuest(3802)
t = tile_of(3802)
check(t is not None and t["icon"]["__texture"] == "Interface\\Icons\\Spell_Arcane_PortalUnderCity",
      "without the map's portal art, the box shows a portal icon")
g.C_Texture = lua.eval("{ GetAtlasInfo = function(a) if a == 'Dungeon' or a == 'Raid' then return {} end end }")
ns.Refresh()
t = tile_of(3802)
check(t["icon"]["__atlas"] == "Dungeon", "with it, the box shows the dungeon entrance swirl")
g.GameTooltip.lines = lua.table()
t["__scripts"]["OnEnter"](t)
check(any(str(l).startswith("Picked up inside ") for l in g.GameTooltip.lines.values()), "its tooltip says it's picked up inside the instance")
ns.ShowDetail(3802)
check(any(s.startswith("Picked up inside ") for s in detail_texts()), "and so do its details")
ns.HideDetail()
other = [f for f in harness["all"].values() if f["questID"] is not None and f["sub"] is not None and f.IsShown(f)
         and not ns.Quests[f["questID"]]["di"] and not ns.Quests[f["questID"]]["cl"]][0]
check(other["icon"]["__atlas"] is None and other["icon"]["__texture"] is not None, "other quests on the page keep their usual icon")
ns.Quests[3802]["di"] = 248  # as if given inside Onyxia's Lair
ns.Refresh()
check(tile_of(3802)["icon"]["__atlas"] == "Raid", "a quest picked up inside a raid gets the raid entrance swirl")
ns.Quests[3802]["di"] = 242
g.C_Texture = None

# --- Quests with Alliance and Horde versions (ATT's ResolveQuestData) ---
check(ns.Quests[8151]["l"] == 50 and list(ns.Quests[8151]["cl"].values()) == [3],
      "a faction-split quest keeps its level and class (8151 is a level 50 Hunter quest)")
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
ns.RefreshPlayer()
q = ns.Quests[8151]
check(q["m"] == 1453 and q["qg"] == 4205 and not ns.IsEligible(8151), "an Alliance character sees its Stormwind trainer, and a Warrior doesn't get the Hunter quest")
check(list(ns.Quests[687]["pre"].values()) == [653] and ns.Quests[687]["m"] == 1455, "its Alliance prerequisite and start (Ironforge)")
check(ns.Quests[2861]["m"] == 1453 and ns.Quests[2861]["l"] == 40, "Tabetha's Task starts in Stormwind for the Alliance")
char["race"], char["faction"] = 2, "Horde"
ns.RefreshPlayer()
q = ns.Quests[8151]
check(q["m"] == 1454 and q["qg"] == 3039, "a Horde character sees its Orgrimmar trainer")
check(list(ns.Quests[687]["pre"].values()) == [688] and ns.Quests[687]["m"] == 1417, "and the Horde prerequisite and start (Arathi Highlands)")
check(687 in list(ns.GetFollowOns(688).values()) and 687 not in list(ns.GetFollowOns(653).values()),
      "the storyline follows your faction's prerequisite")
char["race"], char["faction"] = 1, "Alliance"
ns.RefreshPlayer()

# --- Level ranges from the game's Looking for Group activities ---
g.EJ_GetInstanceInfo = lua.eval("""function(id) local n = { [63] = 'The Deadmines', [238] = 'The Stockade', [226] = 'Ragefire Chasm',
    [316] = 'Scarlet Monastery' }; return n[id] end""")
check(ns.GetLevelRange(213) is None, "without the game's activity list, no range is shown")
g.C_LFGList = lua.eval("""{
  GetAvailableActivities = function() return { 1, 2, 3, 4, 5, 6, 7, 8 } end,
  GetActivityInfoTable = function(id)
    local a = {
      { fullName = "Ragefire Chasm", minLevel = 0, minLevelSuggestion = 13, maxLevelSuggestion = 18 },
      { fullName = "Stormwind Stockades", minLevel = 0, minLevelSuggestion = 23, maxLevelSuggestion = 32 },
      { fullName = "Scarlet Monastery - Graveyard", minLevel = 0, minLevelSuggestion = 30, maxLevelSuggestion = 38 },
      { fullName = "Scarlet Monastery - Cathedral", minLevel = 0, minLevelSuggestion = 38, maxLevelSuggestion = 45 },
      { fullName = "Elwynn Forest", minLevel = 0, minLevelSuggestion = 1, maxLevelSuggestion = 10 },
      { fullName = "Hillsbrad Foothills", minLevel = 0, minLevelSuggestion = 18, maxLevelSuggestion = 34 },
      { fullName = "Custom", minLevel = 0, minLevelSuggestion = 0, maxLevelSuggestion = 0 },
      { fullName = "Warsong Gulch", minLevel = 0, minLevelSuggestion = 20, maxLevelSuggestion = 29 },
    }
    return a[id]
  end }""")
def rng(page):
    r = ns.GetLevelRange(page)
    return r if isinstance(r, tuple) else (r,)
check(rng(213) == (13, 18), f"Ragefire Chasm gets the game's 13-18: {rng(213)}")
check(rng(225) == (23, 32), "The Stockade matches the game's 'Stormwind Stockades'")
check(rng(435) == (30, 45), "Scarlet Monastery's wings make one range, 30-45")
real_map_info = g.C_Map.GetMapInfo
g.C_Map.GetMapInfo = lua.eval("""function(real) return function(id)
    if id == 1424 then return { name = "Hillsbrad Foothills", parentMapID = 1415 } end
    return real(id) end end""")(real_map_info)
check(rng(1429) == (1, 10) and rng(1424) == (18, 34), "zones get theirs too (Elwynn Forest 1-10, Hillsbrad Foothills 18-34)")
g.C_Map.GetMapInfo = real_map_info
check(rng(1453) == (None,) and rng("class") == (None,), "capital cities and the Class page show none")
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
ns.Toggle(True)
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Refresh()
row = [f for f in harness["all"].values() if f["zoneID"] == 1429 and f.IsShown(f)][0]
check(row["text"]["__text"] == "Elwynn Forest" and row["range"]["__text"] == "1-10",
      f"the zone list shows the range in its own column, so a long name can't push it off: {row['range']['__text']!r}")
g.GameTooltip.lines = lua.table()
row["__scripts"]["OnEnter"](row)
lines = [str(l) for l in g.GameTooltip.lines.values()]
check(lines[:2] == ["Elwynn Forest", "Levels 1-10"] and any("quests done" in l for l in lines),
      "hovering a zone shows its full name, range and progress")
check(frame["zoneSummary"]["__text"].startswith("Levels 1-10"), f"and so does the line above the graph: {frame['zoneSummary']['__text'][:30]!r}")
dungeons = [z for z in ns.ui.SortedZones().values() if z["instance"] == "dungeon"]
lows = [z["low"] for z in dungeons]
ranged = [l for l in lows if l is not None]
names = [str(z["name"]) for z in dungeons]
check(ranged and lows[:len(ranged)] == ranged and ranged == sorted(ranged) and all(l is None for l in lows[len(ranged):]),
      f"Dungeons are listed in level order, lowest first, then any without a range: {list(zip(names, lows))[:5]}")
check(names.index("The Stockade") < names.index("Scarlet Monastery") and names.index("Scarlet Monastery") < names.index("The Deadmines"),
      "so The Stockade (23) comes before Scarlet Monastery (30), and The Deadmines, which the game gave no range here, comes after")
unranged = [n for n, l in zip(names, lows) if l is None]
check(unranged == sorted(unranged), "dungeons without a range stay in name order")
not_dungeons = [str(z["name"]) for z in ns.ui.SortedZones().values() if z["instance"] == "raid"]
check(not_dungeons == sorted(not_dungeons), "raids are still listed by name")
g.C_LFGList = None

# --- Scarlet Monastery's wings, and breadcrumbs that lead nowhere you can go ---
check(ns.Quests[1051]["z"] == -361 and all(ns.Quests[i]["z"] == -362 for i in (1049, 1050, 1160, 1951)),
      "Graveyard and Library quests are on their own wing pages")
check(all(ns.Quests[i]["z"] == 435 for i in (1048, 1053, 1113)), "quests that span the monastery stay on its page")
g.EJ_GetInstanceInfo = lua.eval("function(id) if id == 316 then return 'Scarlet Monastery' end end")
check(ns.GetMapName(-361) == "Scarlet Monastery - Graveyard" and ns.GetMapName(-362) == "Scarlet Monastery - Library",
      f"wing pages are named after the instance and wing: {ns.GetMapName(-361)!r}")
g.C_LFGList = lua.eval("""{ GetAvailableActivities = function() return { 1, 2 } end,
  GetActivityInfoTable = function(id) return ({
    { fullName = "Scarlet Monastery - Graveyard", minLevelSuggestion = 26, maxLevelSuggestion = 36 },
    { fullName = "Scarlet Monastery - Library", minLevelSuggestion = 29, maxLevelSuggestion = 39 } })[id] end }""")
ns.ResetLevelRanges()
check(ns.GetLevelRange(-361) == (26, 36) and ns.GetLevelRange(-362) == (29, 39), "each wing gets its own range from the game")
check(ns.GetLevelRange(435) == (26, 39), "and the monastery's page spans them")
g.C_LFGList = None
g.IsInInstance = lua.eval("function() return true end")
g.EJ_GetInstanceForMap = lua.eval("function(m) if m == 302 then return 316 end return 0 end")
check(ns.CurrentInstancePage(302) == 435, "inside the monastery, LorePath opens on its page, not a wing")
g.IsInInstance, g.EJ_GetInstanceForMap = None, None

char["race"], char["class"], char["faction"] = 2, 1, "Horde"
ns.RefreshPlayer()
check(not ns.IsEligible(1198) and not ns.IsEligible(1200),
      "Horde don't see In Search of Thaelrid: it only leads to an Alliance quest")
char["race"], char["faction"] = 1, "Alliance"
ns.RefreshPlayer()
check(ns.IsEligible(1198) and ns.IsEligible(1200), "Alliance still do")

# --- Shift+click a reward to link it in chat ---
rewarded_q = next(qid for qid, q in sorted(ns.Quests.items()) if q["rw"] is not None and ns.IsEligible(qid))
ns.ShowDetail(rewarded_q)
item_btn = [f for f in harness["all"].values() if f["itemID"] is not None and f.IsShown(f)][0]
linked = lua.eval("{}")
g.HandleModifiedItemClick = lua.eval("function(t) return function(link) table.insert(t, link) end end")(linked)
g.C_Item.GetItemInfo = lua.eval("function(id) return 'Item' .. id, '|cff1eff00|Hitem:' .. id .. '|h[Item' .. id .. ']|h|r' end")
item_btn["__scripts"]["OnClick"](item_btn)
check(len(list(linked.values())) == 0, "a plain click does nothing")
harness["shift"] = True
item_btn["__scripts"]["OnClick"](item_btn)
check(list(linked.values()) == [f"|cff1eff00|Hitem:{item_btn['itemID']}|h[Item{item_btn['itemID']}]|h|r"],
      "clicking a reward hands its link to the game (Shift+click links it in chat)")
g.GameTooltip.lines = lua.table()
item_btn["__scripts"]["OnEnter"](item_btn)
check(any("Shift+click to link it in chat" in str(l) for l in g.GameTooltip.lines.values()), "its tooltip says so")
g.C_Item.GetItemInfo = lua.eval("function() return nil end")
before_chat = len(list(harness["chat"].values()))
item_btn["__scripts"]["OnClick"](item_btn)
check(len(list(linked.values())) == 1 and any("still loading" in str(m) for m in list(harness["chat"].values())[before_chat:]),
      "an item the game hasn't loaded yet says to try again")
harness["shift"] = False
g.HandleModifiedItemClick, g.C_Item.GetItemInfo = None, None
ns.HideDetail()

# --- Battlegrounds ---
BG = ns.InstanceZones
check(all(BG[m] == "battleground" for m in (1459, 1460, 1461, 2524)), "Alterac Valley, Warsong Gulch, Arathi Basin and Forever's battleground have pages")
wsg = list(ns.GetZoneQuests(1460).values())
check(len(wsg) > 0 and all(ns.Quests[i]["z"] == 1460 for i in wsg), f"Warsong Gulch's page has its quests ({len(wsg)} for this character)")
check(ns.ui.ZoneIcon(1460) == ns.ZoneIcons[1460], "battlegrounds use their own icons")
real_map_info = g.C_Map.GetMapInfo
g.C_Map.GetMapInfo = lua.eval("""function(real) return function(id)
    if id == 1460 then return { name = "Warsong Gulch", parentMapID = 0 } end
    return real(id) end end""")(real_map_info)
g.C_LFGList = lua.eval("""{ GetAvailableActivities = function() return { 1, 2 } end,
  GetActivityInfoTable = function(id) return ({
    { fullName = "Warsong Gulch", minLevelSuggestion = 20, maxLevelSuggestion = 29 },
    { fullName = "Elwynn Forest", minLevelSuggestion = 1, maxLevelSuggestion = 10 } })[id] end }""")
ns.ResetLevelRanges()
check(ns.GetLevelRange(1460) == (20, 29), "Warsong Gulch gets its range from the game")
check(ns.GetLevelRange(1429) == (1, 10), "and zones get theirs from the same list")
g.C_LFGList = None
g.C_Map.GetMapInfo = real_map_info
ns.ResetLevelRanges()

# --- AllTheThings' notes in quest details ---
check(ns.QuestNotes[635] == "If you miss out on picking up the necklace first, you can still complete this quest even after finishing the rest of the chain.", "notes are extracted with their quests")
check(len(list(ns.QuestNotes.keys())) > 50 and all(ns.Quests[k] is not None for k in ns.QuestNotes.keys()), "only for quests LorePath has")
ns.SetSetting("showSpoilers", False)
ns.ShowDetail(635)
texts = detail_texts()
check("Good to know" in texts and any(t.startswith("If you miss out") for t in texts), "the details show the note, even with spoilers hidden")
ns.ShowDetail(783)
check("Good to know" not in detail_texts(), "quests without a note don't get the heading")
char["race"], char["faction"] = 2, "Horde"
ns.RefreshPlayer()
ns.FocusQuest(635)
t = [f for f in harness["all"].values() if f["questID"] == 635 and f["sub"] is not None and f.IsShown(f)][0]
g.GameTooltip.lines = lua.table()
t["__scripts"]["OnEnter"](t)
lines = [str(l) for l in g.GameTooltip.lines.values()]
check("Good to know:" in lines and any(l.startswith("If you miss out") for l in lines), "the quest's tooltip in the graph shows the note too")
char["race"], char["faction"] = 1, "Alliance"
ns.RefreshPlayer()
ns.HideDetail()

# --- Slash commands: just /lp, /lp config and /lp share ---
before_chat = len(list(harness["chat"].values()))
g.SlashCmdList["LOREPATH"]("help")
out = [str(m) for m in list(harness["chat"].values())[before_chat:]]
cmds = [m for m in out if "/lp" in m]
check(len(cmds) == 3 and any("/lp config" in m for m in cmds) and any("/lp share" in m for m in cmds),
      "/lp help lists three commands: /lp, /lp config and /lp share")
for gone in ("here", "search garrick", "quest", "minimap", "repeatable", "spoilers", "levels", "settings", "options", "find x"):
    before_chat = len(list(harness["chat"].values()))
    g.SlashCmdList["LOREPATH"](gone)
    if not any("commands:" in str(m) for m in list(harness["chat"].values())[before_chat:]):
        check(False, f"/lp {gone} should just show the help now")
check(True, "removed commands just show the help")
share_button = harness["frames"]["LorePathSettingsPanel"]["shareButton"]
g.LorePathDB["questCache"] = lua.eval("{}")
before_chat = len(list(harness["chat"].values()))
share_button["__scripts"]["OnClick"](share_button)
check(any("Nothing new to share" in str(m) for m in list(harness["chat"].values())[before_chat:]),
      "the settings page has a Share quest text button")

# --- Quest icons: portal, then class, profession, starting item ---
check(ns.Quests[6564]["si"] == 16790, "a quest started by a dropped item records it (Allegiance to the Old Gods: Damp Note)")
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
char["completed"], char["log"] = lua.table(), lua.table()
g.GetProfessions = lua.eval("function() return 1, nil end")
g.GetProfessionInfo = lua.eval("function(i) if i == 1 then return 'Leatherworking', 133611, 300, 300, 0, 0, 165 end end")
ns.RefreshPlayer(); ns.RefreshCompleted()
ns.Toggle(True)
def icon_of(qid):
    t = [f for f in harness["all"].values() if f["questID"] == qid and f["sub"] is not None and f.IsShown(f)]
    return t[0]["icon"] if t else None
lw = next(i for i in ns.GetZoneQuests("prof:165").values() if not ns.Quests[i]["di"] and not ns.Quests[i]["cl"])
ns.FocusQuest(lw)
check(icon_of(lw)["__texture"] == 133611, "profession quests show the profession's icon")
item_q = next(qid for qid, q in sorted(ns.Quests.items()) if q["si"] and not q["di"] and not q["cl"] and not q["sk"] and ns.IsEligible(qid))
g.C_Item.GetItemIconByID = lua.eval("function(id) return 900000 + (id % 1000) end")
ns.FocusQuest(item_q)
check(icon_of(item_q)["__texture"] == 900000 + ns.Quests[item_q]["si"] % 1000, f"a quest started by an item shows the item's icon ({item_q})")
g.C_Item.GetItemIconByID = None
ns.Refresh()
check(icon_of(item_q)["__texture"] in ("Interface\\Icons\\INV_Misc_Note_01", "Interface\\Icons\\INV_Letter_15"),
      "without the item's icon, it falls back to the usual one")
ns.FocusQuest(7508)
check(ns.Quests[7508]["cl"] is not None and icon_of(7508)["__texture"] == "Interface\\Icons\\Spell_Arcane_PortalUnderCity",
      "a class quest picked up inside an instance shows the portal: it comes first")
g.GetProfessions = lua.eval("function() return nil end")
ns.RefreshPlayer()

# --- Finished zone list sections start collapsed ---
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Toggle(True)
def class_row():
    rows = [f for f in harness["all"].values() if f["zoneID"] == "class" and f.IsShown(f)]
    return rows[0] if rows else None
def class_heading():
    return [f for f in harness["all"].values() if f["continent"] == "Class" and f["zoneID"] is None and f.IsShown(f)][0]
check(class_row() is not None, "an unfinished Class section starts open")
for qid in ns.GetZoneQuests("class").values():
    char["completed"][qid] = True
ns.Refresh()
check(class_row() is None and class_heading()["collapsed"] is True, "once every class quest is done, the Class section starts collapsed")
h = class_heading()
h["__scripts"]["OnClick"](h)
check(class_row() is not None and g.LorePathDB["collapsedContinents"]["Class"] is False, "opening it yourself is remembered")
ns.Refresh()
check(class_row() is not None, "and it stays open")
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Refresh()
check(class_row() is None, "with the choice cleared it's collapsed again")
h = class_heading()
h["__scripts"]["OnClick"](h)
class_row()["__scripts"]["OnClick"](class_row())   # view the Class page
g.LorePathDB["collapsedContinents"] = lua.table()  # forget the choice
ns.Refresh()
check(class_row() is not None and class_heading()["collapsed"] is False,
      "a finished section holding the page you're on stays open")
char["completed"] = lua.table()
ns.RefreshCompleted()
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Refresh()

# --- Where a quest's starting item comes from ---
QS = ns.QuestStarts
check(QS[6564][1]["n"] == "Blackfathom Tide Priestess" and QS[6564][1]["i"] == 221 and QS[6564][1]["m"] is None,
      "the Damp Note drops from Blackfathom Tide Priestesses inside Blackfathom Deeps, not at their outdoor spawns")
check(QS[123][1]["m"] == 1429 and QS[123][1]["x"] is not None, "an outdoor source has a map position (Gruff Swiftbite, Elwynn Forest)")
g.EJ_GetInstanceInfo = lua.eval("function(id) if id == 227 then return 'Blackfathom Deeps' end end")
ns.ShowDetail(6564)
texts = detail_texts()
srcs = [f for f in harness["all"].values() if f["source"] is not None and f.IsShown(f)]
check("Starts from an item:" in texts and "Start location unknown." not in texts, "the details say the quest starts from an item")
check(len(srcs) == 1 and srcs[0]["what"]["__text"] == "Dropped by Blackfathom Tide Priestess (33%)"
      and srcs[0]["where"]["__text"] == "in Blackfathom Deeps", f"and what drops it, and where: {[srcs[0]['what']['__text'], srcs[0]['where']['__text']] if srcs else None}")
ns.ShowDetail(123)
src = [f for f in harness["all"].values() if f["source"] is not None and f.IsShown(f)][0]
harness["waypoint"] = None
src["__scripts"]["OnClick"](src)
check(harness["waypoint"] is not None and harness["waypoint"]["m"] == 1429, "clicking an outdoor source sets a waypoint at it")
ns.HideDetail()
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
ns.RefreshPlayer()
ns.Toggle(True)
ns.FocusQuest(123)
t = [f for f in harness["all"].values() if f["questID"] == 123 and f["sub"] is not None and f.IsShown(f)][0]
g.GameTooltip.lines = lua.table()
t["__scripts"]["OnEnter"](t)
lines = [str(l) for l in g.GameTooltip.lines.values()]
check(any(l.startswith("Starts from ") for l in lines) and any("Dropped by Gruff Swiftbite" in l for l in lines),
      "the quest's tooltip says what item starts it and what drops it")

# --- World map pins (issue #11) ---
toc = open(os.path.join(ROOT, "LorePath.toc")).read().split()
check("Pins.lua" in toc and "Pins.xml" in toc and toc.index("Pins.lua") < toc.index("Pins.xml"),
      "the TOC loads Pins.lua, then Pins.xml (whose template names Pins.lua's mixin)")
check(harness["templates"]["LorePathQuestPinTemplate"] == "LorePathQuestPinMixin" and g.LorePathQuestPinMixin is not None,
      "Pins.xml's pin template uses the mixin Pins.lua defines")
WM = g.WorldMapFrame
PIN_T = "LorePathQuestPinTemplate"
def pins():
    return [p for p in harness.Pins(PIN_T).values() if p.IsShown(p)]
def pinned_ids():
    return sorted(qid for p in pins() for qid in p["group"]["quests"].values())
def pin_for(qid):
    return next((p for p in pins() if qid in list(p["group"]["quests"].values())), None)

ns.HideDetail()
frame.Hide(frame)
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 5, 1429
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer()
ns.RefreshCompleted()
check(ns.mapPinsProvider is not None and len(list(WM["__providers"].values())) == 1, "LorePath adds one data provider to the world map")
check(harness["frames"]["LorePathMapPinsToggle"] is None, "there's no tick box on the map")
check(ns.mapPinsMenu == "menu", "the filters go in the world map's filter menu (Menu API)")
FILTER_TEXTS = ["Quests at your level", "Low-level quests", "Quests above your level"]
FILTER_KEYS = ["mapPinsCurrent", "mapPinsLow", "mapPinsHigh"]
def filter_boxes():
    entries = list(harness.BuildMenu("MENU_WORLD_MAP_TRACKING").values())
    return entries, [e for e in entries if e["kind"] == "checkbox"]
entries, boxes = filter_boxes()
check(any(e["kind"] == "title" and e["text"] == "LorePath quests" for e in entries) and [e["text"] for e in boxes] == FILTER_TEXTS,
      f"under a 'LorePath quests' heading, three filters: {[e['text'] for e in boxes]}")
check([e["isChecked"]() for e in boxes] == [True, False, False]
      and (g.LorePathDB["mapPinsCurrent"], g.LorePathDB["mapPinsLow"], g.LorePathDB["mapPinsHigh"]) == (True, False, False),
      "by default only 'Quests at your level' is on")
WM.SetMapID(WM, 1429)
WM.Show(WM)

def expected_on(map_id, bands):
    ids = []
    for qid, q in ns.Quests.items():
        if q["m"] == map_id and q["x"] is not None and qid in list(ns.GetZoneQuests(q["z"]).values()) and ns.PinBand(qid) in bands:
            ids.append(qid)
    return sorted(ids)
B = ns.PIN_BAND
current = expected_on(1429, (B.CURRENT,))
check(len(current) > 5 and pinned_ids() == current, f"by default Elwynn pins only quests at your level ({len(current)})")
# The rest of these checks run with all three on.
ns.SetSetting("mapPinsLow", True)
ns.SetSetting("mapPinsHigh", True)
want = expected_on(1429, (B.CURRENT, B.LOW, B.HIGH))
got = pinned_ids()
print(f"Elwynn at level 5: {len(got)} quests pinned in {len(pins())} pins")
check(got == want and len(want) > len(current), f"with all three on, Elwynn pins every quest starting there ({len(got)} vs {len(want)})")
check(all(ns.GetStatus(q) in (S.AVAILABLE, S.REPEATABLE) for q in current), "'at your level' ones are quests you can pick up")
check(len(set(got)) == len(got), "each quest has one pin")
p783 = pin_for(783)
check(p783 is not None and p783["icon"]["__texture"] == "Interface\\GossipFrame\\AvailableQuestIcon", "783 gets a '!' pin")
check(p783 is not None and p783["icon"]["__desaturated"] is False and tuple(p783["icon"]["__vertex"].values()) == (1, 1, 1),
      "in the '!''s own gold: a level-1 quest at level 5 is at your level")
g783 = p783["group"]
check(abs(p783["__pos"][1] - g783["x"] / 100) < 1e-9 and abs(p783["__pos"][2] - g783["y"] / 100) < 1e-9, "the pin sits at its start (map fractions)")
groups = [p["group"] for p in pins()]
close = [(a, b) for i, a in enumerate(groups) for b in groups[i + 1:] if (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 <= 1.5 ** 2]
check(not close, "no two pins sit on top of each other")
multi = next((p for p in pins() if len(list(p["group"]["quests"].values())) > 1), None)
check(multi is not None and multi["count"]["__text"] == str(len(list(multi["group"]["quests"].values()))),
      "quests at one spot share a pin, which shows how many")
single = next(p for p in pins() if len(list(p["group"]["quests"].values())) == 1)
check(all(single["count"]["__text"] == "" for single in [single]), "a pin for one quest shows no count")

# Tooltip and click
def hover(p):
    g.GameTooltip.lines = lua.table()
    p["__scripts"]["OnEnter"](p)
    return [str(l) for l in g.GameTooltip.lines.values()]
sid = single["group"]["quests"][1]
lines = hover(single)
check(lines[0] == ns.GetQuestNameOrID(sid) and any(l.startswith("Requires level") for l in lines) and any(l.startswith("Starts in") for l in lines),
      "a pin's tooltip is the quest's usual tooltip")
check("Click to set a waypoint here." in lines and "Shift+click to open it in LorePath." in lines
      and "Click for details." not in lines and not any("Ctrl+click" in l for l in lines),
      "with the pin's own click hints instead of the window's")
mlines = hover(multi)
n = len(list(multi["group"]["quests"].values()))
check(mlines[0] == f"{n} quests" and sum(1 for l in mlines if l.startswith("[")) == n, f"a shared pin's tooltip lists its {n} quests")
harness["waypoint"] = None
single["__scripts"]["OnMouseUp"](single, "LeftButton")
sq = ns.Quests[sid]
check(harness["waypoint"] is not None and harness["waypoint"]["m"] == 1429 and abs(harness["waypoint"]["x"] - sq["x"] / 100) < 1e-9,
      "clicking a pin sets the waypoint where its quest starts")
harness["waypoint"] = None
multi["__scripts"]["OnMouseUp"](multi, "LeftButton")
mg = multi["group"]
check(harness["waypoint"] is not None and abs(harness["waypoint"]["x"] - mg["x"] / 100) < 1e-9 and "and %d more" % (n - 1) in harness["chat"][len(harness["chat"])],
      "clicking a shared pin sets the waypoint at it")
harness["waypoint"] = None
single["__scripts"]["OnMouseUp"](single, "RightButton")
check(harness["waypoint"] is None, "right-clicking a pin does nothing (the map uses it to zoom out)")
harness["shift"] = True
single["__scripts"]["OnMouseUp"](single, "LeftButton")
harness["shift"] = False
check(harness["waypoint"] is None and frame.IsShown(frame) and ns.detailQuest == sid and ns.focusedQuest == sid,
      "Shift+clicking a pin opens its quest in LorePath, with its details")
ns.HideDetail()
frame.Hide(frame)

# Only the map being viewed
WM.SetMapID(WM, 1415)
check(len(pins()) == 0, "the Eastern Kingdoms continent map shows no pins")
WM.SetMapID(WM, 1429)
check(pinned_ids() == want, "back on Elwynn, its pins return")

# The three filters
def box(text):
    return next(e for e in filter_boxes()[1] if e["text"] == text)
high = expected_on(1429, (B.HIGH,))
check(high and all(q in pinned_ids() for q in high) and all(ns.GetLockReason(q) == "level" for q in high),
      f"with that filter on, quests above your level are pinned ({len(high)})")
hp = next(p for p in pins() if p["group"]["band"] == B.HIGH)
check(hp["icon"]["__desaturated"] is True and hp["icon"]["__vertex"][1] == 1 and hp["icon"]["__vertex"][2] < 0.5,
      "as a red '!'")
box("Quests above your level")["onClick"]()
check(g.LorePathDB["mapPinsHigh"] is False and not box("Quests above your level")["isChecked"]()
      and not any(q in pinned_ids() for q in high), "unticking 'Quests above your level' in the map's menu removes them")
box("Quests above your level")["onClick"]()
check(all(q in pinned_ids() for q in high), "and ticking it brings them back")

char["level"] = 30
ns.RefreshPlayer()
WM.SetMapID(WM, 1429)
p783 = pin_for(783)
check(ns.PinBand(783) == B.LOW and p783 is not None and p783["icon"]["__desaturated"] is True
      and p783["icon"]["__vertex"][1] == p783["icon"]["__vertex"][2] == p783["icon"]["__vertex"][3],
      "at level 30, 783 is a low-level quest: a grey '!'")
box("Low-level quests")["onClick"]()
check(783 not in pinned_ids() and g.LorePathDB["mapPinsLow"] is False, "unticking 'Low-level quests' removes it")
box("Low-level quests")["onClick"]()
box("Quests at your level")["onClick"]()
check(g.LorePathDB["mapPinsCurrent"] is False and all(p["group"]["band"] != B.CURRENT for p in pins()) and 783 in pinned_ids(),
      "unticking 'Quests at your level' leaves the low-level ones")
box("Quests at your level")["onClick"]()
char["level"] = 5
ns.RefreshPlayer()
WM.SetMapID(WM, 1429)
check(pinned_ids() == want, "back at level 5, the same pins as before")

char["log"][783] = True
WM.SetMapID(WM, 1429)
check(783 not in pinned_ids(), "a quest in your log loses its '!'")
char["log"][783] = None
WM.SetMapID(WM, 1429)

# Refreshing on events
harness.RunTimers()
check(783 in pinned_ids(), "783 is pinned before it's turned in")
char["completed"][783] = True
harness.Fire("QUEST_TURNED_IN", 783)
harness.RunTimers()
check(783 not in pinned_ids(), "turning a quest in removes its pin")
before = len(pinned_ids())
char["level"] = 10
harness.Fire("PLAYER_LEVEL_UP", 10)
harness.RunTimers()
check(len(pinned_ids()) == before and any(ns.PinBand(q) == B.CURRENT for q in high), "levelling up redraws the pins: red ones turn gold")
WM.Hide(WM)
char["completed"] = lua.table()
harness.Fire("QUEST_REMOVED", 1)
harness.RunTimers()
check(783 not in pinned_ids(), "while the map is closed, pins wait for it to open")
WM.Show(WM)
check(783 in pinned_ids(), "and redraw when it does")

# Off again
for key in FILTER_KEYS:
    ns.SetSetting(key, False)
check(len(pins()) == 0 and not any(e["isChecked"]() for e in filter_boxes()[1]), "with all three off, no pins, and the menu shows them unticked")
for key in FILTER_KEYS:
    ns.SetSetting(key, True)
check(harness["frames"]["LorePathSettingsPanel"] is not None, "the settings page exists")
labels = [str(f["__text"]) for f in harness["all"].values() if f["__text"]]
check(all(l in labels for l in ("Quests at your level (gold)", "Low-level quests (grey)", "Quests above your level (red)")),
      "the settings page has the same three filters")

# The settings page: in a scroll frame, under headings, with the map filters nested.
sp = harness["frames"]["LorePathSettingsPanel"]
scroll = harness["frames"]["LorePathSettingsScroll"]
check(scroll is not None and scroll["__scrollChild"] is not None and same(scroll["__scrollChild"], sp["body"]),
      "the settings page scrolls: everything is in a scroll frame's content")
page_texts = [f for f in harness["all"].values() if f["__kind"] == "FontString" and f["__parent"] is not None and same(f["__parent"], sp["body"])]
headings = [str(f["__text"]) for f in page_texts if str(f["__text"]) in ("Window", "Quests", "World map")]
check(headings == ["Window", "Quests", "World map"], f"settings are grouped under headings: {headings}")
def left_of(label):
    fs = next(f for f in harness["all"].values() if f["__text"] == label and f["__parent"] is not None and f["__parent"]["__kind"] != "FontString")
    cb = fs["__parent"]
    return next(p[4] for p in cb["__points"].values() if p[1] == "LEFT")
nested = [left_of(t) for t in ("Quests at your level (gold)", "Low-level quests (grey)", "Quests above your level (red)")]
check(len(set(nested)) == 1 and nested[0] > left_of("Show spoilers"), f"the map filters are indented under 'Show quests on the map': {nested} vs {left_of('Show spoilers')}")
check(any(str(f["__text"]) == "Show quests on the map" for f in page_texts), "under a 'Show quests on the map' label")
g.LorePathDB["showMapPins"] = False
ns.InitDB()
check(g.LorePathDB["showMapPins"] is None, "1.2.0-beta1's old pin setting is cleared")

# Clients whose filter menu is a UIDropDownMenu: the filters go in through the button's InitializeDropDown.
saved_menu = g.Menu
g.Menu = None
added = lua.eval("{}")
g.UIDropDownMenu_CreateInfo = lua.eval("function() return {} end")
g.UIDropDownMenu_AddButton = lua.eval("function(info) table.insert(ADDED, info) end")
lua.globals().ADDED = added
g.hooksecurefunc = lua.eval("function(t, name, fn) local old = t[name]; t[name] = function(...) old(...); fn(...) end end")
filter_button = lua.eval("{ InitializeDropDown = function() end }")
WM["overlayFrames"] = lua.eval("{}")
WM["overlayFrames"][1] = filter_button
ns3 = lua.table()
load_file(open(os.path.join(ROOT, "Pins.lua")).read(), "Pins.lua", ns3)
ns3.AttachMapPins()
filter_button.InitializeDropDown(filter_button)
texts = [a["text"] for a in added.values()]
check(ns3["mapPinsMenu"] == "dropdown" and texts == ["LorePath quests"] + FILTER_TEXTS, f"older clients get the filters in the dropdown: {texts}")
g.Menu, g.UIDropDownMenu_CreateInfo, g.UIDropDownMenu_AddButton, g.hooksecurefunc = saved_menu, None, None, None
WM["overlayFrames"] = None
WM["__providers"] = lua.table_from([ns.mapPinsProvider])

# Without the map canvas API, Pins.lua does nothing (and doesn't error)
saved_wm, saved_mixin = g.WorldMapFrame, g.LorePathQuestPinMixin
g.WorldMapFrame = None
ns2 = lua.table()
load_file(open(os.path.join(ROOT, "Pins.lua")).read(), "Pins.lua", ns2)
check(ns2.AttachMapPins() is None, "a client without WorldMapFrame:AddDataProvider gets no pins and no error")
g.WorldMapFrame, g.LorePathQuestPinMixin = saved_wm, saved_mixin

g.SlashCmdList["LOREPATH"]("pins")
check(any("/lp config" in str(l) for l in list(harness["chat"].values())[-4:]), "there's no /lp pins: it prints the usual help")

# --- Attunements (issue #16) ---
atts = {a["id"]: a for a in ns.Attunements.values()}
missing = [(a, s["quest"]) for a, att in atts.items() for s in att["steps"].values() if s["quest"] and ns.Quests[s["quest"]] is None]
check(not missing, f"every attunement quest is in WoW Forever's data: missing {missing}")
check(all(ns.InstanceZones[att["instance"]] is not None for att in atts.values()), "every attunement names a dungeon or raid page")
def rewards(qids):
    return {i for q in qids for i in (ns.Quests[q]["rw"] or lua.table()).values()}
keys_ok = all(s["item"] in rewards([t["quest"] for t in att["steps"].values() if t["quest"]])
              for att in atts.values() for s in att["steps"].values() if s["item"])
check(keys_ok, "each attunement's key is a reward of one of its quests")

char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
ony = list(ns.GetZoneQuests("att:onyxia").values())
check(4182 in ony and 6502 in ony and 4903 not in ony, f"an Alliance character's Onyxia page has the Alliance chain only ({len(ony)} quests)")
sls, others = ns.BuildStorylines("att:onyxia")
sls = list(sls.values())
zones = {ns.Quests[n["id"]]["z"] for n in sls[0]["nodes"].values()} if sls else set()
check(len(sls) == 1 and len(list(sls[0]["nodes"].values())) == len(ony) and len(zones) > 1,
      f"it's one storyline across zones and instances: {len(sls)} storyline, zones {sorted(zones)}")
check(ns.GetMapName("att:onyxia") == "Onyxia's Lair" and ns.GetLevelRange("att:onyxia") == ns.GetLevelRange(248),
      "the page is named after the raid, with the raid's level range")
reqs = list(ns.GetAttunementRequirements("att:onyxia").values())
check(len(reqs) == 1 and reqs[0]["kind"] == "item" and reqs[0]["item"] == 16309 and reqs[0]["done"] is False,
      "its key, the Drakefire Amulet, is a step, not done without it")
done, total, _ = ns.GetZoneProgress("att:onyxia")
check((done, total) == (0, len(ony) + 1), f"progress counts the quests and the key: {done} / {total}")
g.C_Item.GetItemCount = lua.eval("function(id, bank) if id == 16309 and bank then return 1 end return 0 end")
for qid in ony:
    char["completed"][qid] = True
ns.RefreshCompleted()
done, total, _ = ns.GetZoneProgress("att:onyxia")
check(ns.GetAttunementRequirements("att:onyxia")[1]["done"] is True and done == total,
      f"with every quest done and the amulet in your bank, it's complete: {done} / {total}")
g.C_Item.GetItemCount = None
char["completed"] = lua.table()
ns.RefreshCompleted()

char["race"], char["faction"] = 2, "Horde"
ns.RefreshPlayer()
ony_h = list(ns.GetZoneQuests("att:onyxia").values())
scholo_h = list(ns.GetZoneQuests("att:scholomance").values())
check(4903 in ony_h and 6602 in ony_h and 4182 not in ony_h and 5511 in scholo_h and 5505 not in scholo_h,
      "a Horde character gets the Horde chains")
char["race"], char["faction"] = 1, "Alliance"
ns.RefreshPlayer()
groups = dict((gr["name"], list(gr["pages"].values())) for gr in ns.GetSpecialGroups().values())
check(groups.get("Attunements") == ["att:onyxia", "att:ubrs", "att:scholomance", "att:shadowforge"],
      f"the zone list gets an Attunements group: {groups.get('Attunements')}")
char["level"] = 10
ns.RefreshPlayer()
check(len(list(ns.GetZoneQuests("att:onyxia").values())) > 0, "it shows at any level, as a goal")
char["level"] = 60
ns.RefreshPlayer()

# In the window.
g.LorePathDB["collapsedContinents"] = lua.table()
ns.Toggle(True)
ns.Refresh()
heads = [f["continent"] for f in sorted([f for f in harness["all"].values() if f["continent"] is not None and f["zoneID"] is None and f.IsShown(f)],
                                       key=lambda f: f["top"])]
check("Attunements" in heads and heads.index("Attunements") < heads.index("Dungeons"), f"an Attunements heading sits with Class and Professions: {heads[:4]}")
row = page_row("att:onyxia")
check(row is not None and row["text"]["__text"] == "Onyxia's Lair" and row["icon"]["__texture"] == ns.InstanceInfo[248]["ic"],
      "Onyxia's Lair is listed with the raid's icon")
row["__scripts"]["OnClick"](row)
canvas_texts = [str(f["__text"]) for f in harness["all"].values() if f["__kind"] == "FontString" and f.IsShown(f) and f["__text"] is not None]
check(frame["zoneTitle"]["__text"] == "Onyxia's Lair" and "0 / 17 steps done" in frame["zoneSummary"]["__text"],
      f"clicking it shows the page, counting steps: {frame['zoneSummary']['__text']}")
check("Also needed" in canvas_texts and any("Item16309" in t and "ReadyCheck-NotReady" in t for t in canvas_texts),
      "the key is listed above the quests, not ticked yet")
ns.FocusQuest(4182)
check(frame["zoneTitle"]["__text"] == "Onyxia's Lair", "focusing one of its quests stays on the attunement page")
ns.Toggle(False)

# --- Amongst the Ruins, in the data twice (908 and 6921) ---
char["race"], char["class"], char["faction"], char["level"] = 2, 1, "Horde", 25
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
def ruins():
    return sorted(q for q in ns.GetZoneQuests(221).values() if q in (908, 6921))
check(len(ruins()) == 1, f"Blackfathom Deeps shows Amongst the Ruins once: {ruins()}")
char["log"][6921] = True
check(ruins() == [6921], "the one in your log, when you have 6921")
char["log"] = lua.table()
char["log"][908] = True
check(ruins() == [908], "or 908")
char["log"] = lua.table()

# Call of Air: Orgrimmar's (1531) and Thunder Bluff's (1532) are one quest.
char["class"] = 7
def air(race):
    char["race"] = race
    ns.RefreshPlayer()
    return sorted(q for q in ns.GetZoneQuests("class").values() if q in (1531, 1532))
check(air(2) == [1531] and air(6) == [1532], f"a Horde Shaman sees Call of Air once: an orc Orgrimmar's, a tauren Thunder Bluff's ({air(2)}, {air(6)})")
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
ns.RefreshPlayer()

# A shared map pin takes its best quest's colour: gold if any is at your level, else grey, else red.
mixed, wrong = 0, []
for race, faction, maps in ((1, "Alliance", (1429, 1436, 1433, 1453)), (2, "Horde", (1411, 1413, 1454))):
    char["race"], char["faction"] = race, faction
    for level in (8, 15, 25):
        char["level"] = level
        for m in maps:
            for grp in ns.MapPinGroups(m).values():
                bands = [ns.PinBand(q) for q in grp["quests"].values()]
                if len(set(bands)) > 1:
                    mixed += 1
                if grp["band"] != min(bands):
                    wrong.append((m, level, list(grp["quests"].values())))
check(mixed > 0 and not wrong, f"a pin shared by quests of different levels shows the best: gold, else grey, else red ({mixed} mixed pins, wrong: {wrong[:3]})")
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
ns.RefreshPlayer()

# --- Quests in the data twice (runs on every AllTheThings sync) ---
# Two quests with the same name on one page, that one character could have
# together, and that don't lead to each other, show twice: once as done or in
# your log, once as still available (Amongst the Ruins, 908 and 6921). A new one
# fails here, so a person decides once: add it to EXTRA_VERSIONS in Core.lua if
# it's one quest twice, or to SEPARATE below if they really are two quests.
import re as _re
from collections import defaultdict
SEPARATE = [  # same name, but really different quests (or known data gaps, left alone for now)
    {1380, 1381},              # Khan Hratha: one for each centaur faction (Magram, Gelkis)
    {1471, 1474, 1795},        # The Binding (Undercity): Voidwalker, Succubus, Felhunter
    {1504, 1513, 1795},        # The Binding (Orgrimmar)
    {1689, 1739, 1795},        # The Binding (Stormwind)
    {1685, 1717},              # Gakin's Summons: the Voidwalker and Succubus breadcrumbs
    {7802, 7807}, {7803, 7808}, {7804, 7809}, {7805, 7811},  # cloth for Ironforge and for Gnomeregan
    {7826, 7833}, {7827, 7834}, {7831, 7835}, {7824, 7836},  # cloth for Orgrimmar and for the Darkspear
    {1471, 1474, 1504, 1513},  # The Binding: Undercity's and Orgrimmar's are different demons
    {2951, 2952, 4601, 4602, 4605, 4606},  # The Sparklematic 5200!: one for each item you clean, with its second step
    {2278, 2279, 2280, 2439, 2440},  # The Platinum Discs: one chain, but the data doesn't link 2278 to the item it gives you
]

def quest_titles():
    out = {}
    for name in ("Data/QuestText.lua", "Data/CommunityText.lua"):
        text = open(os.path.join(ROOT, name), encoding="utf-8").read()
        for m in _re.finditer(r'^\[(\d+)\]=\{t="((?:[^"\\]|\\.)*)"', text, _re.M):
            out.setdefault(int(m.group(1)), m.group(2))
    return out

def plain_quests():
    def ids(v):
        return set(v.values()) if v is not None else set()
    out = {}
    for qid, q in ns.Quests.items():
        out[qid] = {"z": q["z"], "f": q["f"], "rc": ids(q["rc"]), "cl": ids(q["cl"]), "sk": ns.ProfessionOf(q),
                    "pre": ids(q["pre"]), "nx": ids(q["nx"]), "alt": ids(q["alt"]), "rp": q["rp"] is not None}
    return out

# Which factions can do a quest: its own, or its races' (1 Horde, 2 Alliance).
RACE_FACTION = {1: 2, 3: 2, 4: 2, 7: 2, 95: 2, 2: 1, 5: 1, 6: 1, 8: 1, 96: 1}
def factions_of(q):
    if q["f"]:
        return {q["f"]}
    return {RACE_FACTION[r] for r in q["rc"] if r in RACE_FACTION}

# Quests that lead to each other, through prerequisites and breadcrumbs.
def leads_to(quests):
    reach = {}
    def reaches(a):
        if a not in reach:
            seen, todo = set(), [a]
            while todo:
                x = todo.pop()
                for y in quests[x]["pre"] | quests[x]["nx"]:
                    if y in quests and y not in seen:
                        seen.add(y)
                        todo.append(y)
            reach[a] = seen
        return reach[a]
    return reaches

def find_duplicates(quests, titles, extra_versions, separate):
    """Groups of quest IDs one character could see twice under one name, on one
    page: a zone or instance, the Class page, or a profession's page."""
    # Versions of each other (alt in the data, or EXTRA_VERSIONS), joined up.
    parent = {}
    def root(a):
        while parent.get(a, a) != a:
            a = parent[a]
        return a
    for qid, q in quests.items():
        for other in q["alt"] | set(extra_versions.get(qid, ())):
            parent[root(qid)] = root(other)
    reaches = leads_to(quests)
    known = [set(s) for s in separate]
    # Quests in one storyline are steps, even with the same name (Call of
    # Water's two steps after 1534). And a page shows one version of each quest,
    # hiding the steps after the versions it doesn't show (OneVersionEach in
    # Core.lua). So two quests whose chains share a quest, or versions of one,
    # never show as one quest twice.
    chain_roots = {}
    def roots_of(a):
        if a not in chain_roots:
            chain_roots[a] = {root(x) for x in reaches(a) | {a}}
        return chain_roots[a]

    def together(a, b):
        qa, qb = quests[a], quests[b]
        if qa["rp"] or qb["rp"]:
            return False  # repeatables, and first-time quests beside their repeatable version
        if roots_of(a) & roots_of(b):
            return False
        fa, fb = factions_of(qa), factions_of(qb)
        if fa and fb and not (fa & fb):
            return False
        if qa["rc"] and qb["rc"] and not (qa["rc"] & qb["rc"]):
            return False
        if qa["cl"] and qb["cl"] and not (qa["cl"] & qb["cl"]):
            return False
        return not any(a in s and b in s for s in known)

    pages = defaultdict(lambda: defaultdict(list))
    for qid, q in quests.items():
        if qid not in titles:
            continue
        pages[("zone", q["z"])][titles[qid]].append(qid)
        if q["cl"]:
            pages[("class",)][titles[qid]].append(qid)
        if q["sk"]:
            pages[("prof", q["sk"])][titles[qid]].append(qid)
    found = set()
    for page in pages.values():
        for ids in page.values():
            ids = sorted(ids)
            for i, a in enumerate(ids):
                for b in ids[i + 1:]:
                    if together(a, b):
                        found.add((a, b))
    return sorted(found)

TITLES = quest_titles()
PLAIN = plain_quests()
EXTRA = {k: list(v.values()) for k, v in ns.EXTRA_VERSIONS.items()}
dupes = find_duplicates(PLAIN, TITLES, EXTRA, SEPARATE)
def describe(qid):
    q = PLAIN[qid]
    return f"{qid} (zone {q['z']}, faction {q['f']}, races {sorted(q['rc'])}, classes {sorted(q['cl'])})"
for a, b in dupes:
    print(f"  shown twice? {TITLES[a]!r}: {describe(a)} and {describe(b)}")
check(not dupes, f"no quest shows twice under one name ({len(dupes)} pairs, listed above)"
      + (": add each to EXTRA_VERSIONS in Core.lua (one quest twice) or SEPARATE in run_tests.py (really two quests)" if dupes else ""))

# The check catches what it should, and its lists don't go stale.
without_ruins = {k: v for k, v in EXTRA.items() if k != 6921}
check((908, 6921) in find_duplicates(PLAIN, TITLES, without_ruins, SEPARATE),
      "without its EXTRA_VERSIONS entry, Amongst the Ruins is caught")
without_air = {k: v for k, v in EXTRA.items() if k != 1531}
check((1531, 1532) in find_duplicates(PLAIN, TITLES, without_air, SEPARATE), "and so is Call of Air")
fake = dict(PLAIN)
fake[999001] = dict(PLAIN[783], pre=set(), nx=set(), alt=set())
fake_titles = dict(TITLES)
fake_titles[999001] = TITLES[783]
check((783, 999001) in find_duplicates(fake, fake_titles, EXTRA, SEPARATE), "a new copy of a quest under another ID is caught")
stale = [sorted(s) for i, s in enumerate(SEPARATE) if not find_duplicates(PLAIN, TITLES, EXTRA, SEPARATE[:i] + SEPARATE[i + 1:])]
check(not stale, f"every SEPARATE entry is still needed: {stale}")
# --- Tier 0.5 (Dungeon Set 2): on the Class page, whole, with no page of its own ---
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
check(all(z["id"] != -318 for z in ns.GetZones().values()), "there's no Tier 0.5 Sets page in the zone list")
cls_page = set(ns.GetZoneQuests("class").values())
check(8912 in cls_page and 8922 in cls_page and 8921 in cls_page and 8905 not in cls_page,
      "the Class page has a Warrior's Tier 0.5 chain, with the steps every class shares, and not other classes' steps")
t05 = next(st for st in ns.BuildStorylines("class")[0].values() if 8912 in [n["id"] for n in st["nodes"].values()])
t05_ids = {n["id"] for n in t05["nodes"].values()}
check({8912, 8922, 8921, 8924} <= t05_ids, f"and it's one storyline, from An Earnest Proposition on ({len(t05_ids)} quests)")
check(ns.HomePage(8921) == "class" and ns.HomePage(783) == ns.Quests[783]["z"], "a Tier 0.5 quest's home page is the Class page")
ns.Toggle(True)
ns.FocusQuest(8921)
check(ns.focusedQuest == 8921 and frame["zoneTitle"]["__text"] == "Warrior quests", "jumping to one opens the Class page")
ns.Toggle(False)
# --- Storylines that cross zones: linked tiles for the quests on other pages ---
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 20, 1429
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
sls, _ = ns.BuildStorylines(1429)
sls = list(sls.values())
linked = [(st, l) for st in sls for l in (st["links"] or lua.table()).values()]
froms = [(st, l) for st, l in linked if l["from"] and not l["to"]]
tos = [(st, l) for st, l in linked if l["to"] and not l["from"]]
print(f"Elwynn at level 20: {len(linked)} linked tiles ({len(froms)} from, {len(tos)} to)")
check(tos and all(ns.Quests[l["id"]]["z"] != 1429 for _, l in linked), "Elwynn's storylines link on to quests in other zones")
st, l = tos[0]
node_ids = {n["id"] for n in st["nodes"].values()}
check(any(p in node_ids for p in st["parents"][l["id"]].values()), "a 'to' tile follows the quest in this zone that leads to it")
col_of = {n["id"]: n["col"] for n in list(st["nodes"].values()) + list(st["links"].values())}
check(all(col_of[p] < col_of[c] for c, ps in st["parents"].items() for p in ps.values() if p in col_of and c in col_of),
      "linked tiles sit in the right column: before the quest they unlock, after the one that leads to them")
check(l["id"] not in node_ids and all(ns.Quests[n["id"]]["z"] == 1429 or ns.IsSpecialPage(1429) for n in st["nodes"].values()),
      "linked quests aren't part of the storyline (its progress and next step)")
there = ns.Quests[l["id"]]["z"]
leading = set(st["parents"][l["id"]].values()) & node_ids
back = [lk["id"] for s2 in ns.BuildStorylines(there)[0].values() for lk in (s2["links"] or lua.table()).values() if lk["from"]]
check(leading & set(back), f"and {ns.GetMapName(there)}'s page shows the Elwynn quest its storyline starts from")
char["faction"], char["race"] = "Horde", 2
ns.RefreshPlayer()
check(not any(ns.Quests[lk["id"]]["f"] == 2 for s2 in ns.BuildStorylines(1413)[0].values() for lk in (s2["links"] or lua.table()).values()),
      "a Horde character's storylines never link to Alliance quests")
char["faction"], char["race"] = "Alliance", 1
ns.RefreshPlayer()

# In the window.
ns.Toggle(True)
ns.FocusQuest(st["first"])
tile = next(f for f in harness["all"].values() if f["questID"] == l["id"] and f["link"] is not None and f.IsShown(f))
zone_name = ns.GetMapName(ns.Quests[l["id"]]["z"])
check(tile["sub"]["__text"].find("Continues in " + zone_name) >= 0 and tile["__alpha"] < 1,
      f"a 'to' tile says where the story goes on: {tile['sub']['__text']!r}")
check(tile["icon"]["__texture"] == ns.ui.ZoneIcon(ns.Quests[l["id"]]["z"]) and tile["icon"]["__atlas"] is None,
      f"and shows that zone's icon ({tile['icon']['__texture']})")
own = next(f for f in harness["all"].values() if f["questID"] in node_ids and f["link"] is None and f["icon"] is not None and f.IsShown(f))
check(own["icon"]["__texture"] != ns.ui.ZoneIcon(1429), "the storyline's own quests keep their quest icons")
g.GameTooltip.lines = lua.table()
tile["__scripts"]["OnEnter"](tile)
lines = [str(x) for x in g.GameTooltip.lines.values()]
check(any("continues with it, in " + zone_name in x for x in lines) and "Click to go to it." in lines and "Click for details." not in lines,
      "its tooltip says so, and that a click goes there")
tile["__scripts"]["OnClick"](tile)
check(frame["zoneTitle"]["__text"].startswith(zone_name) and ns.focusedQuest == l["id"], f"clicking it goes to {zone_name}, at that quest")
ns.Toggle(False)
char["level"] = 60

# --- One chain in pieces on a page, joined through other pages; where a chain starts ---
char["race"], char["class"], char["faction"], char["level"], char["map"] = 6, 1, "Horde", 60, 1456
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
tb = next(st for st in ns.BuildStorylines(1456)[0].values() if 1064 in [n["id"] for n in st["nodes"].values()])
tb_nodes = {n["id"]: n for n in tb["nodes"].values()}
tb_links = {n["id"]: n for n in tb["links"].values()}
check(1086 in tb_nodes, "Thunder Bluff's Forsaken Aid and The Flying Machine Airport, joined only through Hillsbrad, are one storyline")
check(1065 in tb_links and 1067 in tb_links
      and tb_nodes[1064]["col"] < tb_links[1065]["col"] < tb_links[1067]["col"] < tb_nodes[1086]["col"],
      "laid out in order: Forsaken Aid, Continues in Hillsbrad, From Hillsbrad, The Flying Machine Airport")
check(1065 not in list((tb["parents"][1067] or lua.table()).values()), "with no line drawn between the two Hillsbrad tiles")
hb = next(st for st in ns.BuildStorylines(1424)[0].values() if 1065 in [n["id"] for n in st["nodes"].values()])
check(hb["origin"] == 1061, f"Hillsbrad's Journey to Tarren Mill knows its chain starts with The Spirits of Stonetalon ({hb['origin']})")
hb_lines = list(ns.ui.StorylineHeaderLines(hb, hb["first"]).values())
check(hb_lines == [f"Part of a chain that starts with Q1061, in {ns.GetMapName(1442)}."], f"and its header tooltip says so: {hb_lines}")
st_own = next(st for st in ns.BuildStorylines(1442)[0].values() if 1061 in [n["id"] for n in st["nodes"].values()])
check(st_own["origin"] is None and ns.ui.StorylineHeaderLines(st_own, st_own["first"]) is None,
      "a storyline that starts on its own page has no such line")
overlaps = []
for z in ns.GetZones().values():
    for st in ns.BuildStorylines(z["id"])[0].values():
        cells = [(n["col"], n["row"]) for n in list(st["nodes"].values()) + list((st["links"] or lua.table()).values())]
        if len(cells) != len(set(cells)):
            overlaps.append(z["id"])
check(not overlaps, f"no storyline on any page puts two tiles in one place: {overlaps[:5]}")

# Errands don't name storylines: "Speak with Ruga" is named after the quest it leads to.
check(ns.IsErrandTitle("Speak with Ruga") and ns.IsErrandTitle("Report to Kadrak") and ns.IsErrandTitle("deliveries to sven")
      and not ns.IsErrandTitle("The Spirits of Stonetalon") and not ns.IsErrandTitle("Speaking of Fortitude"),
      "errand titles are told apart from real ones")
errand = next(st for st in ns.BuildStorylines(1413)[0].values() if len(list(st["nodes"].values())) >= 3)
errand_first = errand["first"]
second = list(errand["nodes"].values())[1]["id"]
g.C_QuestLog.GetTitleForQuestID = lua.eval(f"function(id) if id == {errand_first} then return 'Speak with Ruga' end return 'Q' .. id end")
check(ns.StorylineTitleQuest(errand) == second, "a storyline that opens with an errand takes the next quest's name")
check(list(ns.ui.StorylineHeaderLines(errand, second).values())[0] == "Starts with Speak with Ruga.", "and its tooltip says which quest it starts with")
char["map"] = 1413
ns.Toggle(True)
ns.FocusQuest(errand_first)
header = next(f for f in harness["all"].values() if f["key"] == "s" + str(errand_first) and f.IsShown(f))
check(header["title"]["__text"] == f"Q{second}", f"in the window, its header shows that name: {header['title']['__text']!r}")
g.GameTooltip.lines = lua.table()
header["__scripts"]["OnEnter"](header)
lines = [str(x) for x in g.GameTooltip.lines.values()]
check("Starts with Speak with Ruga." in lines, f"and hovering it explains: {lines}")
ns.Toggle(False)

# A chain keeps one name on every page: Mulgore's The Hunter's Way goes on in the Barrens with its
# breadcrumb Sergra Darkthorn, and the Barrens' storyline is still called The Hunter's Way.
char["race"], char["class"], char["faction"], char["level"], char["map"] = 6, 3, "Horde", 60, 1413
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
g.C_QuestLog.GetTitleForQuestID = lua.eval(
    "function(ns) return function(id) local t = ns.CommunityText[id] or ns.QuestText[id]; return t and t.t end end")(ns)
harness.Fire("QUEST_DATA_LOAD_RESULT", 861, True)  # names arriving, as the client tells us
def storyline_with(page, qid):
    return next((st for st in ns.BuildStorylines(page)[0].values() if qid in [n["id"] for n in st["nodes"].values()]), None)
title_of = lambda st: ns.GetQuestNameOrID(ns.StorylineTitleQuest(st))
hw_mulgore, hw_barrens = storyline_with(1412, 861), storyline_with(1413, 860)
check(title_of(hw_mulgore) == "The Hunter's Way", f"Mulgore's hunter chain is called The Hunter's Way: {title_of(hw_mulgore)!r}")
check(hw_barrens["first"] == 860 and hw_barrens["origin"] == 861 and title_of(hw_barrens) == "The Hunter's Way",
      f"on the Barrens' page, the same chain, starting with Sergra Darkthorn, is still The Hunter's Way: {title_of(hw_barrens)!r}")
hw_lines = list(ns.ui.StorylineHeaderLines(hw_barrens, ns.StorylineTitleQuest(hw_barrens)).values())
check(hw_lines == ["Starts with Sergra Darkthorn.", f"Part of a chain that starts with The Hunter's Way, in {ns.GetMapName(1412)}."],
      f"and its header tooltip says where it starts on this page and where the chain began: {hw_lines}")
ns.Toggle(True)
ns.FocusQuest(860)
header = next(f for f in harness["all"].values() if f["key"] == "s860" and f.IsShown(f))
check(header["title"]["__text"] == "The Hunter's Way", f"in the window, the Barrens' header shows The Hunter's Way: {header['title']['__text']!r}")
ns.Toggle(False)
# A chain that leaves a page for a long way: the Shattered Amulet chain goes from Swamp of Sorrows through eight quests
# in Azshara and Stranglethorn, then comes back. Its pieces are still one storyline, on both pages it comes back to.
char["race"], char["class"], char["faction"], char["level"] = 1, 1, "Alliance", 60
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
sos = next(st for st in ns.BuildStorylines(1435)[0].values() if 2744 in [n["id"] for n in st["nodes"].values()])
check(3627 in [n["id"] for n in sos["nodes"].values()],
      "Swamp of Sorrows' Uniting the Shattered Amulet joins the chain it came back to, eight quests away on other pages")
bl = next(st for st in ns.BuildStorylines(1419)[0].values() if 2783 in [n["id"] for n in st["nodes"].values()])
check(3628 in [n["id"] for n in bl["nodes"].values()],
      "and Blasted Lands' You Are Rakh'likh, Demon joins the start of that chain on its page")
# The rule everywhere: a storyline that carries on a chain from another page has the name the chain has where
# it starts, unless that's only a lead-in (a breadcrumb or an errand), when it keeps its own.
def lead_in(qid):
    return ns.Quests[qid]["bc"] is not None or ns.IsErrandTitle(ns.GetQuestName(qid))
mismatches, renamed, kept = [], 0, 0
for race, cls, fac in [(6, 3, "Horde"), (2, 1, "Horde"), (5, 8, "Horde"), (1, 1, "Alliance"), (4, 11, "Alliance"), (7, 9, "Alliance")]:
    char["race"], char["class"], char["faction"] = race, cls, fac
    ns.RefreshPlayer()
    for z in ns.GetZones().values():
        for st in ns.BuildStorylines(z["id"])[0].values():
            o = st["origin"]
            there = o and storyline_with(ns.Quests[o]["z"], o)
            if not there:
                continue
            want = ns.StorylineTitleQuest(there)
            if lead_in(want):
                kept += 1
                ok = ns.StorylineTitleQuest(st) in [n["id"] for n in st["nodes"].values()]
            else:
                renamed += 1
                ok = ns.StorylineTitleQuest(st) == want
            if not ok:
                mismatches.append((z["id"], st["first"]))
check(renamed > 50 and kept > 0 and not mismatches,
      f"every storyline continuing a chain from another page takes the chain's name ({renamed}), or keeps its own after a lead-in ({kept}): {mismatches[:5]}")
char["race"], char["class"], char["faction"] = 6, 1, "Horde"
ns.RefreshPlayer()
fa = storyline_with(1456, 1064)
check(fa["origin"] == 1061 and title_of(fa) == "Forsaken Aid",
      f"Thunder Bluff's Forsaken Aid keeps its name: its chain starts with the breadcrumb The Spirits of Stonetalon ({title_of(fa)!r})")

# Chain names are kept, so redrawing a page doesn't rebuild the pages its chains start on.
char["race"], char["class"], char["faction"] = 6, 3, "Horde"
ns.RefreshPlayer(); ns.RefreshCompleted()
builds, real_build = lua.eval(
    "function(ns) local real, n = ns.BuildStorylines, { count = 0 }; "
    "ns.BuildStorylines = function(z) n.count = n.count + 1; return real(z) end; return n, real end")(ns)
ns.StorylineTitleQuest(hw_barrens)
builds["count"] = 0
check(ns.StorylineTitleQuest(hw_barrens) == 861 and builds["count"] == 0,
      f"a second lookup of the Barrens' chain name doesn't build Mulgore's storylines again ({builds['count']} builds)")
ns.RefreshPlayer(); ns.RefreshCompleted()
ns.StorylineTitleQuest(hw_barrens)
check(builds["count"] == 0, f"nor does redrawing with nothing changed ({builds['count']} builds)")
harness.Fire("QUEST_ACCEPTED", 860)
harness.RunTimers()
builds["count"] = 0
check(ns.StorylineTitleQuest(hw_barrens) == 861 and builds["count"] > 0,
      f"a change to the quest log clears it, so it's worked out again ({builds['count']} builds)")
harness.Fire("QUEST_REMOVED", 860)
builds["count"] = 0
ns.StorylineTitleQuest(hw_barrens)
check(builds["count"] > 0, "and so does a quest leaving the log")
char["completed"][861] = True
ns.RefreshCompleted()
builds["count"] = 0
ns.StorylineTitleQuest(hw_barrens)
check(builds["count"] > 0, "and finishing a quest")
char["completed"] = lua.table()
ns.RefreshCompleted()
# Names load from the client: a name worked out while one was still missing isn't kept.
bundled = g.C_QuestLog.GetTitleForQuestID
g.C_QuestLog.GetTitleForQuestID = lua.eval("function(f) return function(id) if id == 861 then return nil end return f(id) end end")(bundled)
harness.Fire("QUEST_DATA_LOAD_RESULT", 861, False)
missing_title = ns.StorylineTitleQuest(hw_barrens)
builds["count"] = 0
ns.StorylineTitleQuest(hw_barrens)
check(builds["count"] > 0, f"while a chain's quest name is still loading, its chain name isn't kept (named {missing_title})")
g.C_QuestLog.GetTitleForQuestID = bundled
check(ns.StorylineTitleQuest(hw_barrens) == 861, "so once the name arrives, the chain is named properly")
ns.BuildStorylines = real_build
g.C_QuestLog.GetTitleForQuestID = real_title
harness.Fire("QUEST_DATA_LOAD_RESULT", 861, True)
char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 60, 1429
ns.RefreshPlayer(); ns.RefreshCompleted()
ns.RefreshPlayer()

# --- Long storylines wrap to the window's width ---
WL = ns.ui.WrapLayout
long_line = lua.eval("{ cols = 10, rows = 2 }")
lay = WL(long_line, 800, 40)
check(lay["perBand"] == 3 and lay["bands"] == 4, f"a 10-column storyline in an 800-wide window wraps into bands of 3 ({lay['perBand']} x {lay['bands']})")
x0, y0, b0 = lay.Pos(lua.eval("{ col = 0, row = 0 }"))
x3, y3, b3 = lay.Pos(lua.eval("{ col = 3, row = 0 }"))
check(b3 == 1 and x3 == x0 and y3 > y0 + 2 * 46, "column 4 starts the second band, back at the left, below the first band's rows")
pts = list(lay.Route(lua.eval("{ col = 2, row = 1 }"), lua.eval("{ col = 3, row = 0 }")).values())
ys = [p[2] for p in pts]
check(len(pts) == 6 and -ys[2] > y0 + 2 * 46 - 10 and -ys[2] < y3, "the line into the next band runs along the gap between the bands")
# The real window: its graph area is the frame less the zone list and margins.
graph_w = frame["__w"] - (10 + 220 + 6 + 8 + 8)
check(WL(long_line, graph_w, 40)["perBand"] == 4, f"in LorePath's window ({frame['__w']} wide, graph {graph_w}), a long storyline wraps every 4 quests")
short_line = lua.eval("{ cols = 2, rows = 3 }")
lay2 = WL(short_line, 800, 40)
check(lay2["bands"] == 1 and lay2["height"] == 26 + 8 + 3 * (36 + 10), "a storyline that fits isn't changed")

char["race"], char["class"], char["faction"], char["level"], char["map"] = 1, 1, "Alliance", 30, 1429
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
ns.Toggle(True)
view_w = frame["graphScroll"].GetWidth(frame["graphScroll"])
widest = None
for page in [z["id"] for z in ns.GetZones().values()]:
    for st in ns.BuildStorylines(page)[0].values():
        if st["cols"] > 3 and (widest is None or st["cols"] > widest[1]["cols"]):
            widest = (page, st)
page, st = widest
ns.FocusQuest(st["first"])
ids = {n["id"] for n in st["nodes"].values()}
tiles = [f for f in harness["all"].values() if f["questID"] in ids and f["sub"] is not None and f.IsShown(f)]
check(tiles and max(t["px"] for t in tiles) + 186 <= view_w,
      f"on screen, the longest storyline ({st['cols']} columns, in {ns.GetMapName(page)}) fits the window's width ({max(t['px'] for t in tiles) + 186} <= {view_w})")
ns.Toggle(False)
char["level"] = 60
ns.RefreshPlayer()
# --- Timbermaw Hold's quests are in the zones they start in, not on a Kalimdor page ---
check(all(ns.Quests[q]["z"] == 1448 for q in (6031, 8460, 8461, 8470, 8481)) and all(ns.Quests[q]["z"] == 1452 for q in (8464, 8469)),
      "Timbermaw Hold's quests are on Felwood's page, or Winterspring's for the Winterfall ones")
check(not any(q["z"] == 1414 for q in ns.Quests.values()), "and no quest is left on the Kalimdor continent page")

# --- Story so far: a storyline's finished quests, read in order (issue #4) ---
char["race"], char["class"], char["faction"], char["level"], char["map"] = 6, 1, "Horde", 60, 1412
char["completed"], char["log"] = lua.table(), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
mg = next(st for st in ns.BuildStorylines(1412)[0].values()
          if len([n for n in st["nodes"].values() if not ns.IsRepeatable(n["id"])]) >= 3)
order = [n["id"] for n in sorted(mg["nodes"].values(), key=lambda n: (n["col"], n["row"], n["id"])) if not ns.IsRepeatable(n["id"])]
first_q, second_q, ahead = order[0], order[1], order[2]
char["completed"] = lua.table_from({second_q: True, first_q: True})
ns.RefreshCompleted()
cache = g.LorePathDB["questCache"]
cache[first_q] = lua.table_from({"text": "Take this to the elders, $N.", "done": "The elders thank you."})
cache[ahead] = lua.table_from({"text": "A secret further on."})
story = list(ns.StorySoFar(mg)[0].values())
check([e["id"] for e in story] == [first_q, second_q], f"Story so far lists the finished quests in storyline order: {[e['id'] for e in story]}")
check(story[0]["d"] == "Take this to the elders, $N." and story[0]["c"] == "The elders thank you.",
      "with the description and completion text you saw")
ns.Toggle(True)
ns.FocusQuest(first_q)
header = next(f for f in harness["all"].values() if f["key"] == "s" + str(mg["first"]) and f.IsShown(f))
check(header["story"].IsShown(header["story"]), "a storyline with finished quests has a Story so far button")
header["story"]["__scripts"]["OnClick"](header["story"])
panel = g.LorePathDetailFrame
texts = detail_texts()
check(panel.IsShown(panel) and panel["titleText"]["__text"] == "Story so far" and ns.detailQuest is None,
      "clicking it opens the story in the side panel")
check(any(t.startswith("Take this to the elders, ") and "$N" not in t for t in texts)
      and "The elders thank you." in texts and "On turning it in:" in texts,
      "it reads each quest's text, placeholders filled in")
check(not any("A secret further on." in t for t in texts), "quests you haven't finished stay hidden")
check(any(t.startswith("2 of ") for t in texts) and "The rest of the story is still ahead of you." in texts,
      "it says how far through you are")
header["story"]["__scripts"]["OnClick"](header["story"])
check(not panel.IsShown(panel) and ns.detailStory is None, "clicking it again closes the panel")
header["story"]["__scripts"]["OnClick"](header["story"])
ns.ShowDetail(first_q)
check(ns.detailStory is None and panel["titleText"]["__text"] == "Quest details", "clicking a quest swaps the story for its details")
ns.HideDetail()
char["completed"] = lua.table()
ns.RefreshCompleted()
ns.Refresh()
header = next(f for f in harness["all"].values() if f["key"] == "s" + str(mg["first"]) and f.IsShown(f))
check(not header["story"].IsShown(header["story"]), "a storyline with nothing finished has no Story so far button")
cache[first_q], cache[ahead] = None, None
ns.Toggle(False)

# Story so far follows a chain across pages: Thunder Bluff's Forsaken Aid starts in Stonetalon and goes through Hillsbrad.
char["race"], char["class"], char["faction"], char["level"], char["map"] = 6, 1, "Horde", 60, 1456
char["completed"], char["log"] = lua.table_from({q: True for q in (1061, 1062, 1063, 1064, 1065, 1066, 1067, 1086, 1060)}), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
tb = next(st for st in ns.BuildStorylines(1456)[0].values() if 1064 in [n["id"] for n in st["nodes"].values()])
tb_story = [e["id"] for e in ns.StorySoFar(tb)[0].values()]
check(tb_story == [1061, 1062, 1063, 1064, 1065, 1066, 1067, 1086],
      f"Thunder Bluff's story starts in Stonetalon and goes through Hillsbrad, in order: {tb_story}")
check(1060 not in tb_story, "a finished quest on another page that isn't part of the chain stays out")
hide_was = ns.GetSetting("hideCompleted")
ns.SetSetting("hideCompleted", False)  # the whole chain is finished here
ns.Toggle(True)
ns.FocusQuest(1064)
header = next(f for f in harness["all"].values() if f["key"] == "s" + str(tb["first"]) and f.IsShown(f))
header["story"]["__scripts"]["OnClick"](header["story"])
texts = detail_texts()
zones = [t for t in texts if t.startswith("In ")]
check(zones == ["In " + ns.GetMapName(z) for z in (1442, 1456, 1424, 1456)],
      f"each chapter on another page says where, and so does coming back: {zones}")
check(not any(t.startswith("This chain starts earlier") for t in texts), "with no 'starts earlier' line once you've done where it starts")
char["completed"] = lua.table_from({1064: True})
ns.RefreshCompleted()
ns.Refresh()
texts = detail_texts()
check(any(t.startswith("This chain starts earlier, with ") for t in texts) and not any(t.startswith("In ") for t in texts),
      "before you've done the earlier part, it says where the chain starts instead")
ns.HideDetail()
ns.SetSetting("hideCompleted", hide_was)
char["completed"] = lua.table()
ns.RefreshCompleted()
ns.Toggle(False)

# And it reads on: Hillsbrad's piece of that chain carries on into Thunder Bluff.
char["race"], char["class"], char["faction"], char["level"], char["map"] = 6, 1, "Horde", 60, 1424
char["completed"], char["log"] = lua.table_from({q: True for q in (1061, 1062, 1063, 1064, 1065, 1066, 1067, 1086)}), lua.table()
ns.RefreshPlayer(); ns.RefreshCompleted()
hb = next(st for st in ns.BuildStorylines(1424)[0].values() if 1065 in [n["id"] for n in st["nodes"].values()])
hb_story = [e["id"] for e in ns.StorySoFar(hb)[0].values()]
check(hb_story == [1061, 1062, 1063, 1064, 1065, 1066, 1067, 1086],
      f"Hillsbrad's story includes what came before and after it on other pages: {hb_story}")
char["completed"][1086] = None
ns.RefreshCompleted()
hb_entries, goes_on = ns.StorySoFar(hb)
check(1086 not in [e["id"] for e in hb_entries.values()] and goes_on == 1456,
      f"a later quest you haven't done stays out, and the story says it goes on in Thunder Bluff ({goes_on})")
hide_was = ns.GetSetting("hideCompleted")
ns.SetSetting("hideCompleted", False)
ns.Toggle(True)
ns.FocusQuest(1065)
header = next(f for f in harness["all"].values() if f["key"] == "s" + str(hb["first"]) and f.IsShown(f))
header["story"]["__scripts"]["OnClick"](header["story"])
texts = detail_texts()
check(("The story goes on in " + ns.GetMapName(1456) + ".") in texts, "and the panel says where it goes on")
ns.HideDetail()
ns.SetSetting("hideCompleted", hide_was)
char["completed"] = lua.table()
ns.RefreshCompleted()
ns.Toggle(False)

# --- Close buttons work in combat ---
# The game's window templates close through HideUIPanel, which it blocks for addons in combat.
harness["inCombat"] = True
ns.Toggle(True)
frame["CloseButton"]["__scripts"]["OnClick"](frame["CloseButton"])
check(not frame.IsShown(frame), "in combat, the window's close button still closes it")
ns.Toggle(True)
ns.ShowDetail(783)
detail = g.LorePathDetailFrame
detail["CloseButton"]["__scripts"]["OnClick"](detail["CloseButton"])
check(not detail.IsShown(detail), "and so does the quest details' close button")
g.LorePathDB["questCache"][783] = lua.table_from({"text": "Something only you saw."})
if ns.OpenShare():
    share_f = g.LorePathShareFrame
    share_f["CloseButton"]["__scripts"]["OnClick"](share_f["CloseButton"])
    check(not share_f.IsShown(share_f), "and the share window's")
g.LorePathDB["questCache"][783] = None
harness["inCombat"] = False
ns.Toggle(False)

unexpected = list(harness["errors"].values())
check(len(unexpected) == 0, "no errors were caught anywhere else in the run: " + " | ".join(unexpected)[:300])
print("chat:", list(harness["chat"].values())[-3:])
print()
print("FAILED:" if failures else "All checks passed.", *failures, sep="\n  ")
sys.exit(1 if failures else 0)
