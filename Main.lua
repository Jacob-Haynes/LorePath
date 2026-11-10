-- LorePath: events, saved settings and slash commands.

local addonName, ns = ...

local GetMetadata = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
ns.VERSION = (GetMetadata and GetMetadata(addonName, "Version")) or "?"

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

events:SetScript("OnEvent", function(_, event, arg1, arg2)
    if event == "ADDON_LOADED" then
        if arg1 == addonName then
            ns.InitDB()
            ns.CreateSettingsPanel()
        end
    elseif event == "PLAYER_LOGIN" then
        ns.CreateMinimapButton()
        -- Remember this account's character names, so tools/merge_quest_text.py can
        -- strip any that slipped into saved quest text before it's shared.
        local name = UnitName and UnitName("player")
        if name and LorePathDB then
            LorePathDB.characters = LorePathDB.characters or {}
            LorePathDB.characters[name] = true
        end
        -- Save the text of everything already in your log once it has loaded.
        C_Timer.After(5, ns.CaptureQuestLog)
    elseif event == "QUEST_TURNED_IN" then
        -- The completed-quest list updates a moment after the turn-in.
        ns.QueueRefresh(0.6)
    elseif event == "QUEST_ACCEPTED" then
        -- Newer clients pass (questID), older ones (logIndex, questID).
        local questID = arg2 or arg1
        C_Timer.After(0.5, function() ns.CaptureLogQuest(questID) end)
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
end)

SLASH_LOREPATH1 = "/lp"
SLASH_LOREPATH2 = "/lorepath"
SlashCmdList["LOREPATH"] = function(msg)
    local command = string.lower(string.match(msg or "", "^%s*(%S*)") or "")
    if command == "" then
        ns.Toggle(false)
    elseif command == "here" then
        ns.Toggle(true)
    elseif command == "config" or command == "settings" or command == "options" then
        ns.OpenSettings()
    elseif command == "minimap" then
        ns.SetSetting("showMinimapButton", not ns.GetSetting("showMinimapButton"))
        ns.Print("Minimap button " .. (ns.GetSetting("showMinimapButton") and "shown." or "hidden."))
    elseif command == "repeatable" or command == "repeatables" then
        ns.SetSetting("showRepeatable", not ns.GetSetting("showRepeatable"))
        ns.Print("Repeatable quests " .. (ns.GetSetting("showRepeatable") and "shown." or "hidden."))
    else
        ns.Print("v" .. ns.VERSION .. " commands:")
        ns.Print("  |cffffd100/lp|r - open or close the window")
        ns.Print("  |cffffd100/lp here|r - open on the zone you're in")
        ns.Print("  |cffffd100/lp config|r - open the settings")
        ns.Print("  |cffffd100/lp minimap|r - show or hide the minimap button")
        ns.Print("  |cffffd100/lp repeatable|r - show or hide repeatable quests")
    end
end
