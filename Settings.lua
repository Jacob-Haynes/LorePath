-- LorePath settings: saved options, the Options -> AddOns page, and the minimap button.

local addonName, ns = ...

local DEFAULTS = {
    showMinimapButton = true,
    minimapAngle = 200,         -- degrees around the minimap
    openOnCurrentZone = true,   -- opening the window jumps to the zone you're in
    showOthers = true,          -- list standalone quests under the storylines
    showRepeatable = true,      -- show daily and repeatable quests (in blue)
    showAllProfessions = false, -- list professions you don't have under Professions, greyed out
    showSpoilers = false,       -- show the story of quests you haven't started (and how quests end)
    hideCompleted = false,      -- hide storylines you've finished
    showLevels = true,          -- show quest levels on the quest tiles
    openMapOnWaypoint = true,   -- open the world map when a waypoint is set
    scale = 1.0,                -- window scale
    -- A "!" on the world map where quests start (Pins.lua), by level; also in
    -- the map's filter menu.
    mapPinsCurrent = true,      -- quests at your level, in gold
    mapPinsLow = false,         -- low-level quests, in grey
    mapPinsHigh = false,        -- quests you're not high enough level for yet, in red
}
ns.DEFAULTS = DEFAULTS

local SCALE_MIN, SCALE_MAX, SCALE_STEP = 0.6, 1.4, 0.1

-- Settings that no longer exist: 1.2.0-beta1's map pin switches, replaced by
-- the three level filters.
local RETIRED = { "showMapPins", "mapPinsHigherLevel", "mapPinsActive" }

function ns.InitDB()
    LorePathDB = LorePathDB or {}
    for _, key in ipairs(RETIRED) do
        LorePathDB[key] = nil
    end
    for key, value in pairs(DEFAULTS) do
        if LorePathDB[key] == nil then
            LorePathDB[key] = value
        end
    end
end

function ns.GetSetting(key)
    local value = LorePathDB and LorePathDB[key]
    if value == nil then
        return DEFAULTS[key]
    end
    return value
end

local RefreshPanel -- set once the settings page exists

-- Settings back to their defaults, and the window's saved layout cleared
-- (collapsed storylines and headings, hidden zone list). Saved quest text
-- (questCache) and character names are kept.
function ns.ResetToDefaults()
    ns.InitDB()
    for key, value in pairs(DEFAULTS) do
        LorePathDB[key] = value
    end
    LorePathDB.collapsed = nil
    LorePathDB.collapsedContinents = nil
    LorePathDB.listHidden = nil
    if ns.ApplyListVisibility then
        ns.ApplyListVisibility()
    end
    ns.ApplySettings()
end

function ns.SetSetting(key, value)
    ns.InitDB()
    LorePathDB[key] = value
    -- Showing repeatable quests changes storylines, and so chains' names.
    if ns.ClearChainTitles then
        ns.ClearChainTitles()
    end
    ns.ApplySettings()
end

function ns.ApplySettings()
    if ns.mainFrame then
        ns.mainFrame:SetScale(ns.GetSetting("scale"))
    end
    if ns.UpdateMinimapButton then
        ns.UpdateMinimapButton()
    end
    if RefreshPanel then
        RefreshPanel()
    end
    if ns.Refresh then
        ns.Refresh()
    end
    if ns.RefreshMapPins then
        ns.RefreshMapPins()
    end
end

-- ============================================================================
-- Settings page
-- ============================================================================

local panel, category
local checkboxes = {}

RefreshPanel = function()
    for key, cb in pairs(checkboxes) do
        cb:SetChecked(ns.GetSetting(key) and true or false)
    end
    if panel and panel.scaleValue then
        panel.scaleValue:SetText(string.format("%d%%", math.floor(ns.GetSetting("scale") * 100 + 0.5)))
    end
    if panel and panel.bindingText then
        local key = GetBindingKey and GetBindingKey("LOREPATH_TOGGLE")
        if key then
            panel.bindingText:SetText("Open/close key: |cffffd100" .. key .. "|r  (change it in Key Bindings > AddOns > LorePath)")
        else
            panel.bindingText:SetText("Open/close key: |cff888888not bound|r  (set one in Key Bindings > AddOns > LorePath)")
        end
    end
end

-- The page is laid out top to bottom in `body` (inside a scroll frame, so it
-- never overflows): each element sits under the previous one, `indent` pixels
-- in from the left. Place returns the element, which becomes the next anchor.
local LEFT, WIDTH = 16, 560
local body, last

