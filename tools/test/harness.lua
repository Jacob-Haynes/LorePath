-- Minimal fake WoW API so LorePath's files can run outside the game.
-- Frames are permissive mocks: unknown methods do nothing and return nil.
local harness = {}

local function MockObject(kind)
    local o = { __kind = kind, __shown = false, __scripts = {}, __w = 800, __h = 500 }
    local methods = {
        Show = function(self) self.__shown = true; if self.__scripts.OnShow then self.__scripts.OnShow(self) end end,
        Hide = function(self) local was = self.__shown; self.__shown = false; if was and self.__scripts.OnHide then self.__scripts.OnHide(self) end end,
        IsShown = function(self) return self.__shown end,
        SetShown = function(self, v) self.__shown = v and true or false end,
        SetScript = function(self, name, fn) self.__scripts[name] = fn end,
        GetScript = function(self, name) return self.__scripts[name] end,
        SetText = function(self, t) self.__text = t end,
        GetText = function(self) return self.__text end,
        GetWidth = function(self) return self.__w end,
        GetHeight = function(self) return self.__h end,
        SetSize = function(self, w, h) self.__w, self.__h = w, h end,
        SetWidth = function(self, w) self.__w = w end,
        SetHeight = function(self, h) self.__h = h end,
        GetStringWidth = function() return 60 end,
        -- Scroll frames remember their position; tests can set __vrange/__hrange.
        GetHorizontalScroll = function(self) return self.__hs or 0 end,
        GetVerticalScroll = function(self) return self.__vs or 0 end,
        SetHorizontalScroll = function(self, v) self.__hs = v end,
        SetVerticalScroll = function(self, v) self.__vs = v end,
        GetHorizontalScrollRange = function(self) return self.__hrange or 0 end,
        GetVerticalScrollRange = function(self) return self.__vrange or 0 end,
        GetEffectiveScale = function() return 1 end,
        CreateTexture = function() return MockObject("Texture") end,
        -- Font strings remember their parent (and are listed in harness.all) so tests can read a panel's text.
        CreateFontString = function(self) local fs = MockObject("FontString"); fs.__parent = self; table.insert(harness.all, fs); return fs end,
        CreateLine = function() return MockObject("Line") end,
        Enable = function(self) self.__enabled = true end,
        SetScale = function(self, v) self.__scale = v end,
        GetCenter = function() return 100, 100 end,
        GetChecked = function(self) return self.__checked end,
        SetChecked = function(self, v) self.__checked = v end,
        Disable = function(self) self.__enabled = false end,
    }
    -- Like real frames: unknown methods (capitalised names) are no-ops, unknown fields are nil.
    return setmetatable(o, { __index = function(_, k)
        if methods[k] then return methods[k] end
        if type(k) == "string" and k:match("^%u") then return function() end end
        return nil
    end })
end
harness.MockObject = MockObject
harness.frames = {}

harness.all = {}
function CreateFrame(kind, name, parent, template)
    local f = MockObject(kind)
    f.__parent = parent
    table.insert(harness.all, f)
    f.__template = template
    if name then _G[name] = f; harness.frames[name] = f end
    return f
end

UIParent = MockObject("Frame")
DEFAULT_CHAT_FRAME = { AddMessage = function(_, msg) table.insert(harness.chat, msg) end }
harness.chat = {}
GameTooltip = MockObject("GameTooltip")
GameTooltip.lines = {}
GameTooltip.AddLine = function(self, text) table.insert(self.lines, text) end
GameTooltip_Hide = function() end
UISpecialFrames = {}
ITEM_QUALITY_COLORS = { [2] = { hex = "|cff1eff00" } }
wipe = function(t) for k in pairs(t) do t[k] = nil end return t end
C_Timer = { After = function(_, fn) table.insert(harness.timers, fn) end }
harness.timers = {}
function harness.RunTimers() local t = harness.timers; harness.timers = {}; for _, fn in ipairs(t) do fn() end end
IsShiftKeyDown = function() return false end
IsControlKeyDown = function() return harness.ctrl or false end
IsMouseButtonDown = function() return harness.mouseDown or false end
GetCursorPosition = function() return harness.cx or 0, harness.cy or 0 end
InCombatLockdown = function() return false end
-- Errors that ns.Safely catches are recorded here; the test run fails if any are unexpected.
harness.errors = {}
geterrorhandler = function() return function(err) table.insert(harness.errors, tostring(err)) end end

