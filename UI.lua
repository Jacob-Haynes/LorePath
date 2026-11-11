-- LorePath window: zone list on the left, the selected zone's storylines drawn as
-- quest graphs on the right. Click a quest for its details (Detail.lua); Ctrl+click
-- sets a waypoint where it starts.

local addonName, ns = ...

BINDING_HEADER_LOREPATH = "LorePath"
BINDING_NAME_LOREPATH_TOGGLE = "Open / close LorePath"

local S = ns.STATUS

-- Quest boxes are tinted by status (Attune style); the quest name is coloured by
-- difficulty, the same way your quest log colours it.
local STATUS_STYLE = {
    [S.DONE]      = { bg = { 0.20, 0.36, 0.15 }, border = { 0.42, 0.66, 0.30 }, text = { 1, 1, 1 } },
    [S.ACTIVE]    = { bg = { 0.42, 0.33, 0.07 }, border = { 0.90, 0.72, 0.22 }, text = { 1, 1, 1 } },
    [S.AVAILABLE] = { bg = { 0.12, 0.12, 0.12 }, border = { 0.45, 0.45, 0.45 } }, -- text: difficulty colour
    [S.LEVEL]     = { bg = { 0.10, 0.10, 0.10 }, border = { 0.32, 0.32, 0.32 } },             -- text: difficulty colour
    [S.BLOCKED]   = { bg = { 0.08, 0.08, 0.08 }, border = { 0.26, 0.26, 0.26 }, text = { 0.55, 0.55, 0.55 } },
    [S.MISSED]    = { bg = { 0.06, 0.06, 0.06 }, border = { 0.18, 0.18, 0.18 }, text = { 0.40, 0.40, 0.40 } },
    [S.REPEATABLE] = { bg = { 0.07, 0.14, 0.26 }, border = { 0.35, 0.65, 1.00 } }, -- text: difficulty colour
}

-- WoW's daily/repeatable quest blue, for the "!" marker and the border.
local REPEATABLE_BLUE = { 0.35, 0.65, 1.00 }
-- A repeatable quest you can't take yet keeps its locked look, with a dim blue border.
local REPEATABLE_LOCKED_BORDER = { 0.20, 0.36, 0.55 }

local STATUS_TEXT = {
    [S.DONE]      = "Completed",
    [S.ACTIVE]    = "In your quest log",
    [S.AVAILABLE] = "Available now",
    [S.LEVEL]     = "Your level is too low",
    [S.BLOCKED]   = "Needs an earlier quest",
    [S.MISSED]    = "Skipped (you went past this breadcrumb)",
    [S.REPEATABLE] = "Repeatable: you can take it again and again",
}

-- Second line of a quest box.
local STATUS_SHORT = {
    [S.DONE]      = "Completed",
    [S.ACTIVE]    = "In quest log",
    [S.AVAILABLE] = "Available",
    [S.LEVEL]     = "Too high level",
    [S.BLOCKED]   = "Locked",
    [S.MISSED]    = "Skipped",
    [S.REPEATABLE] = "Repeatable",
}

-- Small marker drawn on the corner of a quest's icon.
local STATUS_MARK = {
    [S.DONE]      = "Interface\\RaidFrame\\ReadyCheck-Ready",
    [S.ACTIVE]    = "Interface\\GossipFrame\\ActiveQuestIcon",
    [S.AVAILABLE] = "Interface\\GossipFrame\\AvailableQuestIcon",
    [S.BLOCKED]   = "Interface\\LFGFrame\\UI-LFG-ICON-LOCK",
    [S.MISSED]    = "Interface\\RaidFrame\\ReadyCheck-NotReady",
}

local LEGEND_ORDER = { S.DONE, S.ACTIVE, S.AVAILABLE, S.REPEATABLE, S.LEVEL, S.BLOCKED }

-- WoW's quest difficulty colours (QuestDifficultyColors in Blizzard's UI code).
local DIFFICULTY = {
    impossible    = { 1.00, 0.10, 0.10 },
    verydifficult = { 1.00, 0.50, 0.25 },
    difficult     = { 1.00, 0.82, 0.00 },
    standard      = { 0.25, 0.75, 0.25 },
    trivial       = { 0.50, 0.50, 0.50 },
}

local QUEST_ICON = "Interface\\Icons\\INV_Misc_Note_01"
local BREADCRUMB_ICON = "Interface\\Icons\\INV_Letter_15"
local ROCK = "Interface\\FrameGeneral\\UI-Background-Rock"
local PLUS = "Interface\\Buttons\\UI-PlusButton-Up"
local MINUS = "Interface\\Buttons\\UI-MinusButton-Up"

local FRAME_W, FRAME_H = 1120, 660
local LIST_W = 220
local NODE_W, NODE_H = 186, 36
local COL_GAP, ROW_GAP = 34, 10
local PAD = 14
local HEADER_H = 26
local SECTION_GAP = 18

local frame
local history = {} -- where you were before each jump to a quest: { zone, v, h }
local HISTORY_MAX = 20

