-- LorePath settings: saved options, the Options -> AddOns page, and the minimap button.

local addonName, ns = ...

local DEFAULTS = {
    showMinimapButton = true,
    minimapAngle = 200,         -- degrees around the minimap
    openOnCurrentZone = true,   -- opening the window jumps to the zone you're in
    showOthers = true,          -- list standalone quests under the storylines
    showRepeatable = true,      -- show daily and repeatable quests (in blue)
    showSpoilers = false,       -- show the story of quests you haven't started (and how quests end)
    hideCompleted = false,      -- hide storylines you've finished
    showLevels = true,          -- show quest levels on the quest tiles
    openMapOnWaypoint = true,   -- open the world map when a waypoint is set
    scale = 1.0,                -- window scale
}
ns.DEFAULTS = DEFAULTS

local SCALE_MIN, SCALE_MAX, SCALE_STEP = 0.6, 1.4, 0.1

function ns.InitDB()
    LorePathDB = LorePathDB or {}
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

local function AddCheckbox(anchor, key, label, description)
    local cb = CreateFrame("CheckButton", nil, panel, "UICheckButtonTemplate")
    cb:SetSize(26, 26)
    cb:SetPoint("TOPLEFT", anchor, "BOTTOMLEFT", anchor == panel.subtitle and 0 or -30, -12)

    local text = (type(cb.text) == "table" and cb.text) or (type(cb.Text) == "table" and cb.Text)
        or cb:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    text:SetFontObject("GameFontHighlight")
    text:ClearAllPoints()
    text:SetPoint("LEFT", cb, "RIGHT", 4, 1)
    text:SetText(label)

    local desc = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    desc:SetPoint("TOPLEFT", cb, "BOTTOMLEFT", 30, 2)
    desc:SetWidth(540)
    desc:SetJustifyH("LEFT")
    desc:SetTextColor(0.75, 0.75, 0.75)
    desc:SetText(description)

    cb:SetScript("OnClick", function(self)
        ns.SetSetting(key, self:GetChecked() and true or false)
    end)
    checkboxes[key] = cb
    return desc
end

function ns.CreateSettingsPanel()
    if panel then
        return
    end
    panel = CreateFrame("Frame", "LorePathSettingsPanel", UIParent)
    panel.name = "LorePath"
    panel:Hide()

    local title = panel:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", 16, -16)
    title:SetText("LorePath |cff888888v" .. (ns.VERSION or "?") .. "|r")

    local subtitle = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    subtitle:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -8)
    subtitle:SetWidth(560)
    subtitle:SetJustifyH("LEFT")
    subtitle:SetText("Your questlines, zone by zone: what you've done, what you've missed, and where the next quest starts.")
    panel.subtitle = subtitle

    local anchor = AddCheckbox(subtitle, "showMinimapButton", "Show minimap button",
        "Left-click opens LorePath, right-click opens these settings, and you can drag it around the minimap.")
    anchor = AddCheckbox(anchor, "openOnCurrentZone", "Open on the zone you're in",
        "Each time the window opens, jump to your current zone. Off: reopen on the last zone you looked at.")
    anchor = AddCheckbox(anchor, "hideCompleted", "Hide finished storylines",
        "Leave out storylines where you've completed every quest, so only unfinished stories show.")
    anchor = AddCheckbox(anchor, "showOthers", "Show standalone quests",
        "List quests that aren't part of any chain under each zone's storylines.")
    anchor = AddCheckbox(anchor, "showRepeatable", "Show repeatable quests",
        "Show daily and repeatable quests, in blue. They never count towards progress. Also the \"Repeatable\" tick box at the top of the window.")
    anchor = AddCheckbox(anchor, "showSpoilers", "Show spoilers",
        "Show the full story of every quest in its details: quests you haven't started, and how quests in your log end. Off: those stay hidden until you press Reveal.")
    anchor = AddCheckbox(anchor, "showLevels", "Show quest levels on tiles",
        "Show each quest's minimum level at the left of its tile.")
    anchor = AddCheckbox(anchor, "openMapOnWaypoint", "Open the map when setting a waypoint",
        "Ctrl+clicking a quest, or Show on map, sets the game's waypoint where it starts. With this on, the world map also opens there.")

    -- Window scale: - / + buttons (works on every client, unlike slider templates)
    local scaleLabel = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    scaleLabel:SetPoint("TOPLEFT", anchor, "BOTTOMLEFT", -26, -22)
    scaleLabel:SetText("Window size:")
    local minus = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    minus:SetSize(24, 22)
    minus:SetPoint("LEFT", scaleLabel, "RIGHT", 10, 0)
    minus:SetText("-")
    local scaleValue = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    scaleValue:SetPoint("LEFT", minus, "RIGHT", 8, 0)
    scaleValue:SetWidth(44)
    panel.scaleValue = scaleValue
    local plus = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
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

    local bindingText = panel:CreateFontString(nil, "ARTWORK", "GameFontHighlightSmall")
    bindingText:SetPoint("TOPLEFT", scaleLabel, "BOTTOMLEFT", 0, -20)
    bindingText:SetJustifyH("LEFT")
    panel.bindingText = bindingText

    local open = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
    open:SetSize(150, 24)
    open:SetPoint("TOPLEFT", bindingText, "BOTTOMLEFT", 0, -16)
    open:SetText("Open LorePath")
    open:SetScript("OnClick", function()
        if SettingsPanel and SettingsPanel:IsShown() and HideUIPanel then
            HideUIPanel(SettingsPanel)
        end
        ns.Toggle(false)
    end)

    local reset = CreateFrame("Button", nil, panel, "UIPanelButtonTemplate")
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

    panel:SetScript("OnShow", RefreshPanel)

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