-- The test character
harness.char = { race = 1, class = 1, faction = "Alliance", level = 10, completed = {}, log = {}, map = 1429 }
UnitRace = function() return "Human", "Human", harness.char.race end
UnitClass = function() return "Warrior", "WARRIOR", harness.char.class end
UnitFactionGroup = function() return harness.char.faction end
UnitLevel = function() return harness.char.level end
GetProfessions = function() return nil end
GetProfessionInfo = function() return nil end

-- Reputation: char.reputation[factionID] = cumulative standing (Neutral = 0).
-- Factions missing from it are unknown to the client (GetFactionDataByID returns nil).
harness.char.reputation = {}
harness.factionNames = { [576] = "Timbermaw Hold", [609] = "Cenarion Circle", [529] = "Argent Dawn" }
harness.factionCalls = 0
C_Reputation = {
    GetFactionDataByID = function(id)
        harness.factionCalls = harness.factionCalls + 1
        local standing = harness.char.reputation[id]
        if standing == nil then return nil end
        return { factionID = id, name = harness.factionNames[id] or ("Faction" .. id), currentStanding = standing, reaction = 4 }
    end,
}
-- The pre-mainline API, for testing the fallback: name, description, standingID, barMin, barMax, barValue, ...
function harness.LegacyGetFactionInfoByID(id)
    local standing = harness.char.reputation[id]
    if standing == nil then return nil end
    return harness.factionNames[id] or ("Faction" .. id), "", 4, 0, 3000, standing
end

C_QuestLog = {
    GetAllCompletedQuestIDs = function()
        local ids = {}
        for id in pairs(harness.char.completed) do table.insert(ids, id) end
        return ids
    end,
    IsQuestFlaggedCompleted = function(id) return harness.char.completed[id] or false end,
    IsOnQuest = function(id) return harness.char.log[id] or false end,
    GetTitleForQuestID = function(id) return "Q" .. id end,
    RequestLoadQuestByID = function() end,
}
local MAPS = { [1429] = { name = "Elwynn Forest", parentMapID = 1415 }, [1415] = { name = "Eastern Kingdoms", parentMapID = 947 },
               [1413] = { name = "The Barrens", parentMapID = 1414 }, [1414] = { name = "Kalimdor", parentMapID = 947 } }
C_Map = {
    GetBestMapForUnit = function() return harness.char.map end,
    GetMapInfo = function(id) return MAPS[id] or { name = "Map" .. id, parentMapID = 0 } end,
    CanSetUserWaypointOnMap = function() return true end,
    SetUserWaypoint = function(point) harness.waypoint = point end,
}
C_SuperTrack = { SetSuperTrackedUserWaypoint = function(v) harness.superTracked = v end }
UiMapPoint = { CreateFromCoordinates = function(m, x, y) return { m = m, x = x, y = y } end }
OpenWorldMap = function(m) harness.openedMap = m end
C_Item = { GetItemNameByID = function(id) return "Item" .. id end, GetItemQualityByID = function() return 2 end }
C_AddOns = { GetAddOnMetadata = function() return "0.1.0" end }
SlashCmdList = {}
Minimap = MockObject("Minimap")
GetBindingKey = function() return nil end
Settings = {
    RegisterCanvasLayoutCategory = function(panel, name)
        harness.settingsCategory = { panel = panel, name = name, GetID = function() return 77 end }
        return harness.settingsCategory
    end,
    RegisterAddOnCategory = function(cat) harness.registeredCategory = cat end,
    OpenToCategory = function(id) harness.openedSettings = id end,
}
-- Fires an event at every frame that has an OnEvent script.
function harness.Fire(event, ...)
    for _, f in ipairs(harness.all) do
        local fn = f.__scripts.OnEvent
        if fn then fn(f, event, ...) end
    end
end

return harness
