-- LorePath: events (including saving quest text as you play), error safety and
-- slash commands.

local addonName, ns = ...

local GetMetadata = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
ns.VERSION = (GetMetadata and GetMetadata(addonName, "Version")) or "?"

-- Runs fn, and if it errors, reports it (to BugSack/the error frame, and once per
-- kind in chat) instead of letting one broken part stop everything else.
local reported = {}
function ns.Safely(label, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then
        if not reported[label] then
            reported[label] = true
            ns.Print("|cffff6060Something went wrong (" .. label .. ").|r The rest of LorePath keeps working. "
                .. "Please report it at github.com/Jacob-Haynes/LorePath/issues: " .. tostring(err))
        end
        local handler = geterrorhandler and geterrorhandler()
        if handler then
            pcall(handler, err)
        end
    end
    return ok
end

local function Later(delay, label, fn, ...)
    local args = { ... }
    C_Timer.After(delay, function()
        ns.Safely(label, fn, unpack(args))
    end)
end

local events = CreateFrame("Frame")
for _, event in ipairs({
    "ADDON_LOADED",
    "PLAYER_LOGIN",
    "QUEST_TURNED_IN",
    "QUEST_ACCEPTED",
    "QUEST_REMOVED",
    "PLAYER_LEVEL_UP",
    "QUEST_DATA_LOAD_RESULT",
    "SKILL_LINES_CHANGED",
    "UPDATE_FACTION",
    "QUEST_DETAIL",
    "QUEST_COMPLETE",
    "QUEST_PROGRESS",
}) do
    pcall(events.RegisterEvent, events, event)
end

local function OnEvent(event, arg1, arg2)
    if event == "ADDON_LOADED" then
        if arg1 == addonName then
            ns.InitDB()
            ns.CreateSettingsPanel()
        end
        -- The quest log may load on demand (Blizzard_WorldMap and friends).
        ns.AttachQuestLogButton()
    elseif event == "PLAYER_LOGIN" then
        ns.CreateMinimapButton()
        ns.AttachQuestLogButton()
        -- Remember this account's character names, so tools/merge_quest_text.py can
        -- strip any that slipped into saved quest text before it's shared.
        local name = UnitName and UnitName("player")
        if name and LorePathDB then
            LorePathDB.characters = LorePathDB.characters or {}
            LorePathDB.characters[name] = true
        end
        -- Save the text of everything already in your log once it has loaded.
        Later(5, "saving your quest log", ns.CaptureQuestLog)
    elseif event == "QUEST_TURNED_IN" then
        -- The completed-quest list updates a moment after the turn-in.
        ns.QueueRefresh(0.6)
    elseif event == "QUEST_ACCEPTED" then
        -- Newer clients pass (questID), older ones (logIndex, questID).
        local questID = arg2 or arg1
        Later(0.5, "saving a quest", ns.CaptureLogQuest, questID)
        ns.QueueRefresh(0.3)
    elseif event == "QUEST_PROGRESS" then
        -- Handing in mid-quest: keep what the quest giver says.
        ns.CaptureQuestProgress()
    elseif event == "QUEST_COMPLETE" then
        -- The turn-in screen: keep the quest's closing text.
        ns.CaptureQuestComplete()
    elseif event == "QUEST_DETAIL" then
        -- A quest giver is showing a quest: keep its text and rewards for the detail panel.
        ns.CaptureQuestDetail()
    elseif event == "QUEST_DATA_LOAD_RESULT" then
        -- Quest names arrive in bursts while the window loads them; redraw once.
        ns.QueueRefresh(0.5)
    else
        ns.QueueRefresh(0.3)
    end
end

events:SetScript("OnEvent", function(_, event, ...)
    ns.Safely(event, OnEvent, event, ...)
end)

SLASH_LOREPATH1 = "/lp"
SLASH_LOREPATH2 = "/lorepath"
-- Kept to a minimum: everything else has a button or a setting.
local function SlashCommand(msg)
    local command = string.lower(string.match(msg or "", "^%s*(%S*)") or "")
    if command == "" then
        ns.Toggle(false)
    elseif command == "config" then
        ns.OpenSettings()
    elseif command == "share" then
        ns.OpenShare()
    else
        ns.Print("v" .. ns.VERSION .. " commands:")
        ns.Print("  |cffffd100/lp|r - open or close the window")
        ns.Print("  |cffffd100/lp config|r - open the settings")
        ns.Print("  |cffffd100/lp share|r - share the quest text you've collected, for everyone's LorePath")
    end
end

SlashCmdList["LOREPATH"] = function(msg)
    ns.Safely("/lp", SlashCommand, msg)
end
