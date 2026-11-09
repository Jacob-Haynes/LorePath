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
}) do
    pcall(events.RegisterEvent, events, event)
end

events:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" then
        if arg1 == addonName then
            ns.InitDB()
            ns.CreateSettingsPanel()
        end
    elseif event == "PLAYER_LOGIN" then
        ns.CreateMinimapButton()
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
    else
        ns.Print("v" .. ns.VERSION .. " commands:")
        ns.Print("  |cffffd100/lp|r - open or close the window")
        ns.Print("  |cffffd100/lp here|r - open on the zone you're in")
        ns.Print("  |cffffd100/lp config|r - open the settings")
        ns.Print("  |cffffd100/lp minimap|r - show or hide the minimap button")
    end
end
