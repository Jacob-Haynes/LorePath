-- LorePath window: zone list on the left, the selected zone's storylines drawn as
-- quest graphs on the right. Click a quest to set a waypoint to where it starts.

local addonName, ns = ...

BINDING_HEADER_LOREPATH = "LorePath"
BINDING_NAME_LOREPATH_TOGGLE = "Open / close LorePath"

local S = ns.STATUS

local STATUS_COLORS = {
    [S.DONE]      = { 0.18, 0.55, 0.22 },
    [S.ACTIVE]    = { 0.85, 0.65, 0.10 },
    [S.AVAILABLE] = { 0.20, 0.45, 0.85 },
    [S.LEVEL]     = { 0.70, 0.38, 0.12 },
    [S.BLOCKED]   = { 0.30, 0.30, 0.33 },
    [S.MISSED]    = { 0.18, 0.18, 0.18 },
}

local STATUS_TEXT = {
    [S.DONE]      = "Completed",
    [S.ACTIVE]    = "In your quest log",
    [S.AVAILABLE] = "Available now",
    [S.LEVEL]     = "Needs a higher level",
    [S.BLOCKED]   = "Needs an earlier quest",
    [S.MISSED]    = "Skipped (you went past this breadcrumb)",
}

local LEGEND_ORDER = { S.DONE, S.ACTIVE, S.AVAILABLE, S.LEVEL, S.BLOCKED }

local FRAME_W, FRAME_H = 1100, 640
local LIST_W = 230
local NODE_W, NODE_H = 150, 24
local COL_GAP, ROW_GAP = 26, 8
local PAD = 12
local SECTION_GAP = 22

local frame
local selectedZone
local zoneRows = {}
local pools = { nodes = {}, lines = {}, headers = {}, buttons = {} }
local used = { nodes = 0, lines = 0, headers = 0, buttons = 0 }

-- ============================================================================
-- Small helpers
-- ============================================================================

local function Hex(color)
    return string.format("%02x%02x%02x", color[1] * 255, color[2] * 255, color[3] * 255)
end

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
        if button ~= "LeftButton" then
            return
        end
        local cx, cy = GetCursorPosition()
        self.pan = { cx = cx, cy = cy, x = self:GetHorizontalScroll(), y = self:GetVerticalScroll() }
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
        local x = pan.x - (cx - pan.cx) / scale
        local y = pan.y + (cy - pan.cy) / scale
        self:SetHorizontalScroll(math.max(0, math.min(x, self:GetHorizontalScrollRange())))
        self:SetVerticalScroll(math.max(0, math.min(y, self:GetVerticalScrollRange())))
    end)
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

local function ShowNodeTooltip(node)
    local id, storyline = node.questID, node.storyline
    local q = ns.Quests[id]
    local status = ns.GetStatus(id)
    GameTooltip:SetOwner(node, "ANCHOR_RIGHT")
    GameTooltip:AddLine(ns.GetQuestNameOrID(id), 1, 0.82, 0)
    GameTooltip:AddLine("Level " .. (q.l or 1), 1, 1, 1)
    local c = STATUS_COLORS[status]
    GameTooltip:AddLine(STATUS_TEXT[status], c[1] + 0.25, c[2] + 0.25, c[3] + 0.25)
    if status == S.BLOCKED then
        local missing = ns.MissingPrereq(id)
        if missing then
            GameTooltip:AddLine("Needs: " .. ns.GetQuestNameOrID(missing), 0.9, 0.9, 0.9, true)
        end
    elseif status == S.LEVEL and q.l then
        GameTooltip:AddLine("Needs level " .. q.l, 0.9, 0.9, 0.9)
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
    if q.m then
        GameTooltip:AddLine(string.format("Starts in %s (%.1f, %.1f)", ns.GetMapName(q.m), q.x, q.y), 0.75, 0.75, 0.75)
    else
        GameTooltip:AddLine("Start location unknown", 0.6, 0.6, 0.6)
    end
    if q.rw then
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine("Rewards:", 1, 0.82, 0)
        for _, itemID in ipairs(q.rw) do
            GameTooltip:AddLine("  " .. ItemText(itemID), 1, 1, 1)
        end
    end
    if q.m then
        GameTooltip:AddLine(" ")
        GameTooltip:AddLine("Click to set a waypoint to where it starts.", 0.5, 0.8, 1)
    end
    GameTooltip:Show()
