-- LorePath world map pins (issue #11): a "!" where each quest starts, on the
-- zone map you're looking at: gold for quests at your level, grey for
-- low-level ones, red for ones you're not high enough level for yet. Each has
-- its own entry in the world map's filter menu (and the settings), all on by
-- default.
--
-- Uses the modern map canvas API (WorldMapFrame:AddDataProvider with a
-- MapCanvasDataProviderMixin, and pins from LorePathQuestPinTemplate in
-- Pins.xml). Everything is guarded: a client without that API simply gets no
-- pins.

local addonName, ns = ...

local TEMPLATE = "LorePathQuestPinTemplate"
local PIN_SIZE = 20
-- Pins closer than this (in % of the map) share one pin, like a quest giver
-- with several quests.
local GROUP_DISTANCE = 1.5

local AVAILABLE_ICON = "Interface\\GossipFrame\\AvailableQuestIcon"
local REPEATABLE_ICON = "Interface\\GossipFrame\\DailyQuestIcon"

-- Level bands, best first (a shared pin shows its best quest's colour), each
-- with its own filter: quests at your level, low-level quests (grey to you),
-- and quests you're not high enough level for yet.
local BAND = { CURRENT = 1, LOW = 2, HIGH = 3 }
ns.PIN_BAND = BAND
ns.PIN_FILTERS = {
    { band = BAND.CURRENT, key = "mapPinsCurrent", text = "Quests at your level" },
    { band = BAND.LOW, key = "mapPinsLow", text = "Low-level quests" },
    { band = BAND.HIGH, key = "mapPinsHigh", text = "Quests above your level" },
}
local BAND_SETTING = {}
for _, filter in ipairs(ns.PIN_FILTERS) do
    BAND_SETTING[filter.band] = filter.key
end
-- nil: the "!" in its own gold.
local BAND_COLOR = { [BAND.LOW] = { 0.6, 0.6, 0.6 }, [BAND.HIGH] = { 1, 0.25, 0.2 } }
local BAND_TEXT_COLOR = { [BAND.CURRENT] = { 1, 0.82, 0 }, [BAND.LOW] = BAND_COLOR[BAND.LOW], [BAND.HIGH] = BAND_COLOR[BAND.HIGH] }

-- ============================================================================
-- Which quests get a pin (no map code, so it's testable on its own)
-- ============================================================================

-- A quest's level band, or nil when it gets no pin (done, in your log, or
-- locked for a reason other than level).
local function PinBand(id)
    local S = ns.STATUS
    local status = ns.GetStatus(id)
    if status == S.LEVEL and ns.GetLockReason(id) == "level" then
        return BAND.HIGH
    elseif status == S.AVAILABLE or status == S.REPEATABLE then
        local q = ns.Quests[id]
        return ns.ui.DifficultyColor(q.l or 1) == ns.ui.DIFFICULTY.trivial and BAND.LOW or BAND.CURRENT
    end
    return nil
end
ns.PinBand = PinBand

local function AnyFilterOn()
    for _, filter in ipairs(ns.PIN_FILTERS) do
        if ns.GetSetting(filter.key) then
            return true
        end
    end
    return false
end

-- The quests to pin on a map, grouped where they overlap:
-- { { m, x, y, band, quests = { id, ... } }, ... }. Only quests that start on
-- this very map are pinned, so continent and world maps show none. A quest
-- is pinned only if its zone page would show it (eligible, one version of
-- each, repeatables only when they're shown) and its band's filter is on.
function ns.MapPinGroups(mapID)
    local groups = {}
    if not mapID or not AnyFilterOn() then
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
        local band = onPage and onPage[id] and PinBand(id)
        if band and ns.GetSetting(BAND_SETTING[band]) then
            table.insert(pins, { id = id, band = band, l = q.l or 1, x = q.x, y = q.y })
        end
    end
    -- Best first, so each group's first quest is the one its icon shows.
    table.sort(pins, function(a, b)
        if a.band ~= b.band then
            return a.band < b.band
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
            table.insert(groups, { m = mapID, x = pin.x, y = pin.y, band = pin.band, quests = { pin.id } })
        end
    end
    return groups
end

-- Icon texture and colour (nil: the icon's own) for a group's pin: its best
-- quest's band, with the blue "!" when that quest is repeatable.
function ns.PinStyle(group)
    local repeatable = ns.IsRepeatable(group.quests[1])
    return repeatable and REPEATABLE_ICON or AVAILABLE_ICON, BAND_COLOR[group.band]
end

local PIN_HINTS = { "Click to set a waypoint here.", "Shift+click to open it in LorePath." }

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
        local band = PinBand(id)
        local c = BAND_TEXT_COLOR[band] or BAND_TEXT_COLOR[BAND.CURRENT]
        local suffix = band == BAND.HIGH and (" (needs level " .. (q.l or 1) .. ")") or ""
        GameTooltip:AddLine(string.format("[%d] %s%s", q.l or 1, ns.GetQuestNameOrID(id), suffix), c[1], c[2], c[3])
    end
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine(PIN_HINTS[1], 0.5, 0.8, 1)
    GameTooltip:AddLine("Shift+click to open the first in LorePath.", 0.5, 0.8, 1)
    GameTooltip:Show()
end

-- Click: a waypoint at the pin. Shift+click: the quest in LorePath (its
-- storyline and details), the first one for a shared pin.
function ns.ClickPin(group)
    local id = group.quests[1]
    if IsShiftKeyDown() then
        return ns.ShowInLorePath(id)
    end
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
    self:SetAlpha(group.band == BAND.LOW and 0.8 or 1)
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

local MENU_TITLE = "LorePath quests"

local function ToggleFilter(key)
    ns.SetSetting(key, not ns.GetSetting(key))
end

-- The three filters in the world map's filter menu (the funnel at its top
-- right), under a "LorePath quests" heading. Newer clients build that menu
-- with the Menu API (tag MENU_WORLD_MAP_TRACKING); older ones with
-- UIDropDownMenu, from the button's InitializeDropDown. Returns which it used,
-- or nil when neither is there (the settings page still has the filters).
local function AddToFilterMenu()
    if type(Menu) == "table" and type(Menu.ModifyMenu) == "function" then
        Menu.ModifyMenu("MENU_WORLD_MAP_TRACKING", function(_, root)
            root:CreateDivider()
            root:CreateTitle(MENU_TITLE)
            for _, filter in ipairs(ns.PIN_FILTERS) do
                root:CreateCheckbox(filter.text,
                    function() return ns.GetSetting(filter.key) and true or false end,
                    function() ToggleFilter(filter.key) end)
            end
        end)
        return "menu"
    end
    if type(hooksecurefunc) ~= "function" or type(UIDropDownMenu_AddButton) ~= "function" then
        return nil
    end
    for _, button in ipairs(WorldMapFrame.overlayFrames or {}) do
        if type(button) == "table" and type(button.InitializeDropDown) == "function" then
            hooksecurefunc(button, "InitializeDropDown", function()
                local title = UIDropDownMenu_CreateInfo()
                title.isTitle, title.notCheckable, title.text = true, true, MENU_TITLE
                UIDropDownMenu_AddButton(title)
                for _, filter in ipairs(ns.PIN_FILTERS) do
                    local info = UIDropDownMenu_CreateInfo()
                    info.text = filter.text
                    info.isNotRadio = true
                    info.keepShownOnClick = true
                    info.checked = function() return ns.GetSetting(filter.key) and true or false end
                    info.func = function() ToggleFilter(filter.key) end
                    UIDropDownMenu_AddButton(info)
                end
            end)
            return "dropdown"
        end
    end
    return nil
end

-- Adds the pins and their filters to the world map, once. Called when addons
-- load, since the world map may load on demand.
function ns.AttachMapPins()
    if provider or not MapAPIPresent() or not TemplateExists() then
        return provider
    end
    provider = MakeProvider()
    WorldMapFrame:AddDataProvider(provider)
    ns.mapPinsProvider = provider
    local ok, how = pcall(AddToFilterMenu)
    ns.mapPinsMenu = ok and how or nil
    return provider
end