local function Place(element, indent, gap)
    element:ClearAllPoints()
    if last then
        element:SetPoint("TOP", last, "BOTTOM", 0, -(gap or 8))
    else
        element:SetPoint("TOP", body, "TOP", 0, -16)
    end
    element:SetPoint("LEFT", body, "LEFT", LEFT + (indent or 0), 0)
    last = element
    return element
end

local function AddText(text, font, indent, gap, color)
    local s = body:CreateFontString(nil, "ARTWORK", font)
    s:SetWidth(WIDTH - (indent or 0))
    s:SetJustifyH("LEFT")
    if color then
        s:SetTextColor(color[1], color[2], color[3])
    end
    s:SetText(text)
    return Place(s, indent, gap)
end

-- A section heading: "Window", "Quests", "World map".
local function AddHeading(text)
    return AddText(text, "GameFontNormal", 0, last and 22 or 0)
end

-- A tick box with its label, and an optional grey description under it.
local function AddCheckbox(key, label, description, indent)
    indent = indent or 0
    local cb = CreateFrame("CheckButton", nil, body, "UICheckButtonTemplate")
    cb:SetSize(26, 26)
    Place(cb, indent, 6)

    local text = (type(cb.text) == "table" and cb.text) or (type(cb.Text) == "table" and cb.Text)
        or cb:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    text:SetFontObject("GameFontHighlight")
    text:ClearAllPoints()
    text:SetPoint("LEFT", cb, "RIGHT", 4, 1)
    text:SetText(label)

    cb:SetScript("OnClick", function(self)
        ns.SetSetting(key, self:GetChecked() and true or false)
    end)
    checkboxes[key] = cb
    if description then
        AddText(description, "GameFontHighlightSmall", indent + 30, 0, { 0.75, 0.75, 0.75 })
    end
    return cb
end

-- The scroll frame's content is as tall as what's in it.
local function FitBody()
    local top, bottom = body:GetTop(), last and last:GetBottom()
    if top and bottom then
        body:SetHeight(math.max(1, top - bottom + 24))
    end
end