end

local function AcquireNode(parent)
    used.nodes = used.nodes + 1
    local node = pools.nodes[used.nodes]
    if not node then
        node = CreateFrame("Button", nil, parent)
        node:SetSize(NODE_W, NODE_H)
        local border = node:CreateTexture(nil, "BACKGROUND")
        border:SetAllPoints()
        border:SetColorTexture(0, 0, 0, 0.9)
        node.bg = node:CreateTexture(nil, "BORDER")
        node.bg:SetPoint("TOPLEFT", 1, -1)
        node.bg:SetPoint("BOTTOMRIGHT", -1, 1)
        local hl = node:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        hl:SetColorTexture(1, 1, 1, 0.15)
        node.level = node:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        node.level:SetPoint("LEFT", 5, 0)
        node.level:SetWidth(20)
        node.level:SetJustifyH("LEFT")
        node.text = node:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        node.text:SetPoint("LEFT", node.level, "RIGHT", 2, 0)
        node.text:SetPoint("RIGHT", -4, 0)
        node.text:SetJustifyH("LEFT")
        node.text:SetWordWrap(false)
        node:SetScript("OnEnter", ShowNodeTooltip)
        node:SetScript("OnLeave", GameTooltip_Hide)
        node:SetScript("OnClick", function(self)
            ns.ShowQuestStart(self.questID)
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
        line:SetThickness(2)
        pools.lines[used.lines] = line
    end
    line:Show()
    return line
end

local function AcquireHeader(parent)
    used.headers = used.headers + 1
    local header = pools.headers[used.headers]
    if not header then
        header = parent:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        header:SetJustifyH("LEFT")
        pools.headers[used.headers] = header
    end
    header:Show()
    return header
end

local function AcquireButton(parent)
    used.buttons = used.buttons + 1
    local button = pools.buttons[used.buttons]
    if not button then
        button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
        button:SetSize(130, 20)
        button:SetText("Show next quest")
        pools.buttons[used.buttons] = button
    end
    button:Show()
    return button
end

local function StyleNode(node, id, storyline)
    local status = ns.GetStatus(id)
    local c = STATUS_COLORS[status]
    node.questID = id
    node.storyline = storyline
    node.bg:SetColorTexture(c[1], c[2], c[3], 0.9)
    if ns.GetSetting("showLevels") then
        node.level:SetText(ns.Quests[id].l or 1)
        node.level:SetWidth(20)
    else
        node.level:SetText("")
        node.level:SetWidth(1)
    end
    node.text:SetText(ns.GetQuestNameOrID(id))
    if status == S.MISSED or status == S.BLOCKED then
        node.text:SetTextColor(0.7, 0.7, 0.7)
    else
        node.text:SetTextColor(1, 1, 1)
    end
end

-- ============================================================================
-- Storyline rendering
-- ============================================================================

local function NextStepText(kind, id, detail)
    if kind == "available" then
        return "|cff8fd3ffNext: " .. ns.GetQuestNameOrID(id) .. "|r"
    elseif kind == "active" then
        return "|cffffd100In progress: " .. ns.GetQuestNameOrID(id) .. "|r"
    elseif kind == "level" then
        return "|cffff9a40Next part at level " .. (detail or "?") .. "|r"
    elseif kind == "blocked" then
        if detail then
            return "|cffaaaaaaFirst finish: " .. ns.GetQuestNameOrID(detail) .. "|r"
        end
        return "|cffaaaaaaWaiting on an earlier quest|r"
    end
    return "|cff4fd35fStoryline complete|r"
end

local function RenderStoryline(canvas, storyline, top)
    -- Children within the storyline, for tooltips.
    storyline.childrenOf = {}
    for child, list in pairs(storyline.parents) do
        for _, parent in ipairs(list) do
            storyline.childrenOf[parent] = storyline.childrenOf[parent] or {}
            table.insert(storyline.childrenOf[parent], child)
        end
    end

    local done, total = 0, 0
    for _, n in ipairs(storyline.nodes) do
        local status = ns.GetStatus(n.id)
        if status ~= S.MISSED then
            total = total + 1
            if status == S.DONE then
                done = done + 1
            end
        end
    end

    local header = AcquireHeader(canvas)
    header:SetFontObject("GameFontNormal")
    header:ClearAllPoints()
    header:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
    header:SetText(string.format("%s  |cffaaaaaa%d / %d|r", ns.GetQuestNameOrID(storyline.first), done, total))

    local kind, nextID, detail = ns.GetNextStep(storyline)
    local button = AcquireButton(canvas)
    button:ClearAllPoints()
    button:SetPoint("LEFT", header, "RIGHT", 12, 0)
    local stepText = AcquireHeader(canvas)
    stepText:SetFontObject("GameFontHighlightSmall")
    stepText:ClearAllPoints()
    stepText:SetPoint("LEFT", button, "RIGHT", 8, 0)
    stepText:SetText(NextStepText(kind, nextID, detail))
    local target = (kind == "available" or kind == "active") and nextID or nil
    if kind == "blocked" and detail and ns.Quests[detail] then
        target = detail
    end
    if target and ns.Quests[target] and ns.Quests[target].m then
        button:Enable()
        button:SetScript("OnClick", function()
            ns.ShowQuestStart(target)
        end)
    else
        button:Disable()
        button:SetScript("OnClick", nil)
    end

    local graphTop = top + 28
    local nodeByID = {}
    for _, n in ipairs(storyline.nodes) do
        local node = AcquireNode(canvas)
        node:ClearAllPoints()
        node:SetPoint("TOPLEFT", canvas, "TOPLEFT",
            PAD + n.col * (NODE_W + COL_GAP),
            -(graphTop + n.row * (NODE_H + ROW_GAP)))
        StyleNode(node, n.id, storyline)
        nodeByID[n.id] = node
    end
    for child, list in pairs(storyline.parents) do
        local childNode = nodeByID[child]
        for _, parent in ipairs(list) do
            local parentNode = nodeByID[parent]
            if childNode and parentNode then
                local line = AcquireLine(canvas)
                line:SetStartPoint("RIGHT", parentNode, 0, 0)
                line:SetEndPoint("LEFT", childNode, 0, 0)
                if ns.IsDone(parent) then
                    line:SetColorTexture(0.35, 0.75, 0.40, 0.9)
                else
                    line:SetColorTexture(0.55, 0.55, 0.55, 0.7)
                end
            end
        end
    end

    local width = PAD * 2 + storyline.cols * (NODE_W + COL_GAP)
    local height = 28 + storyline.rows * (NODE_H + ROW_GAP)
    return width, height
end

local function RenderOthers(canvas, others, top, viewWidth)
    local header = AcquireHeader(canvas)
    header:SetFontObject("GameFontNormal")
    header:ClearAllPoints()
    header:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
    local done = 0
    for _, id in ipairs(others) do
        if ns.GetStatus(id) == S.DONE then
            done = done + 1
        end
    end
    header:SetText(string.format("Other quests  |cffaaaaaa%d / %d|r", done, #others))

    local perRow = math.max(1, math.floor((viewWidth - PAD * 2 + COL_GAP) / (NODE_W + COL_GAP)))
    for i, id in ipairs(others) do
        local col = (i - 1) % perRow
        local row = math.floor((i - 1) / perRow)
        local node = AcquireNode(canvas)
        node:ClearAllPoints()
        node:SetPoint("TOPLEFT", canvas, "TOPLEFT",
            PAD + col * (NODE_W + COL_GAP),
            -(top + 28 + row * (NODE_H + ROW_GAP)))
        StyleNode(node, id, nil)
    end
    local rows = math.ceil(#others / perRow)
    return 28 + rows * (NODE_H + ROW_GAP)
end

local function RenderZone()
    if not frame or not selectedZone then
        return
    end
    ResetPools()
    local canvas = frame.canvas
    local viewWidth = frame.graphScroll:GetWidth()
    local storylines, others = ns.BuildStorylines(selectedZone)

    local top, maxWidth, hidden = PAD, viewWidth, 0
    local hideCompleted = ns.GetSetting("hideCompleted")
    for _, storyline in ipairs(storylines) do
        if hideCompleted and ns.GetNextStep(storyline) == "complete" then
            hidden = hidden + 1
        else
            local w, h = RenderStoryline(canvas, storyline, top)
            maxWidth = math.max(maxWidth, w)
            top = top + h + SECTION_GAP
        end
    end
    if hidden > 0 then
        local note = AcquireHeader(canvas)
        note:SetFontObject("GameFontDisableSmall")
        note:ClearAllPoints()
        note:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
        note:SetText(string.format("%d finished %s hidden (see Settings)", hidden, hidden == 1 and "storyline" or "storylines"))
        top = top + 20 + SECTION_GAP
    end
    if #others > 0 and ns.GetSetting("showOthers") then
        top = top + RenderOthers(canvas, others, top, viewWidth) + SECTION_GAP
    end
    if #storylines == 0 and #others == 0 then
        local header = AcquireHeader(canvas)
        header:SetFontObject("GameFontNormal")
        header:ClearAllPoints()
        header:SetPoint("TOPLEFT", canvas, "TOPLEFT", PAD, -top)
        header:SetText("No quests for your character in this zone.")
        top = top + 30
    end
    canvas:SetSize(maxWidth, math.max(top, frame.graphScroll:GetHeight()))
    if frame.graphScroll.UpdateScrollChildRect then
        frame.graphScroll:UpdateScrollChildRect()
    end

    local done, total = ns.GetZoneProgress(selectedZone)
    frame.zoneTitle:SetText(string.format("%s  |cffaaaaaa%d / %d quests done, %d storylines|r",
        ns.GetMapName(selectedZone), done, total, #storylines))
end

-- ============================================================================
-- Zone list
-- ============================================================================

local function SortedZones()
    local zones = ns.GetZones()
    for _, z in ipairs(zones) do
        z.name = ns.GetMapName(z.id)
        z.continentName = (z.continent ~= 0 and z.continent ~= z.id) and ns.GetMapName(z.continent) or "Other"
    end
    table.sort(zones, function(a, b)
        if a.continentName ~= b.continentName then
            return a.continentName < b.continentName
        end
        return a.name < b.name
    end)
    return zones
end

local function SelectZone(zoneID)
    selectedZone = zoneID
    if LorePathDB then
        LorePathDB.lastZone = zoneID
    end
    for _, row in ipairs(zoneRows) do
        if row.selected then
            row.selected:SetShown(row.zoneID == zoneID)
        end
    end
    frame.graphScroll:SetVerticalScroll(0)
    frame.graphScroll:SetHorizontalScroll(0)
    RenderZone()
end

local function RenderZoneList()
    local list = frame.listContent
    for _, row in ipairs(zoneRows) do
        row:Hide()
    end
    local y, index, lastContinent = 4, 0, nil
    local function NextRow()
        index = index + 1
        local row = zoneRows[index]
        if not row then
            row = CreateFrame("Button", nil, list)
            row:SetHeight(18)
            row.text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            row.text:SetPoint("LEFT", 8, 0)
            row.text:SetJustifyH("LEFT")
            row.count = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
            row.count:SetPoint("RIGHT", -6, 0)
            row.selected = row:CreateTexture(nil, "BACKGROUND")
            row.selected:SetAllPoints()
            row.selected:SetColorTexture(1, 0.82, 0, 0.18)
            local hl = row:CreateTexture(nil, "HIGHLIGHT")
            hl:SetAllPoints()
            hl:SetColorTexture(1, 1, 1, 0.08)
            zoneRows[index] = row
        end
        row:ClearAllPoints()
        row:SetPoint("TOPLEFT", list, "TOPLEFT", 0, -y)
        row:SetPoint("RIGHT", list, "RIGHT", 0, 0)
        row:Show()
        y = y + 18
        return row
    end

    for _, z in ipairs(SortedZones()) do
        if z.continentName ~= lastContinent then
            lastContinent = z.continentName
            local heading = NextRow()
            heading.zoneID = nil
            heading:SetScript("OnClick", nil)
            heading:Disable()
            heading.text:SetFontObject("GameFontNormal")
            heading.text:SetText(z.continentName)
            heading.count:SetText("")
            heading.selected:Hide()
            y = y + 2
        end
        local row = NextRow()
        row.zoneID = z.id
        row:Enable()
        row.text:SetFontObject("GameFontHighlightSmall")
        row.text:SetText("  " .. z.name)
        local done, total = ns.GetZoneProgress(z.id)
        if total > 0 and done == total then
            row.count:SetText("|cff4fd35f" .. done .. "/" .. total .. "|r")
        else
            row.count:SetText(done .. "/" .. total)
        end
        row.selected:SetShown(z.id == selectedZone)
        row:SetScript("OnClick", function(self)
            SelectZone(self.zoneID)
        end)
    end
    list:SetHeight(y + 4)
end

-- ============================================================================
-- Frame
-- ============================================================================

local function CreateMainFrame()
    local ok, f = pcall(CreateFrame, "Frame", "LorePathFrame", UIParent, "BasicFrameTemplateWithInset")
    if not ok then
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

    local settingsButton = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    settingsButton:SetSize(80, 20)
    settingsButton:SetPoint("TOPRIGHT", f, "TOPRIGHT", -28, -2)
    settingsButton:SetText("Settings")
    settingsButton:SetScript("OnClick", function()
        ns.OpenSettings()
    end)

    local title = type(f.TitleText) == "table" and f.TitleText or nil
    if not title then
        title = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
        title:SetPoint("TOP", 0, -8)
    end
    title:SetText("LorePath")

    -- Zone list
    local listScroll = CreateFrame("ScrollFrame", nil, f)
    listScroll:SetPoint("TOPLEFT", f, "TOPLEFT", 10, -30)
    listScroll:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 10, 34)
    listScroll:SetWidth(LIST_W)
    local listContent = CreateFrame("Frame", nil, listScroll)
    listContent:SetSize(LIST_W, 10)
    listScroll:SetScrollChild(listContent)
    MakeScrollable(listScroll, false)
    f.listContent = listContent

    local divider = f:CreateTexture(nil, "ARTWORK")
    divider:SetColorTexture(1, 1, 1, 0.12)
    divider:SetPoint("TOPLEFT", listScroll, "TOPRIGHT", 4, 0)
    divider:SetPoint("BOTTOMLEFT", listScroll, "BOTTOMRIGHT", 4, 0)
    divider:SetWidth(1)

    -- Zone title above the graph
    local zoneTitle = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    zoneTitle:SetPoint("TOPLEFT", listScroll, "TOPRIGHT", 16, -2)
    zoneTitle:SetJustifyH("LEFT")
    f.zoneTitle = zoneTitle

    -- Storyline graph
    local graphScroll = CreateFrame("ScrollFrame", nil, f)
    graphScroll:SetPoint("TOPLEFT", listScroll, "TOPRIGHT", 10, -26)
    graphScroll:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -10, 34)
    local canvas = CreateFrame("Frame", nil, graphScroll)
    canvas:SetSize(10, 10)
    graphScroll:SetScrollChild(canvas)
    MakeScrollable(graphScroll, true)
    f.graphScroll = graphScroll
    f.canvas = canvas

    -- Legend and hint along the bottom
    local x = 14
    for _, status in ipairs(LEGEND_ORDER) do
        local swatch = f:CreateTexture(nil, "ARTWORK")
        swatch:SetSize(12, 12)
        swatch:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", x, 12)
        local c = STATUS_COLORS[status]
        swatch:SetColorTexture(c[1], c[2], c[3], 1)
        local label = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        label:SetPoint("LEFT", swatch, "RIGHT", 4, 0)
        label:SetText(STATUS_TEXT[status])
        x = x + 20 + label:GetStringWidth() + 14
    end
    local hint = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    hint:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -14, 12)
    hint:SetText("Drag to pan  -  Shift+wheel scrolls sideways  -  Click a quest for a waypoint")

    f:SetScript("OnShow", function()
        ns.Refresh()
    end)
    return f
end

-- The zone you're standing in, or the closest parent zone that has quests.
local function CurrentZone()
    local mapID = C_Map.GetBestMapForUnit and C_Map.GetBestMapForUnit("player")
    local known = {}
    for _, z in ipairs(ns.GetZones()) do
        known[z.id] = true
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
    if not selectedZone then
        selectedZone = CurrentZone() or (LorePathDB and LorePathDB.lastZone)
        if not selectedZone then
            local zones = SortedZones()
            selectedZone = zones[1] and zones[1].id
        end
    end
    RenderZoneList()
    RenderZone()
end

local refreshPending = false
function ns.QueueRefresh(delay)
    if refreshPending or not frame or not frame:IsShown() then
        return
    end
    refreshPending = true
    C_Timer.After(delay or 0.3, function()
        refreshPending = false
        ns.Refresh()
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
    end
    if frame:IsShown() then
        ns.Refresh()
    else
        frame:Show()
    end
end

-- Global so Bindings.xml can call it.
function LorePath_Toggle()
    ns.Toggle(false)
end