local function UpdateBackButton()
    if frame and frame.backButton then
        frame.backButton:SetShown(#history > 0)
    end
end

local function ClearHistory()
    wipe(history)
    UpdateBackButton()
end
local selectedZone
local zoneRows = {}
local searchText = "" -- while not empty, the zone list shows quest search results
local renderedKeys = {}
local pools = { nodes = {}, lines = {}, sections = {}, texts = {} }
local used = { nodes = 0, lines = 0, sections = 0, texts = 0 }

-- ============================================================================
-- Small helpers
-- ============================================================================

local function ItemText(itemID)
    local name = C_Item and C_Item.GetItemNameByID and C_Item.GetItemNameByID(itemID)
    if not name then
        if C_Item and C_Item.RequestLoadItemDataByID then
            C_Item.RequestLoadItemDataByID(itemID)
        end
        return "Item #" .. itemID
    end
    local quality = C_Item.GetItemQualityByID and C_Item.GetItemQualityByID(itemID)
    local color = quality and ITEM_QUALITY_COLORS and ITEM_QUALITY_COLORS[quality]
    if color and color.hex then
        return color.hex .. name .. "|r"
    end
    return name
end

local function NameList(ids)
    local names = {}
    for _, id in ipairs(ids) do
        table.insert(names, ns.GetQuestNameOrID(id))
    end
    return table.concat(names, ", ")
end

-- The level below which quests turn grey (Classic's formula).
local function GrayLevel(level)
    if level <= 5 then
        return 0
    elseif level <= 39 then
        return level - math.floor(level / 10) - 5
    end
    return level - math.floor(level / 5) - 1
end

-- Colour for a quest of this level, matching the quest log.
local function LevelRangeText(low, high)
    return low == high and tostring(low) or (low .. "-" .. high)
end

local function DifficultyColor(questLevel)
    local level = UnitLevel("player") or 1
    local diff = questLevel - level
    if diff >= 5 then
        return DIFFICULTY.impossible
    elseif diff >= 3 then
        return DIFFICULTY.verydifficult
    elseif diff >= -2 then
        return DIFFICULTY.difficult
    elseif questLevel > GrayLevel(level) then
        return DIFFICULTY.standard
    end
    return DIFFICULTY.trivial
end

local function Hex(c)
    return string.format("|cff%02x%02x%02x", math.floor(c[1] * 255 + 0.5), math.floor(c[2] * 255 + 0.5), math.floor(c[3] * 255 + 0.5))
end

-- Quests picked up inside a dungeon or raid show its entrance portal, the
-- swirl the map uses (an atlas on newer clients; a portal icon otherwise).
local PORTAL_ATLAS = { dungeon = "Dungeon", raid = "Raid" }
local PORTAL_ICON = "Interface\\Icons\\Spell_Arcane_PortalUnderCity"

-- Icon for a quest box: your class icon for class quests, a portal for quests
-- picked up inside a dungeon or raid, a letter for breadcrumbs, a scroll for
-- everything else.
local function QuestIcon(q)
    if q.cl then
        local _, token = UnitClass("player")
        if token then
            return "Interface\\Icons\\ClassIcon_" .. token:sub(1, 1) .. token:sub(2):lower()
        end
    end
    if q.di then
        return PORTAL_ICON
    end
    if q.bc then
        return BREADCRUMB_ICON
    end
    return QUEST_ICON
end

-- Puts a quest's icon on a texture, using the portal atlas when the client has it.
local function SetQuestIcon(tex, q)
    local atlas = q.di and not q.cl and PORTAL_ATLAS[ns.GetInstanceKind(q.di) or ""]
    if atlas and C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo(atlas) then
        tex:SetAtlas(atlas)
        return
    end
    tex:SetTexture(QuestIcon(q))
    tex:SetTexCoord(0.08, 0.92, 0.08, 0.92) -- trim the icon border (an atlas resets this)
end

-- Zone list icons (issue #15). Zones and most instances use AllTheThings' icon
-- for them (ns.ZoneIcons, ns.InstanceInfo[].ic); the rest fall back to a hand
-- pick, then their continent's icon, then a generic one.
local GENERIC_ICON = {
    map = "Interface\\Icons\\INV_Misc_Map_01",
    dungeon = "Interface\\Icons\\INV_Misc_Key_03",
    raid = "Interface\\Icons\\INV_Misc_Head_Dragon_01",
    battleground = "Interface\\Icons\\INV_BannerPVP_02",
}
-- Zones whose ATT icon is ATT's own texture, which LorePath doesn't ship.
local ZONE_ICON_OVERRIDES = {
    [2521] = "Interface\\Icons\\Spell_Nature_Cyclone", -- Zephras Isle, an island in the sky
}

local function ZoneIcon(zoneID)
    if zoneID == "class" then
        local _, token = UnitClass("player")
        return token and ("Interface\\Icons\\ClassIcon_" .. token:sub(1, 1) .. token:sub(2):lower()) or GENERIC_ICON.map
    elseif ns.IsSpecialPage(zoneID) then
        return ns.ProfessionIcon(tonumber(string.match(zoneID, "%d+")))
    end
    local icon = ZONE_ICON_OVERRIDES[zoneID] or (ns.ZoneIcons and ns.ZoneIcons[zoneID])
    if icon then
        return icon
    end
    local kind = ns.GetInstanceKind(zoneID)
    if kind then
        local info = ns.InstanceInfo and ns.InstanceInfo[zoneID]
        return info and info.ic or GENERIC_ICON[kind] or GENERIC_ICON.dungeon
    end
    local continent = ns.ZoneContinents and ns.ZoneContinents[zoneID]
    if continent and continent ~= 0 and continent ~= zoneID and ns.ZoneIcons and ns.ZoneIcons[continent] then
        return ns.ZoneIcons[continent]
    end
    return GENERIC_ICON.map
end

-- Icon for a zone list heading: the continent's, or Dungeons / Raids.
local function HeadingIcon(group)
    if group.icon then
        return group.icon
    end
    if group.kind then
        return GENERIC_ICON[group.kind] or GENERIC_ICON.dungeon
    end
    return group.continentID and ns.ZoneIcons and ns.ZoneIcons[group.continentID] or GENERIC_ICON.map
end

-- 1px border made of four textures, so it works without BackdropTemplate.
local function AddBorder(f, layer)
    local edges = {}
    for i = 1, 4 do
        edges[i] = f:CreateTexture(nil, layer or "BORDER")
    end
    edges[1]:SetPoint("TOPLEFT"); edges[1]:SetPoint("TOPRIGHT"); edges[1]:SetHeight(1)
    edges[2]:SetPoint("BOTTOMLEFT"); edges[2]:SetPoint("BOTTOMRIGHT"); edges[2]:SetHeight(1)
    edges[3]:SetPoint("TOPLEFT"); edges[3]:SetPoint("BOTTOMLEFT"); edges[3]:SetWidth(1)
    edges[4]:SetPoint("TOPRIGHT"); edges[4]:SetPoint("BOTTOMRIGHT"); edges[4]:SetWidth(1)
    f.SetBorderColor = function(_, r, g, b, a)
        for _, e in ipairs(edges) do
            e:SetColorTexture(r, g, b, a or 1)
        end
    end
end

-- Horizontal fade, used for header underlines. Falls back to a flat colour.
local function SetFade(tex, r, g, b, a)
    tex:SetColorTexture(1, 1, 1, 1)
    local ok = CreateColor and pcall(tex.SetGradient, tex, "HORIZONTAL", CreateColor(r, g, b, a), CreateColor(r, g, b, 0))
    if not ok then
        tex:SetColorTexture(r, g, b, a * 0.5)
    end
end

-- How far (in pixels) the cursor must move with the button held before a press
-- becomes a drag. Below it, a press on a quest or header is still a click.
local PAN_THRESHOLD = 5

-- Starts a possible pan of `scroll` from where the cursor is now.
local function BeginPan(scroll)
    local cx, cy = GetCursorPosition()
    scroll.pan = { cx = cx, cy = cy, x = scroll:GetHorizontalScroll(), y = scroll:GetVerticalScroll() }
    scroll.dragged = false
end

-- Makes a scroll frame scroll with the mouse wheel (shift for sideways) and pan
-- when dragged with the left mouse button.
local function MakeScrollable(scroll, allowPan)
    scroll:EnableMouseWheel(true)
    scroll:SetScript("OnMouseWheel", function(self, delta)
        if IsShiftKeyDown() then
            local x = self:GetHorizontalScroll() - delta * 60
            self:SetHorizontalScroll(math.max(0, math.min(x, self:GetHorizontalScrollRange())))
        else
            local y = self:GetVerticalScroll() - delta * 60
            self:SetVerticalScroll(math.max(0, math.min(y, self:GetVerticalScrollRange())))
        end
    end)
    if not allowPan then
        return
    end
    scroll:EnableMouse(true)
    scroll:SetScript("OnMouseDown", function(self, button)
        if button == "LeftButton" then
            BeginPan(self)
        end
    end)
    scroll:SetScript("OnMouseUp", function(self)
        self.pan = nil
    end)
    scroll:SetScript("OnUpdate", function(self)
        local pan = self.pan
        if not pan then
            return
        end
        if not IsMouseButtonDown("LeftButton") then
            self.pan = nil
            return
        end
        local cx, cy = GetCursorPosition()
        local scale = self:GetEffectiveScale()
        local dx, dy = (cx - pan.cx) / scale, (cy - pan.cy) / scale
        if not self.dragged then
            if math.abs(dx) < PAN_THRESHOLD and math.abs(dy) < PAN_THRESHOLD then
                return
            end
            self.dragged = true -- from here on it's a drag: the release won't click
            GameTooltip:Hide()
        end
        self:SetHorizontalScroll(math.max(0, math.min(pan.x - dx, self:GetHorizontalScrollRange())))
        self:SetVerticalScroll(math.max(0, math.min(pan.y + dy, self:GetVerticalScrollRange())))
    end)
end

-- Quest boxes and storyline headers sit on top of the graph and take the mouse,
-- so they start the graph's pan themselves. A press that turns into a drag pans;
-- one that doesn't is a normal click.
local function StartGraphPan(_, button)
    if button == "LeftButton" and frame and frame.graphScroll then
        BeginPan(frame.graphScroll)
    end
end

-- True if the press now being released was a drag (so it shouldn't click).
local function WasDragged()
    return frame and frame.graphScroll and frame.graphScroll.dragged or false
end

-- True while a drag is moving the graph (so hovering doesn't pop up tooltips).
local function IsPanning()
    local scroll = frame and frame.graphScroll
    return scroll and scroll.pan ~= nil and scroll.dragged or false
end

-- Shared with Detail.lua (the quest detail panel), so both draw quests the same way.
ns.ui = {
    Hex = Hex,
    DifficultyColor = DifficultyColor,
    ItemText = ItemText,
    QuestIcon = QuestIcon,
    AddBorder = AddBorder,
    SetFade = SetFade,
    MakeScrollable = MakeScrollable,
    ZoneIcon = ZoneIcon,
    STATUS_STYLE = STATUS_STYLE,
    STATUS_TEXT = STATUS_TEXT,
    DIFFICULTY = DIFFICULTY,
    REPEATABLE_BLUE = REPEATABLE_BLUE,
}

-- ============================================================================
-- Collapsed state (saved per account)
-- ============================================================================

local function CollapsedTable(name)
    if not LorePathDB then
        return {}
    end
    LorePathDB[name] = LorePathDB[name] or {}
    return LorePathDB[name]
end

-- Sections you haven't opened or closed yourself start collapsed once finished.
local function IsSectionCollapsed(key, complete)
    local value = CollapsedTable("collapsed")[key]
    if value == nil then
        return complete
    end
    return value
end

local RenderZone -- defined below

local function SetSectionCollapsed(key, collapsed)
    CollapsedTable("collapsed")[key] = collapsed
    RenderZone()
end

-- ============================================================================
-- Pools (frames are reused between renders)
-- ============================================================================

local function ResetPools()
    for kind, pool in pairs(pools) do
        for _, obj in ipairs(pool) do
            obj:Hide()
        end
        used[kind] = 0
    end
end

-- A quest's tooltip, shown by its box in the graph or its row in search results.
local function ShowQuestTooltip(owner, id, storyline)
    local q = ns.Quests[id]
    local status = ns.GetStatus(id)
    GameTooltip:SetOwner(owner, "ANCHOR_RIGHT")
    GameTooltip:AddLine(ns.GetQuestNameOrID(id), 1, 0.82, 0)
    local dc = DifficultyColor(q.l or 1)
    GameTooltip:AddLine("Requires level " .. (q.l or 1), dc[1], dc[2], dc[3])
    local lock = ns.GetLockReason(id)
    local pending = status ~= S.DONE and status ~= S.ACTIVE
    if q.mr then
        local rc = (pending and ns.BelowMinRep(q)) and DIFFICULTY.impossible or { 0.75, 0.75, 0.75 }
        GameTooltip:AddLine("Requires " .. ns.ReputationText(q.mr), rc[1], rc[2], rc[3], true)
    end
    if q.xr then
        local rc = (pending and ns.AboveMaxRep(q)) and DIFFICULTY.impossible or { 0.75, 0.75, 0.75 }
        GameTooltip:AddLine("Only below " .. ns.ReputationText(q.xr), rc[1], rc[2], rc[3], true)
    end
    local style = STATUS_STYLE[status]
    local sc = style.text or { 1, 1, 1 }
    if status == S.DONE or status == S.ACTIVE or status == S.REPEATABLE then
        sc = style.border
    end
    local statusText = STATUS_TEXT[status]
    if status == S.LEVEL and lock == "minrep" then
        statusText = "Your reputation is too low"
    elseif status == S.LEVEL and lock == "skill" then
        statusText = ns.HasProfession(q.sk) and "Your skill is too low" or "You don't have this profession"
    elseif status == S.MISSED and lock == "maxrep" and not q.bc then
        statusText = "No longer available (your reputation is too high)"
    end
    GameTooltip:AddLine(statusText, sc[1], sc[2], sc[3])
    if status == S.BLOCKED then
        local missing = ns.MissingPrereq(id)
        if missing then
            GameTooltip:AddLine("Needs: " .. ns.GetQuestNameOrID(missing), 0.9, 0.9, 0.9, true)
        end
    elseif status == S.LEVEL and q.l and (UnitLevel("player") or 1) < q.l then
        GameTooltip:AddLine("Needs level " .. q.l, 0.9, 0.9, 0.9)
    elseif status == S.LEVEL and lock == "skill" then
        GameTooltip:AddLine("Needs " .. ns.SkillText(q), 0.9, 0.9, 0.9)
    elseif status == S.LEVEL and lock == "minrep" then
        GameTooltip:AddLine("Needs " .. ns.ReputationText(q.mr), 0.9, 0.9, 0.9, true)
    end
    if q.bc then
        GameTooltip:AddLine("Breadcrumb: leads you to another quest", 0.75, 0.75, 0.75)
    end
    if q.rp and status ~= S.REPEATABLE then
        local c = REPEATABLE_BLUE
        GameTooltip:AddLine("Repeatable: doesn't count towards progress", c[1], c[2], c[3])
    end
    if storyline then
        local before = storyline.parents[id]
        if before and #before > 0 then
            GameTooltip:AddLine("After: " .. NameList(before), 0.75, 0.75, 0.75, true)
        end
        local after = storyline.childrenOf and storyline.childrenOf[id]
        if after and #after > 0 then
            GameTooltip:AddLine("Leads to: " .. NameList(after), 0.75, 0.75, 0.75, true)
        end
    end
    if ns.IsSpecialPage(selectedZone) then
        -- The Class and profession pages gather quests from every zone.
        GameTooltip:AddLine("Zone: " .. ns.GetMapName(q.z), 0.75, 0.75, 0.75)
    end
    if q.m then
        GameTooltip:AddLine(string.format("Starts in %s (%.1f, %.1f)", ns.GetMapName(q.m), q.x, q.y), 0.75, 0.75, 0.75)
    else
        if q.di then
            GameTooltip:AddLine("Picked up inside " .. ns.GetMapName(q.di), 0.75, 0.75, 0.75)
        else
            GameTooltip:AddLine("Start location unknown", 0.6, 0.6, 0.6)
        end
    end
    if q.rw then
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine("Rewards:", 1, 0.82, 0)
        for _, itemID in ipairs(q.rw) do
            GameTooltip:AddLine("  " .. ItemText(itemID), 1, 1, 1)
        end
    end
    -- AllTheThings' note (also in the details), e.g. where its item drops.
    local note = ns.QuestNotes and ns.QuestNotes[id]
    if note then
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine("Good to know:", 1, 0.82, 0)
        GameTooltip:AddLine(note, 0.65, 0.82, 1, true)
    end
    GameTooltip:AddLine(" ")
    GameTooltip:AddLine("Click for details.", 0.5, 0.8, 1)
    if q.m then
        GameTooltip:AddLine("Ctrl+click to set a waypoint where it starts.", 0.5, 0.8, 1)
    end
    if status == S.ACTIVE then
        GameTooltip:AddLine("Shift+click to open it in your quest log.", 0.5, 0.8, 1)
    end
    GameTooltip:Show()
end

local function ShowNodeTooltip(node)
    if IsPanning() then
        return -- passing over quests while dragging the graph
    end
    ShowQuestTooltip(node, node.questID, node.storyline)
end

local function AcquireNode(parent)
    used.nodes = used.nodes + 1
    local node = pools.nodes[used.nodes]
    if not node then
        node = CreateFrame("Button", nil, parent)
        node:SetSize(NODE_W, NODE_H)
        node.bg = node:CreateTexture(nil, "BACKGROUND")
        node.bg:SetAllPoints()
        AddBorder(node, "BORDER")
        node.icon = node:CreateTexture(nil, "ARTWORK")
        node.icon:SetSize(NODE_H - 8, NODE_H - 8)
        node.icon:SetPoint("LEFT", 4, 0)
        node.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
        node.mark = node:CreateTexture(nil, "OVERLAY")
        node.mark:SetSize(20, 20)
        node.mark:SetPoint("BOTTOMRIGHT", node.icon, "BOTTOMRIGHT", 6, -4)
        node.text = node:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        node.text:SetPoint("TOPLEFT", node.icon, "TOPRIGHT", 6, -1)
        node.text:SetPoint("RIGHT", -5, 0)
        node.text:SetJustifyH("LEFT")
        node.text:SetWordWrap(false)
        node.sub = node:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        node.sub:SetPoint("BOTTOMLEFT", node.icon, "BOTTOMRIGHT", 6, 1)
        node.sub:SetPoint("RIGHT", -5, 0)
        node.sub:SetJustifyH("LEFT")
        node.sub:SetWordWrap(false)
        local hl = node:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        hl:SetColorTexture(1, 1, 1, 0.10)
        -- Gold wash on the quest you just jumped to.
        node.flash = node:CreateTexture(nil, "OVERLAY", nil, 2)
        node.flash:SetAllPoints()
        node.flash:SetColorTexture(1, 0.82, 0, 0.35)
        node.flash:Hide()
        node:SetScript("OnEnter", ShowNodeTooltip)
        node:SetScript("OnLeave", GameTooltip_Hide)
        -- Click opens the detail panel (again to close it); Ctrl+click sets the waypoint;
        -- Shift+click on a quest you're on opens it in the game's quest log.
        -- Dragging from a quest pans the graph instead.
        node:SetScript("OnMouseDown", StartGraphPan)
        node:SetScript("OnClick", function(self)
            if WasDragged() then
                return
            end
            if IsControlKeyDown() then
                ns.ShowQuestStart(self.questID)
            elseif IsShiftKeyDown() and ns.IsOnQuest(self.questID) then
                ns.OpenInQuestLog(self.questID)
            else
                ns.ToggleDetail(self.questID)
            end
        end)
        pools.nodes[used.nodes] = node
    end
    node:SetParent(parent)
    node:Show()
    return node
end

local function AcquireLine(parent)
    used.lines = used.lines + 1
    local line = pools.lines[used.lines]
    if not line then
        line = parent:CreateLine(nil, "ARTWORK")
        line:SetThickness(3)
        pools.lines[used.lines] = line
    end
    line:Show()
    return line
end

local function AcquireText(parent, font)
    used.texts = used.texts + 1
    local text = pools.texts[used.texts]
    if not text then
        text = parent:CreateFontString(nil, "OVERLAY", font)
        text:SetJustifyH("LEFT")
        pools.texts[used.texts] = text
    end
    text:SetFontObject(font)
    text:ClearAllPoints()
    text:Show()
    return text
end

-- A collapsible section header: [+/-] Title  3 / 7   [Show on map]  Next: ...
local function AcquireSection(parent)
    used.sections = used.sections + 1
    local s = pools.sections[used.sections]
    if not s then
        s = CreateFrame("Button", nil, parent)
        s:SetHeight(HEADER_H)
        s.toggle = s:CreateTexture(nil, "ARTWORK")
        s.toggle:SetSize(14, 14)
        s.toggle:SetPoint("LEFT", 0, 0)
        s.title = s:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        s.title:SetPoint("LEFT", s.toggle, "RIGHT", 6, 0)
        s.count = s:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        s.count:SetPoint("LEFT", s.title, "RIGHT", 8, 0)
        s.next = CreateFrame("Button", nil, s, "UIPanelButtonTemplate")
        s.next:SetSize(100, 20)
        s.next:SetText("Show on map")
        s.next:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine("Show on map", 1, 0.82, 0)
            GameTooltip:AddLine(string.format("Sets a waypoint where %s starts%s.",
                ns.GetQuestNameOrID(self.targetQuest),
                ns.GetSetting("openMapOnWaypoint") and " and opens the world map" or ""), 1, 1, 1, true)
            GameTooltip:Show()
        end)
        s.next:SetScript("OnLeave", GameTooltip_Hide)
        -- "Next: ..." / "First finish: ..." - click to jump to that quest.
        s.stepButton = CreateFrame("Button", nil, s)
        s.stepButton:SetHeight(HEADER_H - 4)
        s.step = s.stepButton:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        s.step:SetPoint("LEFT", 2, 0)
        local stepHL = s.stepButton:CreateTexture(nil, "HIGHLIGHT")
        stepHL:SetAllPoints()
        stepHL:SetColorTexture(1, 1, 1, 0.08)
        s.stepButton:SetScript("OnMouseDown", StartGraphPan)
        s.stepButton:SetScript("OnClick", function(self)
            if not WasDragged() then
                ns.FocusQuest(self.targetQuest)
            end
        end)
        s.stepButton:SetScript("OnEnter", function(self)
            if IsPanning() then
                return
            end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine(ns.GetQuestNameOrID(self.targetQuest), 1, 0.82, 0)
            local q = ns.Quests[self.targetQuest]
            if q and q.z ~= selectedZone then
                GameTooltip:AddLine("In " .. ns.GetMapName(q.z), 0.75, 0.75, 0.75)
            end
            GameTooltip:AddLine("Click to show this quest.", 0.5, 0.8, 1)
            GameTooltip:Show()
        end)
        s.stepButton:SetScript("OnLeave", GameTooltip_Hide)
        s.line = s:CreateTexture(nil, "ARTWORK")
        s.line:SetPoint("BOTTOMLEFT", 0, 0)
        s.line:SetPoint("BOTTOMRIGHT", 0, 0)
        s.line:SetHeight(1)
        SetFade(s.line, 0.85, 0.68, 0.25, 0.7)
        local hl = s:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        SetFade(hl, 1, 0.82, 0, 0.10)
        s:SetScript("OnMouseDown", StartGraphPan)
        s:SetScript("OnClick", function(self)
            if not WasDragged() then
                SetSectionCollapsed(self.key, not self.collapsed)
            end
        end)
        pools.sections[used.sections] = s
    end
    s:SetParent(parent)
    s:Show()
    return s
end

local function StyleNode(node, id, storyline)
    local status = ns.GetStatus(id)
    local q = ns.Quests[id]
    local style = STATUS_STYLE[status]
    node.questID = id
    node.storyline = storyline
    node.flash:SetShown(id == ns.focusedQuest)
    node.bg:SetColorTexture(style.bg[1], style.bg[2], style.bg[3], 0.95)
    local border = style.border
    if q.rp and (status == S.LEVEL or status == S.BLOCKED) then
        border = REPEATABLE_LOCKED_BORDER
    end
    if id == ns.detailQuest then
        border = { 1, 0.82, 0 } -- the quest shown in the detail panel
    end
    node:SetBorderColor(border[1], border[2], border[3], 1)
    SetQuestIcon(node.icon, q)
    node.icon:SetDesaturated(status == S.BLOCKED or status == S.MISSED)
    local mark = STATUS_MARK[status]
    node.mark:SetShown(mark ~= nil)
    if mark then
        node.mark:SetTexture(mark)
    end
    -- Too high for you yet: a grey "!", like a quest that isn't available yet.
    node.mark:SetDesaturated(status == S.LEVEL)
    node.mark:SetVertexColor(1, 1, 1)
    if status == S.LEVEL then
        node.mark:SetShown(true)
        node.mark:SetTexture(STATUS_MARK[S.AVAILABLE])
    elseif status == S.REPEATABLE then
        -- The blue "!" of a daily quest: the yellow one, desaturated and tinted.
        node.mark:SetShown(true)
        node.mark:SetTexture(STATUS_MARK[S.AVAILABLE])
        node.mark:SetDesaturated(true)
        node.mark:SetVertexColor(REPEATABLE_BLUE[1], REPEATABLE_BLUE[2], REPEATABLE_BLUE[3])
    end

    -- The level number carries the difficulty colour: red when it's too high for
    -- you, then yellow (your level), green (easy) or grey (low level), as in the
    -- quest log. Names of quests your level or skill is too low for stay neutral.
    -- A reputation lock isn't a level problem, so the name keeps its difficulty colour.
    local lock = ns.GetLockReason(id)
    local tc = style.text or DifficultyColor(q.l or 1)
    if status == S.LEVEL and lock ~= "minrep" then
        tc = { 0.85, 0.85, 0.85 }
    end
    node.text:SetText(ns.GetQuestNameOrID(id))
    node.text:SetTextColor(tc[1], tc[2], tc[3])
    if status == S.LEVEL and lock == "minrep" then
        node.sub:SetText("|cffccccccNeeds " .. ns.ReputationText(q.mr) .. "|r")
    elseif status == S.MISSED and lock == "maxrep" and not q.bc then
        node.sub:SetText("Closed at " .. ns.ReputationText(q.xr))
    elseif status == S.LEVEL then
        -- Shown even with levels turned off, since it's the only sign of why.
        local playerLevel = UnitLevel("player") or 1
        if q.l and playerLevel < q.l then
            node.sub:SetText(Hex(DIFFICULTY.impossible) .. "Lv " .. q.l .. "|r")
        else
            node.sub:SetText(Hex(DIFFICULTY.impossible) .. "Needs " .. ns.SkillText(q) .. "|r")
        end
    else
        local short = STATUS_SHORT[status]
        if status == S.REPEATABLE then
            short = Hex(REPEATABLE_BLUE) .. short .. "|r"
        end
        if ns.GetSetting("showLevels") then
            node.sub:SetText(Hex(DifficultyColor(q.l or 1)) .. "Lv " .. (q.l or 1) .. "|r  " .. short)
        else
            node.sub:SetText(short)
        end
    end
end

-- ============================================================================
-- Storyline rendering
-- ============================================================================

local function NextStepText(kind, id, detail)
    if kind == "available" then
        return "|cffffd100Next:|r " .. ns.GetQuestNameOrID(id)
    elseif kind == "active" then
        return "|cffffd100In progress:|r " .. ns.GetQuestNameOrID(id)
    elseif kind == "level" then
        return "|cffaaaaaaNext part at level " .. (detail or "?") .. "|r"
    elseif kind == "reputation" then
        return "|cffaaaaaaNext part needs " .. (detail or "more reputation") .. "|r"
    elseif kind == "blocked" then
        if detail then
            return "|cffaaaaaaFirst finish:|r " .. ns.GetQuestNameOrID(detail)
        end
        return "|cffaaaaaaWaiting on an earlier quest|r"
    end
    return "|cff6bd35fStoryline complete|r"
end

local function NodeX(col)
    return PAD + col * (NODE_W + COL_GAP)
end

local function NodeY(top, row)
    return top + row * (NODE_H + ROW_GAP)
end

-- "3 / 10", plus "+4 repeatable" in blue. Repeatables are never "done", so they
-- sit outside the count; showing them stops a page of dailies reading as empty.
-- `short` gives the compact form for the zone list ("3/10 +4").
-- Colour of a zone list entry by how much of it you've done: grey before you
-- start, then red, orange at 40%, WoW's gold at 80%, and on towards a
-- yellow-green that stays clearly short of the green a finished entry gets
-- (so green always means done).
local PROGRESS_NOT_STARTED = { 0.62, 0.62, 0.62 }
local PROGRESS_DONE = { 0.42, 0.83, 0.37 } -- the same green as before
local PROGRESS_STOPS = { -- { fraction done, colour }
    { 0.0, { 1.00, 0.25, 0.25 } }, -- red: just started
    { 0.4, { 1.00, 0.55, 0.15 } }, -- orange
    { 0.8, { 1.00, 0.82, 0.20 } }, -- WoW's gold
    { 1.0, { 0.80, 0.86, 0.25 } }, -- yellow-green, never quite reached before it's done
}

local function ProgressColor(done, total)
    if total <= 0 or done <= 0 then
        return PROGRESS_NOT_STARTED
    end
    if done >= total then
        return PROGRESS_DONE
    end
    local p = done / total
    for i = 1, #PROGRESS_STOPS - 1 do
        local from, to = PROGRESS_STOPS[i], PROGRESS_STOPS[i + 1]
        if p <= to[1] then
            local t = (p - from[1]) / (to[1] - from[1])
            local a, b = from[2], to[2]
            return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t }
        end
    end
    return PROGRESS_STOPS[#PROGRESS_STOPS][2]
end
ns.ui.ProgressColor = ProgressColor

local function ProgressText(done, total, repeatables, complete, short)
    local text = ""
    if total > 0 or repeatables == 0 then
        local color = complete and "|cff6bd35f" or "|cffaaaaaa"
        text = color .. string.format(short and "%d/%d" or "%d / %d", done, total) .. "|r"
    end
    if repeatables > 0 then
        local extra = short and ("+" .. repeatables) or ("+" .. repeatables .. " repeatable")
        text = (text ~= "" and (text .. "  ") or "") .. Hex(REPEATABLE_BLUE) .. extra .. "|r"
    end
    return text
end

-- Draws a header and returns the y below it.
local function RenderSection(canvas, key, title, done, total, complete, width, top, repeatables)
    local collapsed = IsSectionCollapsed(key, complete)
    table.insert(renderedKeys, key)
    local s = AcquireSection(canvas)
    s.key, s.collapsed = key, collapsed
    s:ClearAllPoints()
    s:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
    s:SetWidth(width)
    s.toggle:SetTexture(collapsed and PLUS or MINUS)
    s.title:SetText(title)
    s.count:SetText(ProgressText(done, total, repeatables or 0, complete))
    s.next:Hide()
    s.step:SetText("")
    s.stepButton.targetQuest = nil
    s.stepButton:EnableMouse(false)
    return s, collapsed, top + HEADER_H + 8
end

local function RenderStoryline(canvas, storyline, top, viewWidth)
    -- Children within the storyline, for tooltips.
    storyline.childrenOf = {}
    for child, list in pairs(storyline.parents) do
        for _, parent in ipairs(list) do
            storyline.childrenOf[parent] = storyline.childrenOf[parent] or {}
            table.insert(storyline.childrenOf[parent], child)
        end
    end

    local ids = {}
    for _, n in ipairs(storyline.nodes) do
        table.insert(ids, n.id)
    end
    local done, total, repeatables = ns.CountProgress(ids)

    local kind, nextID, detail = ns.GetNextStep(storyline)
    local width = math.max(viewWidth - PAD * 2, storyline.cols * (NODE_W + COL_GAP) - COL_GAP)
    local s, collapsed, graphTop = RenderSection(canvas, "s" .. storyline.first,
        ns.GetQuestNameOrID(storyline.first), done, total, kind == "complete", viewWidth - PAD * 2, top, repeatables)

    local target = (kind == "available" or kind == "active") and nextID or nil
    if kind == "blocked" and detail and ns.Quests[detail] then
        target = detail
    end
    s.stepButton:ClearAllPoints()
    if target and ns.Quests[target] and ns.Quests[target].m then
        s.next:ClearAllPoints()
        s.next:SetPoint("LEFT", s.count, "RIGHT", 14, 0)
        s.next:Show()
        s.next.targetQuest = target
        s.next:SetScript("OnClick", function()
            ns.ShowQuestStart(target)
        end)
        s.stepButton:SetPoint("LEFT", s.next, "RIGHT", 6, 0)
    else
        s.stepButton:SetPoint("LEFT", s.count, "RIGHT", 12, 0)
    end
    s.step:SetText(NextStepText(kind, nextID, detail))
    -- The step text jumps to the quest it names: the next quest, or for a blocked
    -- storyline the earlier quest it's waiting on (which may be in another zone).
    local stepTarget = (kind == "blocked") and detail or nextID
    s.stepButton.targetQuest = stepTarget
    s.stepButton:SetWidth(s.step:GetStringWidth() + 6)
    s.stepButton:SetShown(true)
    s.stepButton:EnableMouse(stepTarget ~= nil and ns.Quests[stepTarget] ~= nil)

    if collapsed then
        return viewWidth, HEADER_H
    end

    local cells = {}
    for _, n in ipairs(storyline.nodes) do
        local node = AcquireNode(canvas)
        node:ClearAllPoints()
        node:SetPoint("TOPLEFT", canvas, "TOPLEFT", NodeX(n.col), -NodeY(graphTop, n.row))
        node.px, node.py = NodeX(n.col), NodeY(graphTop, n.row)
        StyleNode(node, n.id, storyline)
        cells[n.id] = n
    end

    -- Square connectors: right out of the parent, down/up at the gap, into the child.
    for child, list in pairs(storyline.parents) do
        local c = cells[child]
        for _, parent in ipairs(list) do
            local p = cells[parent]
            if c and p then
                local pDone = ns.IsDone(parent)
                local r, g, b, a = 0.32, 0.32, 0.32, 1
                if pDone then
                    r, g, b = 0.40, 0.66, 0.28
                end
                local x1 = NodeX(p.col) + NODE_W
                local y1 = -(NodeY(graphTop, p.row) + NODE_H / 2)
                local x2 = NodeX(c.col)
                local y2 = -(NodeY(graphTop, c.row) + NODE_H / 2)
                local xm = x2 - COL_GAP / 2
                local points = { { x1, y1 }, { xm, y1 }, { xm, y2 }, { x2, y2 } }
                if y1 == y2 then
                    points = { { x1, y1 }, { x2, y2 } }
                end
                for i = 1, #points - 1 do
                    local line = AcquireLine(canvas)
                    line:SetDrawLayer("ARTWORK", pDone and 2 or 1)
                    line:SetStartPoint("TOPLEFT", canvas, points[i][1], points[i][2])
                    line:SetEndPoint("TOPLEFT", canvas, points[i + 1][1], points[i + 1][2])
                    line:SetColorTexture(r, g, b, a)
                end
            end
        end
    end

    local height = HEADER_H + 8 + storyline.rows * (NODE_H + ROW_GAP)
    return PAD * 2 + width, height
end

local function RenderOthers(canvas, others, top, viewWidth)
    local done, total, repeatables = ns.CountProgress(others)
    -- A section of only repeatables is never "finished", so it doesn't start collapsed.
    local complete = done == total and (total > 0 or repeatables == 0)
    local _, collapsed, gridTop = RenderSection(canvas, "o" .. selectedZone, "Other quests",
        done, total, complete, viewWidth - PAD * 2, top, repeatables)
    if collapsed then
        return HEADER_H
    end

    local perRow = math.max(1, math.floor((viewWidth - PAD * 2 + COL_GAP) / (NODE_W + COL_GAP)))
    for i, id in ipairs(others) do
        local col = (i - 1) % perRow
        local row = math.floor((i - 1) / perRow)
        local node = AcquireNode(canvas)
        node:ClearAllPoints()
        node:SetPoint("TOPLEFT", canvas, "TOPLEFT", NodeX(col), -NodeY(gridTop, row))
        node.px, node.py = NodeX(col), NodeY(gridTop, row)
        StyleNode(node, id, nil)
    end
    local rows = math.ceil(#others / perRow)
    return HEADER_H + 8 + rows * (NODE_H + ROW_GAP)
end

RenderZone = function()
    if not frame or not selectedZone then
        return
    end
    ResetPools()
    renderedKeys = {}
    local canvas = frame.canvas
    local viewWidth = frame.graphScroll:GetWidth()
    local storylines, others = ns.BuildStorylines(selectedZone)

    local top, maxWidth, hidden = PAD, viewWidth, 0
    local hideCompleted = ns.GetSetting("hideCompleted")
    for _, storyline in ipairs(storylines) do
        if hideCompleted and ns.GetNextStep(storyline) == "complete" then
            hidden = hidden + 1
        else
            local w, h = RenderStoryline(canvas, storyline, top, viewWidth)
            maxWidth = math.max(maxWidth, w)
            top = top + h + SECTION_GAP
        end
    end
    if hidden > 0 then
        local note = AcquireText(canvas, "GameFontDisableSmall")
        note:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
        note:SetText(string.format("%d finished %s hidden (see Settings)", hidden, hidden == 1 and "storyline" or "storylines"))
        top = top + 20 + SECTION_GAP
    end
    if #others > 0 and ns.GetSetting("showOthers") then
        top = top + RenderOthers(canvas, others, top, viewWidth) + SECTION_GAP
    end
    if #storylines == 0 and #others == 0 then
        local note = AcquireText(canvas, "GameFontNormal")
        note:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
        note:SetText("No quests for your character in this zone.")
        top = top + 30
    end
    canvas:SetSize(maxWidth, math.max(top, frame.graphScroll:GetHeight()))
    if frame.graphScroll.UpdateScrollChildRect then
        frame.graphScroll:UpdateScrollChildRect()
    end

    local done, total, repeatables = ns.GetZoneProgress(selectedZone)
    frame.zoneTitle:SetText(ns.GetMapName(selectedZone))
    frame.zoneIcon:SetTexture(ZoneIcon(selectedZone))
    local summary = string.format("%d / %d quests done", done, total)
    if repeatables > 0 then
        summary = summary .. "  -  " .. Hex(REPEATABLE_BLUE) .. repeatables .. " repeatable|r"
    end
    local low, high = ns.GetLevelRange(selectedZone)
    if low then
        summary = "Levels " .. LevelRangeText(low, high) .. "  -  " .. summary
    end
    frame.zoneSummary:SetText(summary .. string.format("  -  %d storylines", #storylines))
end

local function SetAllCollapsed(collapsed)
    local t = CollapsedTable("collapsed")
    for _, key in ipairs(renderedKeys) do
        t[key] = collapsed
    end
    RenderZone()
end

-- ============================================================================
-- Zone list
-- ============================================================================

-- Instance pages get their own headings, after the continents.
local INSTANCE_GROUPS = {
    dungeon = { name = "Dungeons", rank = 1 },
    raid = { name = "Raids", rank = 2 },
    battleground = { name = "Battlegrounds", rank = 3 },
}

local function SortedZones()
    local zones = ns.GetZones()
    for _, z in ipairs(zones) do
        z.name = ns.GetMapName(z.id)
        local group = z.instance and INSTANCE_GROUPS[z.instance]
        if group then
            z.continentName, z.groupRank = group.name, group.rank
        else
            z.continentName = (z.continent ~= 0 and z.continent ~= z.id) and ns.GetMapName(z.continent) or "Other"
            z.groupRank = 0
        end
    end
    table.sort(zones, function(a, b)
        if a.groupRank ~= b.groupRank then
            return a.groupRank < b.groupRank
        end
        if a.continentName ~= b.continentName then
            return a.continentName < b.continentName
        end
        return a.name < b.name
    end)
    return zones
end

local RenderZoneList

local function SelectZone(zoneID)
    selectedZone = zoneID
    ns.focusedQuest = nil
    ClearHistory() -- picking a zone yourself starts a fresh trail
    if LorePathDB then
        LorePathDB.lastZone = zoneID
    end
    for _, row in ipairs(zoneRows) do
        if row.selected then
            row.selected:SetShown(row.zoneID ~= nil and row.zoneID == zoneID)
        end
    end
    frame.graphScroll:SetVerticalScroll(0)
    frame.graphScroll:SetHorizontalScroll(0)
    RenderZone()
end

RenderZoneList = function()
    local list = frame.listContent
    for _, row in ipairs(zoneRows) do
        row:Hide()
    end
    local y, index = 6, 0
    local function NextRow(height)
        index = index + 1
        local row = zoneRows[index]
        if not row then
            row = CreateFrame("Button", nil, list)
            row.toggle = row:CreateTexture(nil, "ARTWORK")
            row.toggle:SetSize(12, 12)
            row.toggle:SetPoint("LEFT", 4, 0)
            row.icon = row:CreateTexture(nil, "ARTWORK")
            row.icon:SetSize(16, 16)
            row.icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
            -- A small tick on the icon of a zone you've finished, like the quest boxes.
            row.check = row:CreateTexture(nil, "OVERLAY")
            row.check:SetSize(12, 12)
            row.check:SetPoint("BOTTOMRIGHT", row.icon, "BOTTOMRIGHT", 4, -3)
            row.check:SetTexture("Interface\\RaidFrame\\ReadyCheck-Ready")
            row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            row.text:SetJustifyH("LEFT")
            row.text:SetWordWrap(false)
            row.count = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            row.count:SetPoint("RIGHT", -8, 0)
            -- Level range, in its own column before the count, so a long name
            -- is what gets shortened, not the range.
            row.range = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            row.range:SetPoint("RIGHT", row.count, "LEFT", -6, 0)
            row.range:SetTextColor(0.62, 0.62, 0.62)
            -- Second line, used by search results only.
            row.sub = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
            row.sub:SetPoint("BOTTOMLEFT", 10, 4)
            row.sub:SetPoint("RIGHT", row.count, "LEFT", -4, 0)
            row.sub:SetJustifyH("LEFT")
            row.sub:SetWordWrap(false)
            row.lineL = row:CreateTexture(nil, "ARTWORK")
            row.lineL:SetHeight(1)
            row.lineR = row:CreateTexture(nil, "ARTWORK")
            row.lineR:SetHeight(1)
            row.lineL:SetColorTexture(0.6, 0.6, 0.6, 0.35)
            row.lineR:SetColorTexture(0.6, 0.6, 0.6, 0.35)
            row.selected = row:CreateTexture(nil, "BACKGROUND")
            row.selected:SetAllPoints()
            SetFade(row.selected, 1, 0.82, 0, 0.28)
            local hl = row:CreateTexture(nil, "HIGHLIGHT")
            hl:SetAllPoints()
            hl:SetColorTexture(1, 1, 1, 0.07)
            zoneRows[index] = row
        end
        row:SetHeight(height)
        row:ClearAllPoints()
        row:SetPoint("TOPLEFT", list, "TOPLEFT", 0, -y)
        row:SetPoint("RIGHT", list, "RIGHT", 0, 0)
        row:Show()
        row.top = y
        y = y + height
        -- Rows are reused between the zone list and search results.
        row.zoneID, row.continent, row.resultQuest = nil, nil, nil
        row.selected:Hide()
        row.toggle:Hide()
        row.lineL:Hide()
        row.lineR:Hide()
        row.sub:Hide()
        row.icon:Hide()
        row.check:Hide()
        row.count:SetText("")
        row.range:SetText("")
        row:SetScript("OnEnter", nil)
        row:SetScript("OnLeave", nil)
        return row
    end

    -- Searching: quest results replace the zone list.
    if searchText ~= "" then
        local ids, total = ns.SearchQuests(searchText)
        local header = NextRow(22)
        header.text:SetFontObject("GameFontNormalSmall")
        header.text:ClearAllPoints()
        header.text:SetPoint("LEFT", 10, 0)
        header.text:SetPoint("RIGHT", -8, 0)
        header.text:SetTextColor(0.85, 0.85, 0.85)
        if total == 0 then
            header.text:SetText("No quests match")
        elseif total > #ids then
            header.text:SetText(string.format("First %d of %d quests", #ids, total))
        else
            header.text:SetText(total == 1 and "1 quest" or (total .. " quests"))
        end
        header:SetScript("OnClick", nil)
        for _, id in ipairs(ids) do
            local q = ns.Quests[id]
            local status = ns.GetStatus(id)
            local row = NextRow(32)
            row.resultQuest = id
            row.text:SetFontObject("GameFontHighlightSmall")
            row.text:ClearAllPoints()
            row.text:SetPoint("TOPLEFT", 10, -4)
            row.text:SetPoint("RIGHT", row.count, "LEFT", -4, 0)
            row.text:SetText(ns.GetQuestNameOrID(id))
            -- Coloured as in the graph: by status, else by difficulty.
            local tc = STATUS_STYLE[status].text or DifficultyColor(q.l or 1)
            if status == S.LEVEL and ns.GetLockReason(id) ~= "minrep" then
                tc = { 0.85, 0.85, 0.85 }
            end
            row.text:SetTextColor(tc[1], tc[2], tc[3])
            row.sub:SetText(ns.GetMapName(q.z) .. " - " .. STATUS_SHORT[status])
            row.sub:Show()
            row.count:SetText(Hex(DifficultyColor(q.l or 1)) .. (q.l or 1) .. "|r")
            row:SetScript("OnClick", function(self)
                if IsControlKeyDown() then
                    ns.ShowQuestStart(self.resultQuest)
                else
                    ns.FocusQuest(self.resultQuest)
                end
            end)
            row:SetScript("OnEnter", function(self)
                ShowQuestTooltip(self, self.resultQuest)
            end)
            row:SetScript("OnLeave", GameTooltip_Hide)
        end
        list:SetHeight(y + 4)
        return
    end

    -- Class and Professions first (issue #8), then zones grouped by continent,
    -- with totals for each heading.
    local groups, order = {}, {}
    for _, special in ipairs(ns.GetSpecialGroups()) do
        local g = { name = special.name, zones = {}, done = 0, total = 0, repeatables = 0,
                    icon = special.name == "Class" and ZoneIcon("class") or "Interface\\Icons\\INV_Pick_02" }
        for _, page in ipairs(special.pages) do
            local z = { id = page, name = ns.GetMapName(page) }
            local skill = tonumber(string.match(page, "^prof:(%d+)$"))
            z.greyed = skill ~= nil and not ns.HasProfession(skill) -- a profession you don't have
            z.done, z.total, z.repeatables = ns.GetZoneProgress(page)
            g.done, g.total = g.done + z.done, g.total + z.total
            g.repeatables = g.repeatables + z.repeatables
            table.insert(g.zones, z)
        end
        groups[g.name] = g
        table.insert(order, g)
    end
    for _, z in ipairs(SortedZones()) do
        local g = groups[z.continentName]
        if not g then
            g = { name = z.continentName, zones = {}, done = 0, total = 0, repeatables = 0, kind = z.instance,
                  continentID = (not z.instance and z.continent ~= 0 and z.continent ~= z.id) and z.continent or nil }
            groups[z.continentName] = g
            table.insert(order, g)
        end
        z.done, z.total, z.repeatables = ns.GetZoneProgress(z.id)
        g.done, g.total = g.done + z.done, g.total + z.total
        g.repeatables = g.repeatables + z.repeatables
        table.insert(g.zones, z)
    end

    local collapsedContinents = CollapsedTable("collapsedContinents")
    for _, g in ipairs(order) do
        local collapsed = collapsedContinents[g.name] == true
        local heading = NextRow(24)
        heading.zoneID = nil
        heading.selected:Hide()
        heading.toggle:Show()
        heading.toggle:SetTexture(collapsed and PLUS or MINUS)
        heading.text:SetFontObject("GameFontNormalSmall")
        heading.text:ClearAllPoints()
        heading.text:SetPoint("CENTER", 0, 0)
        heading.text:SetText(string.upper(g.name))
        heading.text:SetTextColor(0.85, 0.85, 0.85)
        heading.count:SetText("")
        heading.lineL:Show()
        heading.lineR:Show()
        heading.icon:Show()
        heading.icon:SetTexture(HeadingIcon(g))
        heading.icon:ClearAllPoints()
        heading.icon:SetPoint("RIGHT", heading.text, "LEFT", -5, 0)
        heading.check:Hide()
        heading.lineL:ClearAllPoints()
        heading.lineL:SetPoint("LEFT", heading.toggle, "RIGHT", 6, 0)
        heading.lineL:SetPoint("RIGHT", heading.icon, "LEFT", -6, 0)
        heading.lineR:ClearAllPoints()
        heading.lineR:SetPoint("LEFT", heading.text, "RIGHT", 6, 0)
        heading.lineR:SetPoint("RIGHT", heading, "RIGHT", -8, 0)
        heading.continent = g.name
        heading:SetScript("OnClick", function(self)
            collapsedContinents[self.continent] = not collapsedContinents[self.continent] or nil
            RenderZoneList()
        end)
        heading:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine(g.name, 1, 0.82, 0)
            GameTooltip:AddLine(string.format("%d / %d quests done", g.done, g.total), 1, 1, 1)
            if g.repeatables > 0 then
                GameTooltip:AddLine(g.repeatables .. " repeatable quests", REPEATABLE_BLUE[1], REPEATABLE_BLUE[2], REPEATABLE_BLUE[3])
            end
            GameTooltip:Show()
        end)
        heading:SetScript("OnLeave", GameTooltip_Hide)

        if not collapsed then
            for _, z in ipairs(g.zones) do
                local row = NextRow(20)
                row.zoneID = z.id
                row.continent = nil -- rows are reused; only headings carry a continent
                row.toggle:Hide()
                row.lineL:Hide()
                row.lineR:Hide()
                row.text:SetFontObject("GameFontHighlightSmall")
                row.icon:Show()
                row.icon:SetTexture(ZoneIcon(z.id))
                row.icon:ClearAllPoints()
                row.icon:SetPoint("LEFT", 12, 0)
                row.text:ClearAllPoints()
                row.text:SetPoint("LEFT", row.icon, "RIGHT", 5, 0)
                row.text:SetPoint("RIGHT", row.range, "LEFT", -4, 0)
                row.text:SetText(z.name)
                -- Zones, dungeons and raids show the game's suggested level range.
                local low, high = ns.GetLevelRange(z.id)
                row.range:SetText(low and LevelRangeText(low, high) or "")
                local complete = z.total > 0 and z.done == z.total
                row.check:SetShown(complete)
                row.icon:SetDesaturated(z.greyed or false)
                local color = z.greyed and { 0.45, 0.45, 0.45 } -- a profession you don't have
                    or ProgressColor(z.done, z.total)
                row.text:SetTextColor(color[1], color[2], color[3])
                row.count:SetText(ProgressText(z.done, z.total, z.repeatables, complete, true))
                row.selected:SetShown(z.id == selectedZone)
                row:SetScript("OnClick", function(self)
                    SelectZone(self.zoneID)
                end)
                -- The full name (it may be shortened in the row), range and progress.
                row:SetScript("OnEnter", function(self)
                    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                    GameTooltip:AddLine(z.name, 1, 0.82, 0)
                    if low then
                        GameTooltip:AddLine("Levels " .. LevelRangeText(low, high), 1, 1, 1)
                    end
                    GameTooltip:AddLine(string.format("%d / %d quests done", z.done, z.total), 1, 1, 1)
                    if z.repeatables > 0 then
                        GameTooltip:AddLine(z.repeatables .. " repeatable quests", REPEATABLE_BLUE[1], REPEATABLE_BLUE[2], REPEATABLE_BLUE[3])
                    end
                    GameTooltip:Show()
                end)
                row:SetScript("OnLeave", GameTooltip_Hide)
            end
        end
        y = y + 4
    end
    list:SetHeight(y + 4)
end

-- ============================================================================
-- Jumping to a quest
-- ============================================================================

local function FocusedNode()
    for i = 1, used.nodes do
        local node = pools.nodes[i]
        if node.questID == ns.focusedQuest then
            return node
        end
    end
end

-- Scrolls the zone list so the selected zone's row is in view.
local function ScrollListToSelected()
    if not frame or not frame.listScroll then
        return
    end
    for _, row in ipairs(zoneRows) do
        if row:IsShown() and row.zoneID == selectedZone and row.top then
            local scroll = frame.listScroll
            if scroll.UpdateScrollChildRect then
                scroll:UpdateScrollChildRect()
            end
            local view = scroll:GetHeight()
            local current = scroll:GetVerticalScroll()
            if row.top < current or row.top + row:GetHeight() > current + view then
                scroll:SetVerticalScroll(math.max(0, math.min(row.top - view / 3, scroll:GetVerticalScrollRange())))
            end
            return
        end
    end
end

-- Scrolls the graph so the focused quest sits near the top left.
local function ScrollToFocus()
    local node = frame and FocusedNode()
    if not node or not node.px then
        return
    end
    local scroll = frame.graphScroll
    if scroll.UpdateScrollChildRect then
        scroll:UpdateScrollChildRect()
    end
    scroll:SetVerticalScroll(math.max(0, math.min(node.py - 60, scroll:GetVerticalScrollRange())))
    scroll:SetHorizontalScroll(math.max(0, math.min(node.px - 40, scroll:GetHorizontalScrollRange())))
end

-- Shows a quest in the window: switches to its zone, opens the storyline (or
-- "Other quests") it belongs to, scrolls to it and highlights it for a moment.
function ns.FocusQuest(id)
    local q = id and ns.Quests[id]
    if not q or not frame then
        return
    end
    local zone = q.z
    -- On the Class or a profession page, stay there if the quest is on it.
    if ns.IsSpecialPage(selectedZone) then
        for _, other in ipairs(ns.GetZoneQuests(selectedZone)) do
            if other == id then
                zone = selectedZone
                break
            end
        end
    end
    local storylines, others = ns.BuildStorylines(zone)
    local key
    for _, storyline in ipairs(storylines) do
        for _, n in ipairs(storyline.nodes) do
            if n.id == id then
                key = "s" .. storyline.first
            end
        end
    end
    if not key then
        for _, other in ipairs(others) do
            if other == id then
                key = "o" .. zone
            end
        end
    end
    if not key then
        if q.rp and not ns.GetSetting("showRepeatable") and ns.IsEligible(id) then
            ns.Print(ns.GetQuestNameOrID(id) .. " is a repeatable quest; tick \"Repeatable\" to show it.")
        else
            ns.Print(ns.GetQuestNameOrID(id) .. " isn't shown for this character.")
        end
        return
    end
    if key:sub(1, 1) == "o" and not ns.GetSetting("showOthers") then
        ns.Print(ns.GetQuestNameOrID(id) .. " is a standalone quest; turn on \"Show standalone quests\" in Settings to see it.")
    end
    CollapsedTable("collapsed")[key] = false
    for _, z in ipairs(SortedZones()) do
        if z.id == zone then
            CollapsedTable("collapsedContinents")[z.continentName] = nil
        end
    end
    if ns.IsSpecialPage(zone) then
        CollapsedTable("collapsedContinents")[zone == "class" and "Class" or "Professions"] = nil
    end

    -- Remember where you were, for the Back button.
    if selectedZone then
        table.insert(history, {
            zone = selectedZone,
            v = frame.graphScroll:GetVerticalScroll(),
            h = frame.graphScroll:GetHorizontalScroll(),
        })
        if #history > HISTORY_MAX then
            table.remove(history, 1)
        end
    end
    UpdateBackButton()

    selectedZone = zone
    if LorePathDB then
        LorePathDB.lastZone = zone
    end
    ns.focusedQuest = id
    RenderZoneList()
    RenderZone()
    ScrollListToSelected()
    C_Timer.After(0, ScrollListToSelected)
    ScrollToFocus()
    C_Timer.After(0, ScrollToFocus) -- the scroll range updates a frame later in game
    C_Timer.After(2.5, function()
        if ns.focusedQuest == id then
            ns.focusedQuest = nil
            for i = 1, used.nodes do
                if pools.nodes[i].questID == id then
                    pools.nodes[i].flash:Hide()
                end
            end
        end
    end)
end

-- Returns to the zone and scroll position you were at before the last jump.
function ns.GoBack()
    local entry = table.remove(history)
    UpdateBackButton()
    if not entry or not frame then
        return
    end
    ns.focusedQuest = nil
    selectedZone = entry.zone
    if LorePathDB then
        LorePathDB.lastZone = entry.zone
    end
    RenderZoneList()
    RenderZone()
    ScrollListToSelected()
    local function Restore()
        local scroll = frame.graphScroll
        if scroll.UpdateScrollChildRect then
            scroll:UpdateScrollChildRect()
        end
        scroll:SetVerticalScroll(math.max(0, math.min(entry.v, scroll:GetVerticalScrollRange())))
        scroll:SetHorizontalScroll(math.max(0, math.min(entry.h, scroll:GetHorizontalScrollRange())))
    end
    Restore()
    C_Timer.After(0, Restore) -- the scroll range updates a frame later in game
end

-- ============================================================================
-- Frame
-- ============================================================================

local function CreateInset(parent)
    local ok, inset = pcall(CreateFrame, "Frame", nil, parent, "InsetFrameTemplate")
    if not ok then
        inset = CreateFrame("Frame", nil, parent)
        local bg = inset:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(0.04, 0.04, 0.04, 0.9)
        AddBorder(inset, "BORDER")
        inset:SetBorderColor(0.3, 0.3, 0.3, 1)
    end
    return inset
end

-- Shows or hides the zone list, giving the graph the whole width.
local function ApplyListVisibility(f)
    local hidden = LorePathDB and LorePathDB.listHidden
    f.listInset:SetShown(not hidden)
    f.graphInset:ClearAllPoints()
    if hidden then
        f.graphInset:SetPoint("TOPLEFT", f, "TOPLEFT", 10, -62)
    else
        f.graphInset:SetPoint("TOPLEFT", f.listInset, "TOPRIGHT", 6, 0)
    end
    f.graphInset:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -8, 32)
    local prefix = hidden and "Interface\\Buttons\\UI-SpellbookIcon-NextPage-" or "Interface\\Buttons\\UI-SpellbookIcon-PrevPage-"
    f.listToggle:SetNormalTexture(prefix .. "Up")
    f.listToggle:SetPushedTexture(prefix .. "Down")
end

-- For Settings' "Reset to defaults": show the zone list again if it was hidden.
function ns.ApplyListVisibility()
    if frame then
        ApplyListVisibility(frame)
    end
end

local function CreateMainFrame()
    local f
    for _, template in ipairs({ "PortraitFrameTemplate", "BasicFrameTemplateWithInset" }) do
        local ok, made = pcall(CreateFrame, "Frame", "LorePathFrame", UIParent, template)
        if ok then
            f = made
            break
        end
    end
    if not f then
        f = CreateFrame("Frame", "LorePathFrame", UIParent, BackdropTemplateMixin and "BackdropTemplate" or nil)
        if f.SetBackdrop then
            f:SetBackdrop({
                bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
                edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
                tile = true, tileSize = 32, edgeSize = 32,
                insets = { left = 11, right = 12, top = 12, bottom = 11 },
            })
        end
        local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
        close:SetPoint("TOPRIGHT", -4, -4)
    end
    f:SetSize(FRAME_W, FRAME_H)
    f:SetPoint("CENTER")
    f:SetFrameStrata("HIGH")
    f:SetToplevel(true)
    f:SetClampedToScreen(true)
    f:EnableMouse(true)
    f:SetMovable(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", f.StartMoving)
    f:SetScript("OnDragStop", f.StopMovingOrSizing)
    f:Hide()
    f:SetScale(ns.GetSetting("scale"))
    table.insert(UISpecialFrames, "LorePathFrame")
    ns.mainFrame = f

    if f.SetTitle then
        f:SetTitle("LorePath")
    else
        local title = type(f.TitleText) == "table" and f.TitleText or f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        if title ~= f.TitleText then
            title:SetPoint("TOP", 0, -6)
        end
        title:SetText("LorePath")
    end
    if f.SetPortraitToAsset then
        pcall(f.SetPortraitToAsset, f, "Interface\\Icons\\INV_Misc_Book_09")
    end

    -- Zone list (left)
    local listInset = CreateInset(f)
    listInset:SetPoint("TOPLEFT", f, "TOPLEFT", 10, -62)
    listInset:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 10, 32)
    listInset:SetWidth(LIST_W)
    f.listInset = listInset
    -- Quest search, at the top of the zone list.
    local ok, search = pcall(CreateFrame, "EditBox", "LorePathSearchBox", listInset, "SearchBoxTemplate")
    if not ok then
        search = CreateFrame("EditBox", "LorePathSearchBox", listInset, "InputBoxTemplate")
    end
    search:SetHeight(20)
    search:SetPoint("TOPLEFT", listInset, "TOPLEFT", 12, -6)
    search:SetPoint("TOPRIGHT", listInset, "TOPRIGHT", -8, -6)
    search:SetAutoFocus(false)
    search:SetMaxLetters(60)
    if type(search.Instructions) == "table" then
        search.Instructions:SetText("Search quests")
    end
    search:SetScript("OnTextChanged", function(self, userInput)
        if type(SearchBoxTemplate_OnTextChanged) == "function" and type(self.Instructions) == "table" then
            pcall(SearchBoxTemplate_OnTextChanged, self) -- placeholder text and clear button
        end
        local text = self:GetText() or ""
        if text ~= searchText then
            searchText = text
            f.listScroll:SetVerticalScroll(0)
            RenderZoneList()
            if text == "" then
                ScrollListToSelected()
            end
        end
    end)
    search:SetScript("OnEscapePressed", function(self)
        self:SetText("")
        self:GetScript("OnTextChanged")(self, true) -- in case SetText didn't fire it
        self:ClearFocus()
    end)
    search:SetScript("OnEnterPressed", function(self)
        self:ClearFocus()
    end)
    search:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Search quests", 1, 0.82, 0)
        GameTooltip:AddLine("Type part of a quest's name, or its ID. Click a result to show it; Escape clears the search.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    search:SetScript("OnLeave", GameTooltip_Hide)
    f.searchBox = search

    local listScroll = CreateFrame("ScrollFrame", nil, listInset)
    listScroll:SetPoint("TOPLEFT", 4, -30)
    listScroll:SetPoint("BOTTOMRIGHT", -4, 4)
    local listContent = CreateFrame("Frame", nil, listScroll)
    listContent:SetSize(LIST_W - 8, 10)
    listScroll:SetScrollChild(listContent)
    MakeScrollable(listScroll, false)
    f.listScroll = listScroll
    f.listContent = listContent

    -- Storyline graph (right), on a stone background
    local graphInset = CreateInset(f)
    f.graphInset = graphInset
    local rock = graphInset:CreateTexture(nil, "BACKGROUND", nil, 1)
    rock:SetPoint("TOPLEFT", 3, -3)
    rock:SetPoint("BOTTOMRIGHT", -3, 3)
    rock:SetTexture(ROCK, "REPEAT", "REPEAT")
    rock:SetHorizTile(true)
    rock:SetVertTile(true)
    rock:SetVertexColor(0.55, 0.55, 0.55)
    local graphScroll = CreateFrame("ScrollFrame", nil, graphInset)
    graphScroll:SetPoint("TOPLEFT", 4, -4)
    graphScroll:SetPoint("BOTTOMRIGHT", -4, 4)
    local canvas = CreateFrame("Frame", nil, graphScroll)
    canvas:SetSize(10, 10)
    graphScroll:SetScrollChild(canvas)
    MakeScrollable(graphScroll, true)
    f.graphScroll = graphScroll
    f.canvas = canvas

    -- Header row: list toggle, zone name and progress, expand/collapse buttons
    local listToggle = CreateFrame("Button", nil, f)
    listToggle:SetSize(26, 26)
    listToggle:SetPoint("TOPLEFT", f, "TOPLEFT", 62, -30)
    listToggle:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
    listToggle:SetScript("OnClick", function()
        LorePathDB.listHidden = not LorePathDB.listHidden or nil
        ApplyListVisibility(f)
        RenderZone()
    end)
    listToggle:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine(LorePathDB.listHidden and "Show the zone list" or "Hide the zone list", 1, 1, 1)
        GameTooltip:Show()
    end)
    listToggle:SetScript("OnLeave", GameTooltip_Hide)
    f.listToggle = listToggle

    local zoneIcon = f:CreateTexture(nil, "ARTWORK")
    zoneIcon:SetSize(22, 22)
    zoneIcon:SetPoint("LEFT", listToggle, "RIGHT", 6, 0)
    zoneIcon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
    f.zoneIcon = zoneIcon
    local zoneTitle = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    zoneTitle:SetPoint("LEFT", zoneIcon, "RIGHT", 6, 0)
    zoneTitle:SetJustifyH("LEFT")
    f.zoneTitle = zoneTitle
    local zoneSummary = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    zoneSummary:SetPoint("LEFT", zoneTitle, "RIGHT", 12, -1)
    zoneSummary:SetTextColor(0.7, 0.7, 0.7)
    f.zoneSummary = zoneSummary

    local expandAll = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    expandAll:SetSize(90, 20)
    expandAll:SetPoint("TOPRIGHT", f, "TOPRIGHT", -12, -33)
    expandAll:SetText("Expand all")
    expandAll:SetScript("OnClick", function() SetAllCollapsed(false) end)
    local collapseAll = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    collapseAll:SetSize(90, 20)
    collapseAll:SetPoint("RIGHT", expandAll, "LEFT", -4, 0)
    collapseAll:SetText("Collapse all")
    collapseAll:SetScript("OnClick", function() SetAllCollapsed(true) end)

    -- Quick show/hide for repeatable quests (the same setting as on the settings page).
    local repeatToggle = CreateFrame("CheckButton", nil, f, "UICheckButtonTemplate")
    repeatToggle:SetSize(22, 22)
    local repeatLabel = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    repeatLabel:SetPoint("RIGHT", collapseAll, "LEFT", -10, 0)
    repeatLabel:SetText("Repeatable")
    repeatLabel:SetTextColor(REPEATABLE_BLUE[1], REPEATABLE_BLUE[2], REPEATABLE_BLUE[3])
    repeatToggle:SetPoint("RIGHT", repeatLabel, "LEFT", -1, 0)
    repeatToggle:SetChecked(ns.GetSetting("showRepeatable") and true or false)
    repeatToggle:SetScript("OnClick", function(self)
        ns.SetSetting("showRepeatable", self:GetChecked() and true or false)
    end)
    repeatToggle:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
        GameTooltip:AddLine("Show repeatable quests", 1, 0.82, 0)
        GameTooltip:AddLine("Daily and repeatable quests, in blue. They never count towards progress.", 1, 1, 1, true)
        GameTooltip:Show()
    end)
    repeatToggle:SetScript("OnLeave", GameTooltip_Hide)
    f.repeatToggle = repeatToggle

    -- Back: returns to where you were before jumping to a quest.
    local back = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    back:SetSize(70, 20)
    back:SetPoint("RIGHT", repeatToggle, "LEFT", -8, 0)
    back:SetText("Back")
    back:SetScript("OnClick", function() ns.GoBack() end)
    back:SetScript("OnEnter", function(self)
        local entry = history[#history]
        if entry then
            GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
            GameTooltip:AddLine("Back to " .. ns.GetMapName(entry.zone), 1, 1, 1)
            GameTooltip:Show()
        end
    end)
    back:SetScript("OnLeave", GameTooltip_Hide)
    back:Hide()
    f.backButton = back

    -- Footer: status legend, help, settings
    local x = 16
    for _, status in ipairs(LEGEND_ORDER) do
        local swatch = CreateFrame("Frame", nil, f)
        swatch:SetSize(14, 14)
        swatch:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", x, 10)
        local style = STATUS_STYLE[status]
        local fill = swatch:CreateTexture(nil, "BACKGROUND")
        fill:SetAllPoints()
        fill:SetColorTexture(style.bg[1], style.bg[2], style.bg[3], 1)
        AddBorder(swatch, "BORDER")
        swatch:SetBorderColor(style.border[1], style.border[2], style.border[3], 1)
        -- The same corner marker the quest boxes use, so similar tints stay tellable apart.
        local markPath = STATUS_MARK[status] or STATUS_MARK[S.AVAILABLE]
        local mark = swatch:CreateTexture(nil, "OVERLAY")
        mark:SetSize(16, 16)
        mark:SetPoint("CENTER")
        mark:SetTexture(markPath)
        if status == S.LEVEL then
            mark:SetDesaturated(true)
        elseif status == S.REPEATABLE then
            mark:SetDesaturated(true)
            mark:SetVertexColor(REPEATABLE_BLUE[1], REPEATABLE_BLUE[2], REPEATABLE_BLUE[3])
        end
        local label = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        label:SetPoint("LEFT", swatch, "RIGHT", 5, 0)
        label:SetText(STATUS_SHORT[status])
        x = x + 24 + label:GetStringWidth() + 12
    end
    local settingsButton = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    settingsButton:SetSize(80, 20)
    settingsButton:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -10, 7)
    settingsButton:SetText("Settings")
    settingsButton:SetScript("OnClick", function()
        ns.OpenSettings()
    end)

    -- The finer points live in a "?" tooltip, so the footer stays readable.
    local help = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    help:SetSize(24, 20)
    help:SetPoint("RIGHT", settingsButton, "LEFT", -6, 0)
    help:SetText("?")
    help:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOPLEFT")
        GameTooltip:AddLine("Using LorePath", 1, 0.82, 0)
        GameTooltip:AddLine("Click a quest for its details; click it again to close them.", 1, 1, 1, true)
        GameTooltip:AddLine("Ctrl+click a quest to set a waypoint where it starts.", 1, 1, 1, true)
        GameTooltip:AddLine("Search quests by name or ID in the box above the zone list.", 1, 1, 1, true)
        GameTooltip:AddLine("Shift+click a quest you're on to open it in your quest log.", 1, 1, 1, true)
        GameTooltip:AddLine("Click \"Next\" or \"First finish\" in a storyline header to jump to that quest; Back returns you.", 1, 1, 1, true)
        GameTooltip:AddLine("Drag anywhere on the graph to pan, even from a quest; Shift+mouse wheel scrolls sideways.", 1, 1, 1, true)
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine("Level colours, as in your quest log:", 1, 0.82, 0)
        GameTooltip:AddLine(Hex(DIFFICULTY.impossible) .. "too high|r  " .. Hex(DIFFICULTY.difficult) .. "your level|r  "
            .. Hex(DIFFICULTY.standard) .. "easy|r  " .. Hex(DIFFICULTY.trivial) .. "low level|r", 1, 1, 1)
        GameTooltip:Show()
    end)
    help:SetScript("OnLeave", GameTooltip_Hide)

    ApplyListVisibility(f)
    f:SetScript("OnShow", function()
        ns.Refresh()
    end)
    return f
end

-- The zone you're standing in (or the instance you're inside), or the closest
-- parent zone that has quests.
local function CurrentZone()
    local mapID = C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
    local known = {}
    for _, z in ipairs(ns.GetZones()) do
        known[z.id] = true
    end
    -- Inside a dungeon or raid, its own page (when it has quests for you).
    local instancePage = ns.CurrentInstancePage(mapID)
    if instancePage and known[instancePage] then
        return instancePage
    end
    while mapID and mapID > 0 do
        if known[mapID] then
            return mapID
        end
        local info = C_Map.GetMapInfo(mapID)
        mapID = info and info.parentMapID
    end
    return nil
end

-- ============================================================================
-- Public
-- ============================================================================

function ns.Refresh()
    if not frame or not frame:IsShown() then
        return
    end
    ns.RefreshPlayer()
    ns.RefreshCompleted()
    frame.repeatToggle:SetChecked(ns.GetSetting("showRepeatable") and true or false)
    if not selectedZone then
        selectedZone = CurrentZone() or (LorePathDB and LorePathDB.lastZone)
        if not selectedZone then
            local zones = SortedZones()
            selectedZone = zones[1] and zones[1].id
        end
    end
    RenderZoneList()
    RenderZone()
    if ns.RefreshDetail then
        ns.RefreshDetail()
    end
end

local refreshPending = false
function ns.QueueRefresh(delay)
    if refreshPending or not frame or not frame:IsShown() then
        return
    end
    refreshPending = true
    C_Timer.After(delay or 0.3, function()
        refreshPending = false
        if ns.Safely then
            ns.Safely("refresh", ns.Refresh)
        else
            ns.Refresh()
        end
    end)
end

function ns.Toggle(openCurrentZone)
    frame = frame or CreateMainFrame()
    if frame:IsShown() and not openCurrentZone then
        frame:Hide()
        return
    end
    ns.RefreshPlayer() -- the current-zone lookup needs to know which quests are yours
    if openCurrentZone or (not frame:IsShown() and ns.GetSetting("openOnCurrentZone")) then
        selectedZone = CurrentZone() or selectedZone
        ClearHistory()
    end
    if frame:IsShown() then
        ns.Refresh()
    else
        frame:Show()
    end
    ScrollListToSelected()
end

-- Global so Bindings.xml can call it.
function LorePath_Toggle()
    ns.Toggle(false)
end