function ns.CreateSettingsPanel()
    if panel then
        return
    end
    panel = CreateFrame("Frame", "LorePathSettingsPanel", UIParent)
    panel.name = "LorePath"
    panel:Hide()

    -- Scrolls with the mouse wheel; the template adds a scroll bar where the client has it.
    local ok, scroll = pcall(CreateFrame, "ScrollFrame", "LorePathSettingsScroll", panel, "UIPanelScrollFrameTemplate")
    if not ok then
        scroll = CreateFrame("ScrollFrame", "LorePathSettingsScroll", panel)
    end
    scroll:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, -4)
    scroll:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -28, 4)
    scroll:EnableMouseWheel(true)
    scroll:SetScript("OnMouseWheel", function(self, delta)
        local y = self:GetVerticalScroll() - delta * 40
        self:SetVerticalScroll(math.max(0, math.min(y, self:GetVerticalScrollRange())))
    end)
    body = CreateFrame("Frame", nil, scroll)
    body:SetSize(WIDTH + LEFT * 2, 1)
    scroll:SetScrollChild(body)
    panel.scroll, panel.body = scroll, body
    last = nil

    AddText("LorePath |cff888888v" .. (ns.VERSION or "?") .. "|r", "GameFontNormalLarge")
    panel.subtitle = AddText("Your questlines, zone by zone: what you've done, what you've missed, and where the next quest starts.",
        "GameFontHighlightSmall")

    AddHeading("Window")
    AddCheckbox("showMinimapButton", "Show minimap button",
        "Left-click opens LorePath, right-click opens these settings, and you can drag it around the minimap.")
    AddCheckbox("openOnCurrentZone", "Open on the zone you're in",
        "Each time the window opens, jump to your current zone. Off: reopen on the last zone you looked at.")

    -- Window scale: - / + buttons (works on every client, unlike slider templates)
    local scaleLabel = body:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    Place(scaleLabel, 4, 14)
    scaleLabel:SetText("Window size:")
    local minus = CreateFrame("Button", nil, body, "UIPanelButtonTemplate")
    minus:SetSize(24, 22)
    minus:SetPoint("LEFT", scaleLabel, "RIGHT", 10, 0)
    minus:SetText("-")
    local scaleValue = body:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    scaleValue:SetPoint("LEFT", minus, "RIGHT", 8, 0)
    scaleValue:SetWidth(44)
    panel.scaleValue = scaleValue
    local plus = CreateFrame("Button", nil, body, "UIPanelButtonTemplate")
    plus:SetSize(24, 22)
    plus:SetPoint("LEFT", scaleValue, "RIGHT", 8, 0)
    plus:SetText("+")
    local function Step(delta)
        local value = ns.GetSetting("scale") + delta
        value = math.max(SCALE_MIN, math.min(SCALE_MAX, math.floor(value * 10 + 0.5) / 10))
        ns.SetSetting("scale", value)
    end
    minus:SetScript("OnClick", function() Step(-SCALE_STEP) end)
    plus:SetScript("OnClick", function() Step(SCALE_STEP) end)

    local bindingText = body:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    Place(bindingText, 4, 14)
    bindingText:SetJustifyH("LEFT")
    panel.bindingText = bindingText

    AddHeading("Quests")
    AddCheckbox("hideCompleted", "Hide finished storylines",
        "Leave out storylines where you've completed every quest, so only unfinished stories show.")
    AddCheckbox("showOthers", "Show standalone quests",
        "List quests that aren't part of any chain under each zone's storylines.")
    AddCheckbox("showRepeatable", "Show repeatable quests",
        "Show daily and repeatable quests, in blue. They never count towards progress. Also the \"Repeatable\" tick box at the top of the window.")
    AddCheckbox("showAllProfessions", "Show professions you don't have",
        "List every profession under Professions in the zone list, with the ones you don't have greyed out, so you can see their quests.")
    AddCheckbox("showLevels", "Show quest levels on tiles",
        "Show each quest's minimum level at the left of its tile.")
    AddCheckbox("showSpoilers", "Show spoilers",
        "Show the full story of every quest in its details: quests you haven't started, and how quests in your log end. Off: those stay hidden until you press Reveal.")

    AddHeading("World map")
    AddCheckbox("openMapOnWaypoint", "Open the map when setting a waypoint",
        "Ctrl+clicking a quest, or Show on map, sets the game's waypoint where it starts. With this on, the world map also opens there.")
    AddText("Show quests on the map", "GameFontHighlight", 4, 14)
    AddText("A \"!\" where each quest starts: hover it for the quest, click it to set a waypoint, Shift+click to open it in LorePath. "
        .. "Also under LorePath quests in the world map's filter menu.", "GameFontHighlightSmall", 4, 2, { 0.75, 0.75, 0.75 })
    AddCheckbox("mapPinsCurrent", "Quests at your level (gold)", nil, 20)
    AddCheckbox("mapPinsLow", "Low-level quests (grey)", nil, 20)
    AddCheckbox("mapPinsHigh", "Quests above your level (red)", nil, 20)

    local open = CreateFrame("Button", nil, body, "UIPanelButtonTemplate")
    open:SetSize(150, 24)
    Place(open, 0, 24)
    open:SetText("Open LorePath")
    open:SetScript("OnClick", function()
        if SettingsPanel and SettingsPanel:IsShown() and HideUIPanel then
            HideUIPanel(SettingsPanel)
        end
        ns.Toggle(false)
    end)

    local reset = CreateFrame("Button", nil, body, "UIPanelButtonTemplate")
    reset:SetSize(150, 24)
    reset:SetPoint("LEFT", open, "RIGHT", 10, 0)
    reset:SetText("Reset to defaults")
    reset:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Reset to defaults", 1, 0.82, 0)
        GameTooltip:AddLine("Puts every setting back, re-opens collapsed storylines and zone list headings, and shows the zone list again. Your saved quest text is kept.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    reset:SetScript("OnLeave", GameTooltip_Hide)
    reset:SetScript("OnClick", function()
        ns.ResetToDefaults()
    end)

    -- Sharing collected quest text (also /lp share).
    local share = CreateFrame("Button", nil, body, "UIPanelButtonTemplate")
    share:SetSize(150, 24)
    share:SetPoint("LEFT", reset, "RIGHT", 10, 0)
    share:SetText("Share quest text")
    share:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Share quest text", 1, 0.82, 0)
        GameTooltip:AddLine("Shows a code holding the quest text you've saved that LorePath doesn't have yet, to paste into a \"Share quest text\" issue on GitHub, so everyone's LorePath gets it.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    share:SetScript("OnLeave", GameTooltip_Hide)
    share:SetScript("OnClick", function()
        if SettingsPanel and SettingsPanel:IsShown() and HideUIPanel then
            HideUIPanel(SettingsPanel)
        end
        ns.OpenShare()
    end)
    panel.shareButton = share

    panel:SetScript("OnShow", function()
        RefreshPanel()
        FitBody()
        C_Timer.After(0, FitBody) -- again once wrapped text has its final height
    end)
    panel:SetScript("OnSizeChanged", function()
        FitBody()
    end)

    if Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory then
        category = Settings.RegisterCanvasLayoutCategory(panel, panel.name)
        Settings.RegisterAddOnCategory(category)
    elseif InterfaceOptions_AddCategory then
        InterfaceOptions_AddCategory(panel)
    end
end

function ns.OpenSettings()
    if InCombatLockdown() then
        ns.Print("Settings can't be opened in combat.")
        return
    end
    -- The settings page sits underneath the LorePath window, so close the window first.
    if ns.mainFrame and ns.mainFrame:IsShown() then
        ns.mainFrame:Hide()
    end
    if category and Settings and Settings.OpenToCategory then
        local id = (category.GetID and category:GetID()) or category.ID
        local ok = pcall(Settings.OpenToCategory, id)
        if not ok and C_SettingsUtil and C_SettingsUtil.OpenSettingsPanel then
            pcall(C_SettingsUtil.OpenSettingsPanel, id)
        end
    elseif panel and InterfaceOptionsFrame_OpenToCategory then
        InterfaceOptionsFrame_OpenToCategory(panel)
        InterfaceOptionsFrame_OpenToCategory(panel)
    else
        ns.Print("Open Options > AddOns > LorePath.")
    end
end

-- ============================================================================
-- Minimap button
-- ============================================================================

local minimapButton
local atan2 = math.atan2 or math.atan

local function PositionMinimapButton()
    local angle = math.rad(ns.GetSetting("minimapAngle"))
    local radius = (Minimap:GetWidth() / 2) + 5
    minimapButton:ClearAllPoints()
    minimapButton:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * radius, math.sin(angle) * radius)
end

function ns.UpdateMinimapButton()
    if not minimapButton then
        return
    end
    if ns.GetSetting("showMinimapButton") then
        PositionMinimapButton()
        minimapButton:Show()
    else
        minimapButton:Hide()
    end
end

function ns.CreateMinimapButton()
    if minimapButton or not Minimap then
        return
    end
    local b = CreateFrame("Button", "LorePathMinimapButton", Minimap)
    b:SetSize(31, 31)
    b:SetFrameStrata("MEDIUM")
    b:SetFrameLevel(8)
    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:RegisterForDrag("LeftButton")
    b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")

    local background = b:CreateTexture(nil, "BACKGROUND")
    background:SetSize(20, 20)
    background:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
    background:SetPoint("TOPLEFT", 7, -5)
    local icon = b:CreateTexture(nil, "ARTWORK")
    icon:SetSize(17, 17)
    icon:SetTexture("Interface\\Icons\\INV_Misc_Book_09")
    icon:SetPoint("TOPLEFT", 7, -6)
    local border = b:CreateTexture(nil, "OVERLAY")
    border:SetSize(53, 53)
    border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    border:SetPoint("TOPLEFT")

    b:SetScript("OnClick", function(_, button)
        if button == "RightButton" then
            ns.OpenSettings()
        else
            ns.Toggle(false)
        end
    end)
    b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine("LorePath", 1, 0.82, 0)
        GameTooltip:AddLine("Left-click: open or close", 1, 1, 1)
        GameTooltip:AddLine("Right-click: settings", 1, 1, 1)
        GameTooltip:AddLine("Drag: move this button", 0.7, 0.7, 0.7)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", GameTooltip_Hide)
    b:SetScript("OnDragStart", function(self)
        self:SetScript("OnUpdate", function()
            local mx, my = Minimap:GetCenter()
            local cx, cy = GetCursorPosition()
            local scale = Minimap:GetEffectiveScale()
            local angle = math.deg(atan2(cy / scale - my, cx / scale - mx))
            LorePathDB.minimapAngle = angle % 360
            PositionMinimapButton()
        end)
    end)
    b:SetScript("OnDragStop", function(self)
        self:SetScript("OnUpdate", nil)
    end)

    minimapButton = b
    ns.minimapButton = b
    ns.UpdateMinimapButton()
end

-- Addon compartment (the addons menu by the minimap), declared in the TOC.
function LorePath_OnAddonCompartmentClick(_, mouseButton)
    if mouseButton == "RightButton" then
        ns.OpenSettings()
    else
        ns.Toggle(false)
    end
end
