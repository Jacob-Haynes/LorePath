-- Sharing quest text (issue #14): /lp share builds a share code from the quest
-- text you've saved that LorePath doesn't already ship, and shows it to copy
-- into a "Share quest text" issue on GitHub. A workflow there checks it and adds
-- it to Data/CommunityText.lua for everyone (tools/merge_quest_text.py).
--
-- The code is "LP1:" followed by JSON, one line:
--   LP1:{"v":1,"q":{"<questID>":{"t":title,"o":objectives,"d":description,
--        "p":progress,"c":completion,"m":copper,"x":xp,"r":[[factionID,amount],...]}}}
-- A big collection is split into several codes, each small enough for one
-- GitHub issue.

local addonName, ns = ...

ns.SHARE_PREFIX = "LP1:"
ns.SHARE_PART_LIMIT = 60000 -- characters per code (GitHub issues allow 65536)
ns.SHARE_URL = "github.com/Jacob-Haynes/LorePath/issues/new/choose"

-- Saved field -> share field.
local TEXT_FIELDS = { { "o", "obj" }, { "d", "text" }, { "p", "prog" }, { "c", "done" } }

local function JsonString(s)
    -- "|" is escaped too: the edit box would otherwise read |c, |H and |n as
    -- colour, link and newline codes, and the copied text would lose them.
    return '"' .. s:gsub('[%c"\\|]', function(c)
        if c == '"' then
            return '\\"'
        elseif c == "\\" then
            return "\\\\"
        elseif c == "\n" then
            return "\\n"
        elseif c == "\t" then
            return "\\t"
        end
        return string.format("\\u%04x", c:byte())
    end) .. '"'
end

-- Every character name this account has used (LorePathDB.characters), longest
-- first, so text saved on one character doesn't carry another's name.
local function AccountNames()
    local names = {}
    for name in pairs(LorePathDB and LorePathDB.characters or {}) do
        if type(name) == "string" and name ~= "" then
            table.insert(names, name)
        end
    end
    table.sort(names, function(a, b) return #a > #b end)
    return names
end

-- Text as it should be shared: names back to $N, no colour codes or links.
local function Scrub(text, names)
    if type(text) ~= "string" then
        return nil
    end
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|H.-|h", ""):gsub("|h", "")
    for _, name in ipairs(names) do
        text = text:gsub("%f[%w]" .. name:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0") .. "%f[%W]", "$N")
    end
    text = text:gsub("\r", ""):match("^%s*(.-)%s*$")
    return text ~= "" and text or nil
end

local function SameRep(a, b)
    if type(a) ~= "table" or type(b) ~= "table" or #a ~= #b then
        return false
    end
    for i, pair in ipairs(a) do
        if not b[i] or pair[1] ~= b[i][1] or pair[2] ~= b[i][2] then
            return false
        end
    end
    return true
end

-- The fields of one saved quest worth sharing: anything that isn't already in
-- LorePath's community text or bundled vanilla text, word for word.
local function ShareEntry(id, saved, names)
    local shipped = ns.CommunityText and ns.CommunityText[id] or {}
    local bundled = ns.QuestText and ns.QuestText[id] or {}
    local out = {}
    local function New(field, value)
        return value ~= nil and value ~= shipped[field] and value ~= bundled[field]
    end
    local title = ns.GetQuestName(id)
    if New("t", title) then
        out.t = title
    end
    for _, pair in ipairs(TEXT_FIELDS) do
        local value = Scrub(saved[pair[2]], names)
        if New(pair[1], value) then
            out[pair[1]] = value
        end
    end
    for field, key in pairs({ m = "money", x = "xp" }) do
        local value = saved[key]
        if type(value) == "number" and value > 0 and value ~= shipped[field] then
            out[field] = math.floor(value)
        end
    end
    if type(saved.rep) == "table" and #saved.rep > 0 and not SameRep(saved.rep, shipped.r) then
        out.r = saved.rep
    end
    local fields = 0
    for _ in pairs(out) do
        fields = fields + 1
    end
    -- A title on its own only matters for quests with no name in LorePath yet.
    if fields == 0 or (fields == 1 and out.t and (shipped.t or bundled.t)) then
        return nil
    end
    return out
end

local function EncodeEntry(id, e)
    local parts = {}
    for _, field in ipairs({ "t", "o", "d", "p", "c" }) do
        if e[field] then
            table.insert(parts, '"' .. field .. '":' .. JsonString(e[field]))
        end
    end
    for _, field in ipairs({ "m", "x" }) do
        if e[field] then
            table.insert(parts, '"' .. field .. '":' .. string.format("%d", e[field]))
        end
    end
    if e.r then
        local pairsOut = {}
        for _, pair in ipairs(e.r) do
            if type(pair[1]) == "number" and type(pair[2]) == "number" then
                table.insert(pairsOut, string.format("[%d,%d]", pair[1], pair[2]))
            end
        end
        if #pairsOut > 0 then
            table.insert(parts, '"r":[' .. table.concat(pairsOut, ",") .. "]")
        end
    end
    return '"' .. id .. '":{' .. table.concat(parts, ",") .. "}"
end

-- The share codes for everything worth sharing, and how many quests they hold.
function ns.BuildShareCodes(limit)
    limit = limit or ns.SHARE_PART_LIMIT
    local cache = LorePathDB and LorePathDB.questCache or {}
    local names = AccountNames()
    local ids = {}
    for id in pairs(cache) do
        if type(id) == "number" and ns.Quests[id] then
            table.insert(ids, id)
        end
    end
    table.sort(ids)
    local head, tail = ns.SHARE_PREFIX .. '{"v":1,"q":{', "}}"
    local codes, current, length, count = {}, {}, 0, 0
    for _, id in ipairs(ids) do
        local entry = ShareEntry(id, cache[id], names)
        if entry then
            local encoded = EncodeEntry(id, entry)
            if #current > 0 and #head + length + #encoded + #current + #tail > limit then
                table.insert(codes, head .. table.concat(current, ",") .. tail)
                current, length = {}, 0
            end
            table.insert(current, encoded)
            length = length + #encoded
            count = count + 1
        end
    end
    if #current > 0 then
        table.insert(codes, head .. table.concat(current, ",") .. tail)
    end
    return codes, count
end

-- ============================================================================
-- Share window
-- ============================================================================

local shareFrame

local function CreateShareFrame()
    local ok, f = pcall(CreateFrame, "Frame", "LorePathShareFrame", UIParent, "BasicFrameTemplateWithInset")
    if not ok then
        f = CreateFrame("Frame", "LorePathShareFrame", UIParent)
        local bg = f:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(0.05, 0.05, 0.05, 0.95)
        local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
        close:SetPoint("TOPRIGHT", 2, 2)
    end
    f:SetSize(540, 380)
    f:SetPoint("CENTER")
    f:SetFrameStrata("DIALOG")
    f:SetClampedToScreen(true)
    f:EnableMouse(true)
    f:SetMovable(true)
    f:RegisterForDrag("LeftButton")
    f:SetScript("OnDragStart", f.StartMoving)
    f:SetScript("OnDragStop", f.StopMovingOrSizing)
    f:Hide()
    table.insert(UISpecialFrames, "LorePathShareFrame")
    local title = type(f.TitleText) == "table" and f.TitleText or f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    if title ~= f.TitleText then
        title:SetPoint("TOP", 0, -6)
    end
    title:SetText("Share quest text")

    local info = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    info:SetPoint("TOPLEFT", 16, -32)
    info:SetPoint("RIGHT", -16, 0)
    info:SetJustifyH("LEFT")
    f.info = info

    local scroll = CreateFrame("ScrollFrame", nil, f)
    scroll:SetPoint("TOPLEFT", 16, -96)
    scroll:SetPoint("BOTTOMRIGHT", -16, 44)
    local bg = scroll:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetColorTexture(0, 0, 0, 0.5)
    local box = CreateFrame("EditBox", nil, scroll)
    box:SetMultiLine(true)
    box:SetMaxLetters(0)
    box:SetAutoFocus(false)
    box:SetFontObject("GameFontHighlightSmall")
    box:SetWidth(500)
    scroll:SetScrollChild(box)
    scroll:EnableMouseWheel(true)
    scroll:SetScript("OnMouseWheel", function(self, delta)
        local y = self:GetVerticalScroll() - delta * 40
        self:SetVerticalScroll(math.max(0, math.min(y, self:GetVerticalScrollRange())))
    end)
    -- Read-only: typing puts the code back; clicking selects all of it.
    box:SetScript("OnTextChanged", function(self, userInput)
        if userInput and self.code then
            self:SetText(self.code)
            self:HighlightText()
        end
    end)
    box:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
    box:SetScript("OnMouseUp", function(self) self:SetFocus(); self:HighlightText() end)
    box:SetScript("OnEscapePressed", function(self) self:ClearFocus(); f:Hide() end)
    f.box = box

    local prev = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    prev:SetSize(90, 22)
    prev:SetPoint("BOTTOMLEFT", 16, 14)
    prev:SetText("Previous")
    prev:SetScript("OnClick", function() ns.ShowSharePart(f.part - 1) end)
    f.prev = prev
    local nextButton = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    nextButton:SetSize(90, 22)
    nextButton:SetPoint("LEFT", prev, "RIGHT", 6, 0)
    nextButton:SetText("Next")
    nextButton:SetScript("OnClick", function() ns.ShowSharePart(f.part + 1) end)
    f.next = nextButton
    local select = CreateFrame("Button", nil, f, "UIPanelButtonTemplate")
    select:SetSize(110, 22)
    select:SetPoint("BOTTOMRIGHT", -16, 14)
    select:SetText("Select all")
    select:SetScript("OnClick", function() box:SetFocus(); box:HighlightText() end)
    return f
end

-- Shows code number `part` (1-based) of the current share.
function ns.ShowSharePart(part)
    local f = shareFrame
    if not f or not f.codes or #f.codes == 0 then
        return
    end
    part = math.max(1, math.min(part, #f.codes))
    f.part = part
    local code = f.codes[part]
    f.box.code = code
    f.box:SetText(code)
    f.box:SetCursorPosition(0)
    local which = #f.codes > 1 and string.format(" This is code %d of %d: send each one, in its own issue.", part, #f.codes) or ""
    f.info:SetText(string.format(
        "Quest text you've saved that LorePath doesn't have yet: %d %s.%s\n\n"
        .. "Click the code, press Ctrl+C to copy it, then paste it into a new \"Share quest text\" issue at %s. "
        .. "Your character names are replaced with $N; nothing else about you is in the code.",
        f.count, f.count == 1 and "quest" or "quests", which, ns.SHARE_URL))
    f.prev:SetShown(#f.codes > 1)
    f.next:SetShown(#f.codes > 1)
    f.prev:SetEnabled(part > 1)
    f.next:SetEnabled(part < #f.codes)
end

-- /lp share
function ns.OpenShare()
    local codes, count = ns.BuildShareCodes()
    if count == 0 then
        ns.Print("Nothing new to share: LorePath already has the text of every quest you've saved. Thank you!")
        if shareFrame then
            shareFrame:Hide()
        end
        return false
    end
    shareFrame = shareFrame or CreateShareFrame()
    shareFrame.codes, shareFrame.count = codes, count
    shareFrame:Show()
    ns.ShowSharePart(1)
    return true
end
