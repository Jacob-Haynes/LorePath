-- Sharing quest text (issue #14): /lp share builds a share code from the quest
-- text you've saved that LorePath doesn't already ship, and shows it to copy
-- into a "Share quest text" issue on GitHub. A workflow there checks it and adds
-- it to Data/CommunityText.lua for everyone (tools/merge_quest_text.py).
--
-- The code is "LP1:" followed by JSON, one line:
--   LP1:{"v":1,"q":{"<questID>":{"t":title,"o":objectives,"d":description,
--        "p":progress,"c":completion,"m":copper,"x":xp,"r":[[factionID,amount],...],
--        "s":{"k":"u"|"o"|"i","n":creature or object ID,"m":mapID,"x":x,"y":y,"i":instance}}}}
-- s is where the quest was offered (issue #37), shared only for quests whose
-- start LorePath's own data doesn't have.
-- A big collection is split into several codes, each small enough for one
-- GitHub issue. Players without a GitHub account paste them into the share page
-- (share/, a Cloudflare Worker), which opens the issues for them.

local addonName, ns = ...

ns.SHARE_PREFIX = "LP1:"
ns.SHARE_PART_LIMIT = 60000 -- characters per code (GitHub issues allow 65536)
ns.SHARE_URL = "github.com/Jacob-Haynes/LorePath/issues/new/choose"
-- The share page (share/README.md), once it's deployed; until then the window
-- only names the GitHub issue form.
ns.SHARE_PAGE_URL = nil

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
-- first, so text saved on one character doesn't carry another's name. And their
-- classes and races (older saves have just `true` for each name), with the
-- character you're on, for ns.PutPlaceholders.
local function AccountNames()
    local names, people = {}, { ns.CurrentPerson() }
    for name, who in pairs(LorePathDB and LorePathDB.characters or {}) do
        if type(name) == "string" and name ~= "" then
            table.insert(names, name)
        end
        if type(who) == "table" then
            table.insert(people, who)
        end
    end
    table.sort(names, function(a, b) return #a > #b end)
    return names, people
end

-- Text as it should be shared: names back to $N, no colour codes or links, and
-- for story text (not objectives) class and race back to $C and $R.
local function Scrub(text, names, people)
    if type(text) ~= "string" then
        return nil
    end
    text = text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""):gsub("|H.-|h", ""):gsub("|h", "")
    for _, name in ipairs(names) do
        text = text:gsub("%f[%w]" .. name:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0") .. "%f[%W]", "$N")
    end
    text = ns.PutPlaceholders(text, people)
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

-- Whether a quest's start is worth sharing: LorePath's own data has no start
-- point or quest giver for it, or it starts from an item pfQuest doesn't know.
local function WantStart(id)
    local q = ns.Quests[id]
    if q.cs then
        return true -- only what players have shared so far
    end
    if not q.m and not q.di then
        return true
    end
    if not q.qg and not q.si then
        return true
    end
    return q.si ~= nil and not (ns.QuestStarts and ns.QuestStarts[id])
end

-- A saved start, when it's worth sharing and LorePath doesn't already have it
-- (or a better one: a quest giver beats an item or object).
local function ShareStart(id, start, shipped)
    if type(start) ~= "table" or not start.k or not WantStart(id) then
        return nil
    end
    if ns.BetterStart(shipped, start) ~= start then
        return nil
    end
    return start
end

-- The fields of one saved quest worth sharing: anything that isn't already in
-- LorePath's community text, word for word, or the bundled vanilla text once its
-- placeholders are filled in (which also catches gendered wording).
local function ShareEntry(id, saved, names, people)
    local shipped = ns.CommunityText and ns.CommunityText[id] or {}
    local bundled = ns.QuestText and ns.QuestText[id] or {}
    local out = {}
    local function New(field, value)
        return value ~= nil and value ~= shipped[field] and value ~= bundled[field]
            and not ns.MatchesBundled(value, bundled[field], people)
    end
    local title = ns.GetQuestName(id)
    if New("t", title) then
        out.t = title
    end
    for _, pair in ipairs(TEXT_FIELDS) do
        local value = Scrub(saved[pair[2]], names, pair[1] ~= "o" and people or nil)
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
    out.s = ShareStart(id, saved.start, shipped.s)
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

local function EncodeStart(s)
    local parts = { '"k":' .. JsonString(s.k) }
    for _, field in ipairs({ "n", "m", "i" }) do
        if type(s[field]) == "number" then
            table.insert(parts, string.format('"%s":%d', field, s[field]))
        end
    end
    if type(s.m) == "number" and type(s.x) == "number" and type(s.y) == "number" then
        table.insert(parts, string.format('"x":%.1f,"y":%.1f', s.x, s.y))
    end
    return "{" .. table.concat(parts, ",") .. "}"
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
    if e.s then
        table.insert(parts, '"s":' .. EncodeStart(e.s))
    end
    return '"' .. id .. '":{' .. table.concat(parts, ",") .. "}"
end

-- The share codes for everything worth sharing, and how many quests they hold.
function ns.BuildShareCodes(limit)
    limit = limit or ns.SHARE_PART_LIMIT
    local cache = LorePathDB and LorePathDB.questCache or {}
    local names, people = AccountNames()
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
        local entry = ShareEntry(id, cache[id], names, people)
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
        f.CloseButton = close
    end
    ns.ui.CloseDirectly(f) -- works in combat too
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
    local where, which
    if ns.SHARE_PAGE_URL then
        which = #f.codes > 1 and string.format(" This is code %d of %d: paste them all, one after another.", part, #f.codes) or ""
        where = string.format("paste it at %s (no account needed), or into a new \"Share quest text\" issue at %s", ns.SHARE_PAGE_URL, ns.SHARE_URL)
    else
        which = #f.codes > 1 and string.format(" This is code %d of %d: send each one, in its own issue.", part, #f.codes) or ""
        where = string.format("paste it into a new \"Share quest text\" issue at %s", ns.SHARE_URL)
    end
    f.info:SetText(string.format(
        "Quest text and quest starts you've saved that LorePath doesn't have yet: %d %s.%s\n\n"
        .. "Click the code, press Ctrl+C to copy it, then %s. "
        .. "Your name, class and race are replaced with $N, $C and $R. Quest starts say who offered each quest and where, nothing about you.",
        f.count, f.count == 1 and "quest" or "quests", which, where))
    f.prev:SetShown(#f.codes > 1)
    f.next:SetShown(#f.codes > 1)
    f.prev:SetEnabled(part > 1)
    f.next:SetEnabled(part < #f.codes)
end

-- /lp share
function ns.OpenShare()
    local codes, count = ns.BuildShareCodes()
    if count == 0 then
        ns.Print("Nothing new to share: LorePath already has the text and start of every quest you've saved. Thank you!")
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
