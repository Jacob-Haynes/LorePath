-- Minimal fake WoW API so Chronicler's files can run outside the game.
-- Frames are permissive mocks: unknown methods do nothing and return nil.
local harness = {}

local function MockObject(kind)
    local o = { __kind = kind, __shown = false, __scripts = {}, __w = 800, __h = 500 }
    local methods = {
        Show = function(self) self.__shown = true; if self.__scripts.OnShow then self.__scripts.OnShow(self) end end,
        Hide = function(self) self.__shown = false end,
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
        GetHorizontalScroll = function() return 0 end,
        GetVerticalScroll = function() return 0 end,
        GetHorizontalScrollRange = function() return 0 end,
        GetVerticalScrollRange = function() return 0 end,
        GetEffectiveScale = function() return 1 end,
        CreateTexture = function() return MockObject("Texture") end,
        CreateFontString = function() return MockObject("FontString") end,
        CreateLine = function() return MockObject("Line") end,
        Enable = function(self) self.__enabled = true end,
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
IsMouseButtonDown = function() return false end
GetCursorPosition = function() return 0, 0 end
InCombatLockdown = function() return false end

-- The test character
harness.char = { race = 1, class = 1, faction = "Alliance", level = 10, completed = {}, log = {}, map = 1429 }
UnitRace = function() return "Human", "Human", harness.char.race end
UnitClass = function() return "Warrior", "WARRIOR", harness.char.class end
UnitFactionGroup = function() return harness.char.faction end
UnitLevel = function() return harness.char.level end
GetProfessions = function() return nil end
GetProfessionInfo = function() return nil end

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

return harness
