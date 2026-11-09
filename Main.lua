-- Chronicler: events, saved settings and slash commands.

local addonName, ns = ...

local GetMetadata = (C_AddOns and C_AddOns.GetAddOnMetadata) or GetAddOnMetadata
ns.VERSION = (GetMetadata and GetMetadata(addonName, "Version")) or "?"

local events = CreateFrame("Frame")
for _, event in ipairs({
    "ADDON_LOADED",
    "QUEST_TURNED_IN",
    "QUEST_ACCEPTED",
    "QUEST_REMOVED",
    "PLAYER_LEVEL_UP",
    "QUEST_DATA_LOAD_RESULT",
    "SKILL_LINES_CHANGED",
}) do
    pcall(events.RegisterEvent, events, event)
end

events:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" then
        if arg1 == addonName then
            ChroniclerDB = ChroniclerDB or {}
        end
    elseif event == "QUEST_TURNED_IN" then
        -- The completed-quest list updates a moment after the turn-in.
        ns.QueueRefresh(0.6)
    elseif event == "QUEST_DATA_LOAD_RESULT" then
        -- Quest names arrive in bursts while the window loads them; redraw once.
        ns.QueueRefresh(0.5)
    else
        ns.QueueRefresh(0.3)
    end
end)

SLASH_CHRONICLER1 = "/chron"
SLASH_CHRONICLER2 = "/chronicler"
SlashCmdList["CHRONICLER"] = function(msg)
    local command = string.lower(string.match(msg or "", "^%s*(%S*)") or "")
    if command == "" then
        ns.Toggle(false)
    elseif command == "here" then
        ns.Toggle(true)
    else
        ns.Print("v" .. ns.VERSION .. " commands:")
        ns.Print("  |cffffd100/chron|r - open or close the window")
        ns.Print("  |cffffd100/chron here|r - open on the zone you're in")
    end
end
