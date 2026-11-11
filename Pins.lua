-- LorePath world map pins (issue #11): a "!" where each quest you can pick up
-- starts, on the zone map you're looking at. Off by default ("Show quests on
-- the world map" in the settings, or the tick box on the map itself).
--
-- Uses the modern map canvas API (WorldMapFrame:AddDataProvider with a
-- MapCanvasDataProviderMixin, and pins from LorePathQuestPinTemplate in
-- Pins.xml). Everything is guarded: a client without that API simply gets no
-- pins and no tick box.

local addonName, ns = ...

local TEMPLATE = "LorePathQuestPinTemplate"
local PIN_SIZE = 20
-- Pins closer than this (in % of the map) share one pin, like a quest giver
-- with several quests.
local GROUP_DISTANCE = 1.5

local AVAILABLE_ICON = "Interface\\GossipFrame\\AvailableQuestIcon"
local REPEATABLE_ICON = "Interface\\GossipFrame\\DailyQuestIcon"
local ACTIVE_ICON = "Interface\\GossipFrame\\IncompleteQuestIcon"

-- Kinds of pin, best first: a group shows its best quest's icon.
local KIND = { AVAILABLE = 1, REPEATABLE = 2, LEVEL = 3, ACTIVE = 4 }
ns.PIN_KIND = KIND

local LEVEL_GREY = { 0.55, 0.55, 0.55 }
local ACTIVE_GREY = { 0.85, 0.85, 0.85 }

-- ============================================================================
-- Which quests get a pin (no map code, so it's testable on its own)
-- ============================================================================

-- What kind of pin a quest gets, or nil for none.
local function PinKind(id)
    local S = ns.STATUS
    local status = ns.GetStatus(id)
    if status == S.AVAILABLE then
        return KIND.AVAILABLE
    elseif status == S.REPEATABLE then
        return KIND.REPEATABLE
    elseif status == S.LEVEL and ns.GetSetting("mapPinsHigherLevel") and ns.GetLockReason(id) == "level" then
        return KIND.LEVEL
    elseif status == S.ACTIVE and ns.GetSetting("mapPinsActive") then
        return KIND.ACTIVE
    end
    return nil
end

-- The quests to pin on a map, grouped where they overlap:
-- { { m, x, y, kind, quests = { id, ... } }, ... }. Only quests that start on
-- this very map are pinned, so continent and world maps show none. A quest
-- is pinned only if its zone page would show it (eligible, one version of
-- each, repeatables only when they're shown).
function ns.MapPinGroups(mapID)
    local groups = {}
    if not mapID or not ns.GetSetting("showMapPins") then
        return groups
    end
    ns.RefreshPlayer()
    ns.RefreshCompleted()

    local candidates, zones = {}, {}
    for id, q in pairs(ns.Quests) do
        if q.m == mapID and q.x and q.y then
            table.insert(candidates, id)
            zones[q.z] = zones[q.z] or false
        end
    end
    for zone in pairs(zones) do
        local onPage = {}
        for _, id in ipairs(ns.GetZoneQuests(zone)) do
            onPage[id] = true
        end
        zones[zone] = onPage
    end

    local pins = {}
    for _, id in ipairs(candidates) do
        local q = ns.Quests[id]
        local onPage = zones[q.z]
        local kind = onPage and onPage[id] and PinKind(id)
        if kind then
            table.insert(pins, { id = id, kind = kind, l = q.l or 1, x = q.x, y = q.y })
        end
    end
    -- Best first, so each group's first quest is the one its icon shows.
    table.sort(pins, function(a, b)
        if a.kind ~= b.kind then
            return a.kind < b.kind
        elseif a.l ~= b.l then
            return a.l < b.l
        end
        return a.id < b.id
    end)

    local limit = GROUP_DISTANCE * GROUP_DISTANCE
    for _, pin in ipairs(pins) do
        local home
        for _, group in ipairs(groups) do
            local dx, dy = group.x - pin.x, group.y - pin.y
            if dx * dx + dy * dy <= limit then
                home = group
                break
            end
        end
        if home then
            table.insert(home.quests, pin.id)
        else
            table.insert(groups, { m = mapID, x = pin.x, y = pin.y, kind = pin.kind, quests = { pin.id } })
        end
    end
    return groups
end

-- Icon texture and colour for a group's pin.
function ns.PinStyle(group)
    local id = group.quests[1]
    local q = ns.Quests[id]
    if group.kind == KIND.REPEATABLE then
        return REPEATABLE_ICON, nil
    elseif group.kind == KIND.LEVEL then
        return AVAILABLE_ICON, LEVEL_GREY
    elseif group.kind == KIND.ACTIVE then
        return ACTIVE_ICON, ACTIVE_GREY
    end
    return AVAILABLE_ICON, ns.ui.DifficultyColor(q.l or 1)
end

local PIN_HINTS = { "Click to set a waypoint here." }

-- One quest: LorePath's usual quest tooltip. Several: a line for each.
function ns.ShowPinTooltip(owner, group)
    if #group.quests == 1 then
        ns.ui.ShowQuestTooltip(owner, group.quests[1], nil, PIN_HINTS)
        return
    end
    GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
    GameTooltip:AddLine(string.format("%d quests", #group.quests), 1, 0.82, 0)
    for _, id in ipairs(group.quests) do
        local q = ns.Quests[id]
        local status = ns.GetStatus(id)
        local c
        if status == ns.STATUS.AVAILABLE then
            c = ns.ui.DifficultyColor(q.l or 1)
        elseif status == ns.STATUS.REPEATABLE then
            c = ns.ui.REPEATABLE_BLUE
        elseif status == ns.STATUS.ACTIVE then
            c = ACTIVE_GREY
        else
            c = LEVEL_GREY
        end
        local suffix = ""
        if status == ns.STATUS.ACTIVE then
            suffix = " (in your log)"
        elseif status == ns.STATUS.LEVEL then
            suffix = " (needs level " .. (q.l or 1) .. ")"
        end
        GameTooltip:AddLine(string.format("[%d] %s%s", q.l or 1, ns.GetQuestNameOrID(id), suffix), c[1], c[2], c[3])
    end
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine(PIN_HINTS[1], 0.5, 0.8, 1)
    GameTooltip:Show()
end

function ns.ClickPin(group)
    local id = group.quests[1]
    if #group.quests == 1 then
        return ns.ShowQuestStart(id)
    end
    return ns.SetWaypoint(group.m, group.x, group.y, string.format("%s and %d more", ns.GetQuestNameOrID(id), #group.quests - 1))
end

-- ============================================================================
-- The pin (LorePathQuestPinTemplate in Pins.xml uses this mixin)
-- ============================================================================

-- Global, because Pins.xml names it. A copy of MapCanvasPinMixin plus our own
-- methods; the map canvas sets the pin's OnEnter/OnLeave to OnMouseEnter/
-- OnMouseLeave and calls OnMouseClickAction on a click.
LorePathQuestPinMixin = {}
for key, value in pairs(type(MapCanvasPinMixin) == "table" and MapCanvasPinMixin or {}) do
    LorePathQuestPinMixin[key] = value
end
local Pin = LorePathQuestPinMixin

function Pin:OnAcquired(group)
    self.group = group
    if not self.icon then
        self:SetSize(PIN_SIZE, PIN_SIZE)
        self.icon = self:CreateTexture(nil, "OVERLAY")
        self.icon:SetAllPoints()
        self.count = self:CreateFontString(nil, "OVERLAY", "NumberFontNormalSmall")
        self.count:SetPoint("BOTTOMRIGHT", self, "BOTTOMRIGHT", 3, -2)
    end
    if self.UseFrameLevelType then
        pcall(self.UseFrameLevelType, self, "PIN_FRAME_LEVEL_AREA_POI")
    end
    if self.SetScalingLimits then
        pcall(self.SetScalingLimits, self, 1, 1.0, 1.2)
    end
    local texture, color = ns.PinStyle(group)
    self.icon:SetTexture(texture)
    if color then
        -- The "!" is yellow; greyed out first, it takes the colour as is.
        self.icon:SetDesaturated(true)
        self.icon:SetVertexColor(color[1], color[2], color[3])
    else
        self.icon:SetDesaturated(false)
        self.icon:SetVertexColor(1, 1, 1)
    end
    self:SetAlpha(group.kind == KIND.LEVEL and 0.75 or 1)
    self.count:SetText(#group.quests > 1 and tostring(#group.quests) or "")
    self:SetPosition(group.x / 100, group.y / 100)
end

function Pin:OnReleased()
    self.group = nil
end

function Pin:OnMouseEnter()
    if self.group then
        ns.Safely("map pin tooltip", ns.ShowPinTooltip, self, self.group)
    end
end

function Pin:OnMouseLeave()
    GameTooltip:Hide()
end

function Pin:OnMouseClickAction(button)
    if self.group and (button == nil or button == "LeftButton") then
        ns.Safely("map pin", ns.ClickPin, self.group)
    end
end

-- ============================================================================
-- The data provider and the tick box on the map
-- ============================================================================

local provider

local function MapAPIPresent()
    return type(WorldMapFrame) == "table" and type(WorldMapFrame.AddDataProvider) == "function"
        and type(MapCanvasDataProviderMixin) == "table" and type(MapCanvasPinMixin) == "table"
end

local function TemplateExists()
    if C_XMLUtil and C_XMLUtil.GetTemplateInfo then
        local ok, info = pcall(C_XMLUtil.GetTemplateInfo, TEMPLATE)
        return ok and info ~= nil
    end
    return true -- can't tell; AcquirePin is guarded anyway
end

local function MakeProvider()
    local p = {}
    for key, value in pairs(MapCanvasDataProviderMixin) do
        p[key] = value
    end
    function p:RemoveAllData()
        self:GetMap():RemoveAllPinsByTemplate(TEMPLATE)
    end
    function p:RefreshAllData()
        self:RemoveAllData()
        local map = self:GetMap()
        for _, group in ipairs(ns.MapPinGroups(map:GetMapID())) do
            map:AcquirePin(TEMPLATE, group)
        end
    end
    return p
end

-- Redraws the pins if the map is open (it redraws itself when it opens or
-- changes map).
function ns.RefreshMapPins()
    if not provider or not provider:GetMap() then
        return
    end
    local map = provider:GetMap()
    if map.IsShown and not map:IsShown() then
        return
    end
    ns.Safely("map pins", provider.RefreshAllData, provider)
    if ns.mapPinsToggle then
        ns.mapPinsToggle:SetChecked(ns.GetSetting("showMapPins") and true or false)
    end
end

local pinRefreshPending = false
function ns.QueueMapPinsRefresh(delay)
    if pinRefreshPending or not provider then
        return
    end
    pinRefreshPending = true
    C_Timer.After(delay or 0.3, function()
        pinRefreshPending = false
        ns.RefreshMapPins()
    end)
end

local function MakeToggle()
    local parent = WorldMapFrame.ScrollContainer or WorldMapFrame
    local cb = CreateFrame("CheckButton", "LorePathMapPinsToggle", WorldMapFrame, "UICheckButtonTemplate")
    cb:SetSize(24, 24)
    cb:SetPoint("BOTTOMLEFT", parent, "BOTTOMLEFT", 6, 6)
    cb:SetFrameLevel((parent:GetFrameLevel() or 0) + 20)
    local text = (type(cb.text) == "table" and cb.text) or (type(cb.Text) == "table" and cb.Text)
        or cb:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    text:ClearAllPoints()
    text:SetPoint("LEFT", cb, "RIGHT", 2, 1)
    text:SetText("LorePath quests")
    cb:SetChecked(ns.GetSetting("showMapPins") and true or false)
    cb:SetScript("OnClick", function(self)
        ns.SetSetting("showMapPins", self:GetChecked() and true or false)
    end)
    cb:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("LorePath quests", 1, 0.82, 0)
        GameTooltip:AddLine("Show a \"!\" where each quest you can pick up starts, coloured by difficulty. More options in Options > AddOns > LorePath.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    cb:SetScript("OnLeave", GameTooltip_Hide)
    return cb
end

-- Adds the pins and the tick box to the world map, once. Called when addons
-- load, since the world map may load on demand.
function ns.AttachMapPins()
    if provider or not MapAPIPresent() or not TemplateExists() then
        return provider
    end
    provider = MakeProvider()
    WorldMapFrame:AddDataProvider(provider)
    ns.mapPinsProvider = provider
    ns.mapPinsToggle = MakeToggle()
    return provider
end
