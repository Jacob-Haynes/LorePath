-- LorePath quest detail panel: pops out from the right edge of the main window
-- when you click a quest, and shows what the game (and LorePath's data) knows
-- about it: requirements, where it starts, quest text, item rewards and the chain.
-- Also saves quest text and rewards as you play (LorePathDB.questCache).

local addonName, ns = ...

local S = ns.STATUS
local IsOnQuest = function(id) return ns.IsOnQuest(id) end
local PANEL_W = 330
local TEXT_W = PANEL_W - 44
local ICON = 30

local panel
local pools = { texts = {}, buttons = {}, items = {}, sources = {} }
local used = { texts = 0, buttons = 0, items = 0, sources = 0 }
ns.detailQuest = nil

-- ============================================================================
-- Quest information from the client (and what LorePath saw at quest givers)
-- ============================================================================

local function Cache()
    if not LorePathDB then
        return {}
    end
    LorePathDB.questCache = LorePathDB.questCache or {}
    return LorePathDB.questCache
end

-- WoW Forever's client can hand addons "secret" values: ones they may pass on
-- but not compare, read or test (issecretvalue says which). Using one is an
-- error, so anything secret is treated as unknown. (UnitGUID("questnpc") is
-- one, in some quest windows.)
local function IsSecret(value)
    if type(issecretvalue) ~= "function" then
        return false
    end
    local ok, secret = pcall(issecretvalue, value)
    return ok and secret == true
end
ns.IsSecret = IsSecret

local function Get(fn, ...)
    if type(fn) == "function" then
        local ok, value = pcall(fn, ...)
        if ok and not IsSecret(value) and value ~= "" then
            return value
        end
    end
end

local LogQuestText, QuestLinkText, ReputationRewards -- defined below

-- The game fills your character's name into quest text. Saved text puts the
-- $N placeholder back, so it reads right on other characters and is safe to
-- share (see tools/merge_quest_text.py).
local function Unfill(text)
    if IsSecret(text) then
        return nil
    end
    if type(text) ~= "string" then
        return text
    end
    local name = UnitName and UnitName("player")
    if type(name) == "string" and name ~= "" then
        local pattern = "%f[%w]" .. name:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0") .. "%f[%W]"
        text = text:gsub(pattern, "$N")
    end
    return text
end

local function GetText(fn, ...)
    return Unfill(Get(fn, ...))
end

-- ============================================================================
-- Class and race placeholders
-- ============================================================================
-- The game fills your class and race into quest text too ($C, $R). Saved story
-- text (description, progress, completion) puts them back, or a shared quest
-- would call everyone a mage. Quest text also uses these words in general
-- ("the blood of a hunter", "we tauren"), so only the uses that address you are
-- replaced:
--   class: any use except after an article ("a hunter") or inside a name
--          ("Defias Mage");
--   race:  only when said to you: ", orc." or "Orc, ..." at the start.
-- Objectives aren't touched: they're full of creature names. Gendered wording
-- ($Ghe:she;) can't be told apart from the rest; ns.MatchesBundled catches it
-- for the vanilla quests the bundled text has.

local function Escape(s)
    return (s:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]", "%%%0"))
end

local ARTICLES = { a = true, an = true, the = true, A = true, An = true, The = true }

local function ReplaceClass(text, word, upper, lower)
    for _, form in ipairs({ word, word:lower() }) do
        local placeholder = form ~= form:lower() and upper or lower
        local source = text
        text = source:gsub("()(%f[%w]" .. Escape(form) .. "%f[%W])", function(at, found)
            local before = source:sub(1, at - 1):match("(%a+)%s+$")
            if before and (ARTICLES[before] or (form ~= form:lower() and before:match("^%u"))) then
                return found
            end
            return placeholder
        end)
    end
    return text
end

local function ReplaceRace(text, word, upper, lower)
    for _, form in ipairs({ word, word:lower() }) do
        local placeholder = form ~= form:lower() and upper or lower
        local p = Escape(form)
        text = text:gsub("(,%s+)" .. p .. "([%.!%?,;])", "%1" .. placeholder .. "%2")
        text = text:gsub("^" .. p .. "([,!])", placeholder .. "%1")
    end
    return text
end

-- Puts $C/$c and $R/$r back for each of `people` ({class = "Mage", race = "Orc"}).
function ns.PutPlaceholders(text, people)
    if type(text) ~= "string" then
        return text
    end
    for _, who in ipairs(people or {}) do
        if type(who) == "table" then
            if type(who.class) == "string" and who.class ~= "" then
                text = ReplaceClass(text, who.class, "$C", "$c")
            end
            if type(who.race) == "string" and who.race ~= "" then
                text = ReplaceRace(text, who.race, "$R", "$r")
            end
        end
    end
    return text
end

-- The character you're playing, as ns.PutPlaceholders wants it.
function ns.CurrentPerson()
    return {
        class = UnitClass and (UnitClass("player")) or nil,
        race = UnitRace and (UnitRace("player")) or nil,
    }
end

-- Whether `text` (saved from the game) is the bundled vanilla text `bundled`
-- with its placeholders filled in, for any of `people`, either gender. Spacing
-- is ignored: the game and pfQuest don't always agree on it.
function ns.MatchesBundled(text, bundled, people)
    if type(text) ~= "string" or type(bundled) ~= "string" then
        return false
    end
    local function Squeeze(s)
        return (s:gsub("%s+", ""))
    end
    local classes, races = { "$C", "$c" }, { "$R", "$r" }
    for _, who in ipairs(people or {}) do
        if type(who) == "table" then
            for _, pair in ipairs({ { classes, who.class }, { races, who.race } }) do
                local list, word = pair[1], pair[2]
                if type(word) == "string" and word ~= "" then
                    table.insert(list, Squeeze(word))
                    table.insert(list, Squeeze(word:lower()))
                end
            end
        end
    end
    -- The bundled text as a list of steps, each a list of what may stand there.
    local steps, pos = {}, 1
    while pos <= #bundled do
        local s = bundled:find("%$%a", pos)
        if not s then
            table.insert(steps, { Squeeze(bundled:sub(pos)) })
            break
        end
        table.insert(steps, { Squeeze(bundled:sub(pos, s - 1)) })
        local kind = bundled:sub(s + 1, s + 1):lower()
        local _, gEnd, male, female = bundled:find("^%$[Gg]%s*([^:;]-)%s*:%s*([^;]-)%s*;", s)
        if gEnd then
            table.insert(steps, { Squeeze(male), Squeeze(female) })
            pos = gEnd + 1
        else
            if kind == "n" then
                table.insert(steps, { "$N" })
            elseif kind == "c" then
                table.insert(steps, classes)
            elseif kind == "r" then
                table.insert(steps, races)
            elseif kind ~= "b" then -- $B is a line break: spacing, so nothing
                table.insert(steps, { bundled:sub(s, s + 1) })
            end
            pos = s + 2
        end
    end
    local target = Squeeze(text)
    local function Match(i, at)
        if i > #steps then
            return at == #target + 1
        end
        for _, option in ipairs(steps[i]) do
            if target:sub(at, at + #option - 1) == option and Match(i + 1, at + #option) then
                return true
            end
        end
        return false
    end
    return Match(1, 1)
end

-- Saved story text: your name, class and race back to placeholders.
local function GetStory(fn, ...)
    return ns.PutPlaceholders(Unfill(Get(fn, ...)), { ns.CurrentPerson() })
end

local function Saved(id)
    local entry = Cache()[id] or {}
    Cache()[id] = entry
    return entry
end

local function AfterCapture(id)
    if panel and panel:IsShown() and ns.detailQuest == id then
        ns.RefreshDetail()
    end
end

-- Who or what is offering the quest on screen, and where you are (issue #37):
-- { k = "u" creature / "o" object / "i" item, n = creature or object ID,
--   m, x, y = your map and position (%), or i = the instance you're in }.
-- A quest another player shares with you (the quest window's unit is a player)
-- says nothing about where it starts, so it isn't kept. Nor is one whose
-- giver the game keeps secret: an unknown giver mustn't be mistaken for an item.
local function SeenStart()
    local start = {}
    if type(UnitGUID) == "function" then
        local ok, raw = pcall(UnitGUID, "questnpc")
        if ok and IsSecret(raw) then
            return nil
        end
    end
    local guid = Get(UnitGUID, "questnpc")
    local kind, objectID
    if type(guid) == "string" then
        kind, objectID = guid:match("^(%a+)%-%d+%-%d+%-%d+%-%d+%-(%d+)")
        kind = kind or guid:match("^(%a+)")
    end
    if kind == "Creature" or kind == "Vehicle" then
        start.k, start.n = "u", tonumber(objectID)
    elseif kind == "GameObject" then
        start.k, start.n = "o", tonumber(objectID)
    elseif kind == nil then
        start.k = "i" -- no unit: the quest came from an item in your bags
    else
        return nil
    end
    local map = C_Map and Get(C_Map.GetBestMapForUnit, "player")
    if type(map) ~= "number" then
        return start
    end
    if Get(IsInInstance) then
        start.i = map
        return start
    end
    local pos = Get(C_Map.GetPlayerMapPosition, map, "player")
    local ok, x, y = pcall(function() return pos:GetXY() end)
    if ok and not IsSecret(x) and not IsSecret(y) and type(x) == "number" and type(y) == "number" and (x > 0 or y > 0) then
        start.m = map
        start.x = math.floor(x * 1000 + 0.5) / 10
        start.y = math.floor(y * 1000 + 0.5) / 10
    end
    return start
end

-- One start per quest: the first one seen, unless a quest giver offers it
-- after an item or object did.
function ns.BetterStart(old, new)
    if type(new) ~= "table" or not new.k then
        return old
    end
    if type(old) ~= "table" or not old.k or (old.k ~= "u" and new.k == "u") then
        return new
    end
    return old
end

-- What a quest giver shows when it offers a quest (QUEST_DETAIL): its text,
-- objectives and rewards, kept for quests you don't accept straight away, and
-- where it was offered.
function ns.CaptureQuestDetail()
    local id = Get(GetQuestID)
    if not id or id == 0 or not ns.Quests[id] then
        return
    end
    local entry = Saved(id)
    entry.text = GetStory(GetQuestText) or entry.text
    entry.obj = GetText(GetObjectiveText) or entry.obj
    entry.money = Get(GetRewardMoney) or entry.money
    entry.xp = Get(GetRewardXP) or entry.xp
    entry.start = ns.BetterStart(entry.start, SeenStart())
    AfterCapture(id)
end

-- Handing items in mid-quest (QUEST_PROGRESS): what the quest giver says while
-- you're still working on it.
function ns.CaptureQuestProgress()
    local id = Get(GetQuestID)
    if not id or id == 0 or not ns.Quests[id] then
        return
    end
    local entry = Saved(id)
    entry.prog = GetStory(GetProgressText) or entry.prog
    AfterCapture(id)
end

-- The reward screen at turn-in (QUEST_COMPLETE): the quest's closing text,
-- which is the end of that part of the story.
function ns.CaptureQuestComplete()
    local id = Get(GetQuestID)
    if not id or id == 0 or not ns.Quests[id] then
        return
    end
    local entry = Saved(id)
    entry.done = GetStory(GetRewardText) or entry.done
    entry.money = Get(GetRewardMoney) or entry.money
    entry.xp = Get(GetRewardXP) or entry.xp
    AfterCapture(id)
end

-- A quest in your log: its text, objectives and rewards, saved so they're
-- still there after you turn it in.
function ns.CaptureLogQuest(id)
    if not id or not ns.Quests[id] or not IsOnQuest(id) then
        return
    end
    local entry = Saved(id)
    local text, objectives = LogQuestText(id)
    entry.text = ns.PutPlaceholders(Unfill(text), { ns.CurrentPerson() }) or entry.text
    entry.obj = Unfill(objectives) or entry.obj
    local money, xp = Get(GetQuestLogRewardMoney, id), Get(GetQuestLogRewardXP, id)
    if (money and money > 0) or (xp and xp > 0) then
        entry.money, entry.xp = money or 0, xp or 0
    end
    local rep = ReputationRewards(id)
    if #rep > 0 then
        entry.rep = rep -- { {factionID, amount}, ... }
    end
    AfterCapture(id)
end

-- Everything currently in your log (at login, so installing LorePath mid-quest
-- still captures those quests).
function ns.CaptureQuestLog()
    if not (C_QuestLog.GetNumQuestLogEntries and C_QuestLog.GetInfo) then
        return
    end
    for i = 1, C_QuestLog.GetNumQuestLogEntries() do
        local info = C_QuestLog.GetInfo(i)
        if info and not info.isHeader and info.questID then
            ns.CaptureLogQuest(info.questID)
        end
    end
end

-- Description and objectives text of a quest in your log (the log reads the
-- selected quest, so select it briefly and put the old selection back).
function LogQuestText(id)
    if not (IsOnQuest(id) and C_QuestLog.SetSelectedQuest and type(GetQuestLogQuestText) == "function") then
        return nil
    end
    local previous = C_QuestLog.GetSelectedQuest and C_QuestLog.GetSelectedQuest()
    C_QuestLog.SetSelectedQuest(id)
    local ok, text, objectives = pcall(GetQuestLogQuestText)
    if previous and previous ~= 0 then
        C_QuestLog.SetSelectedQuest(previous)
    end
    if ok then
        return (not IsSecret(text)) and text or nil, (not IsSecret(objectives)) and objectives or nil
    end
end

-- Objective lines ("Defias Thug slain: 0/15"). Works for quests the client has
-- loaded, accepted or not.
local function Objectives(id)
    local lines = {}
    if C_QuestLog.GetQuestObjectives then
        local ok, list = pcall(C_QuestLog.GetQuestObjectives, id)
        if ok and type(list) == "table" then
            for _, o in ipairs(list) do
                if o.text and o.text ~= "" then
                    table.insert(lines, { text = o.text, done = o.finished })
                end
            end
        end
    end
    if #lines == 0 and type(GetQuestObjectiveInfo) == "function" then
        for i = 1, 10 do
            local ok, text, _, finished = pcall(GetQuestObjectiveInfo, id, i, false)
            if not ok or not text or text == "" then
                break
            end
            table.insert(lines, { text = text, done = finished })
        end
    end
    return lines
end

-- Reputation rewards of a quest in your log: { {factionID, amount}, ... }.
function ReputationRewards(id)
    local list = {}
    if not IsOnQuest(id) or type(GetNumQuestLogRewardFactions) ~= "function" then
        return list
    end
    local ok, count = pcall(GetNumQuestLogRewardFactions, id)
    for i = 1, (ok and tonumber(count) or 0) do
        local ok2, factionID, amount = pcall(GetQuestLogRewardFactionInfo, i, id)
        if ok2 and tonumber(factionID) and tonumber(amount) then
            table.insert(list, { factionID, amount })
        end
    end
    return list
end

-- Fills in quest text placeholders: $N name, $C class, $R race, $G male:female;
-- and $B line breaks.
function ns.FillQuestText(text)
    if type(text) ~= "string" then
        return text
    end
    local name = (UnitName and UnitName("player")) or "adventurer"
    local class = (UnitClass and UnitClass("player")) or "adventurer"
    local race = (UnitRace and UnitRace("player")) or "traveller"
    local female = UnitSex and UnitSex("player") == 3
    text = text:gsub("%$[Gg]%s*([^:;]-)%s*:%s*([^;]-)%s*;", function(male, fem)
        return female and fem or male
    end)
    text = text:gsub("%$[Bb]", "\n")
    text = text:gsub("%$[Nn]", name)
    text = text:gsub("%$C", class):gsub("%$c", class:lower())
    text = text:gsub("%$R", race):gsub("%$r", race:lower())
    return text
end

-- The quest's link tooltip (what you see hovering a quest link in chat): its
-- one-line goal and its requirements. The client gives this for any quest it
-- can load, including completed ones and WoW Forever's own.
function QuestLinkText(id)
    if not (C_TooltipInfo and C_TooltipInfo.GetHyperlink) then
        return nil, {}
    end
    local ok, data = pcall(C_TooltipInfo.GetHyperlink, "quest:" .. id)
    if not ok or type(data) ~= "table" or type(data.lines) ~= "table" then
        return nil, {}
    end
    local summary, goals, inRequirements = {}, {}, false
    for i = 2, #data.lines do -- line 1 is the title
        local text = data.lines[i].leftText
        if not IsSecret(text) and type(text) == "string" and text ~= "" and text ~= " " then
            if text:match("^Requirements") then
                inRequirements = true
            elseif inRequirements then
                table.insert(goals, (text:gsub("^%s*%-%s*", "")))
            else
                table.insert(summary, text)
            end
        end
    end
    return #summary > 0 and table.concat(summary, " ") or nil, goals
end

-- Name of an NPC by ID, from the game's creature tooltip (nil until it's cached).
local function NPCName(npcID)
    if not (C_TooltipInfo and C_TooltipInfo.GetHyperlink) then
        return nil
    end
    local ok, data = pcall(C_TooltipInfo.GetHyperlink, ("unit:Creature-0-0-0-0-%d-0000000000"):format(npcID))
    local line = ok and data and data.lines and data.lines[1]
    if not line or IsSecret(line.leftText) then
        return nil
    end
    return line.leftText ~= "" and line.leftText or nil
end

-- ============================================================================
-- Building blocks (pooled, laid out top to bottom)
-- ============================================================================

local content, cursor

local function Reset()
    for kind, pool in pairs(pools) do
        for _, obj in ipairs(pool) do
            obj:Hide()
        end
        used[kind] = 0
    end
    cursor = 6
end

local function Height(fontString, fallback)
    local h = fontString.GetStringHeight and fontString:GetStringHeight()
    return (type(h) == "number" and h > 0) and h or fallback
end

local function AddText(text, font, color, gap, indent)
    used.texts = used.texts + 1
    local fs = pools.texts[used.texts]
    if not fs then
        fs = content:CreateFontString(nil, "OVERLAY", font)
        fs:SetJustifyH("LEFT")
        fs:SetWordWrap(true)
        pools.texts[used.texts] = fs
    end
    fs:SetFontObject(font or "GameFontHighlightSmall")
    fs:ClearAllPoints()
    cursor = cursor + (gap or 4)
    fs:SetPoint("TOPLEFT", content, "TOPLEFT", 8 + (indent or 0), -cursor)
    fs:SetWidth(TEXT_W - (indent or 0))
    fs:SetText(text)
    local c = color or { 1, 1, 1 }
    fs:SetTextColor(c[1], c[2], c[3])
    fs:Show()
    cursor = cursor + Height(fs, 14)
    return fs
end

local function AddHeader(text)
    return AddText(text, "GameFontNormal", { 1, 0.82, 0 }, 14)
end

-- A clickable line: jumps to the quest in the graph and shows its details.
local function AddQuestLink(id, indent)
    used.buttons = used.buttons + 1
    local b = pools.buttons[used.buttons]
    if not b then
        b = CreateFrame("Button", nil, content)
        b.text = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        b.text:SetPoint("LEFT", 0, 0)
        b.text:SetJustifyH("LEFT")
        b.text:SetWordWrap(false)
        local hl = b:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        hl:SetColorTexture(1, 1, 1, 0.08)
        b:SetScript("OnClick", function(self)
            ns.FocusQuest(self.questID)
            ns.ShowDetail(self.questID)
        end)
        b:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_LEFT")
            GameTooltip:AddLine(ns.GetQuestNameOrID(self.questID), 1, 0.82, 0)
            local q = ns.Quests[self.questID]
            if q then
                GameTooltip:AddLine("In " .. ns.GetMapName(q.z), 0.75, 0.75, 0.75)
                GameTooltip:AddLine("Click to show this quest.", 0.5, 0.8, 1)
            else
                GameTooltip:AddLine("Not in LorePath's quest data.", 0.6, 0.6, 0.6)
            end
            GameTooltip:Show()
        end)
        b:SetScript("OnLeave", GameTooltip_Hide)
        pools.buttons[used.buttons] = b
    end
    b.questID = id
    cursor = cursor + 2
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", content, "TOPLEFT", 8 + (indent or 10), -cursor)
    b:SetSize(TEXT_W - (indent or 10), 16)
    local status = ns.Quests[id] and ns.GetStatus(id)
    local mark = (status == S.DONE and "|cff6bd35f[done]|r ") or (status == S.ACTIVE and "|cffffd100[in log]|r ") or ""
    b.text:SetText(mark .. ns.GetQuestNameOrID(id))
    b.text:SetWidth(TEXT_W - (indent or 10))
    b:EnableMouse(ns.Quests[id] ~= nil)
    b:Show()
    cursor = cursor + 16
    return b
end

-- One reward item: icon (with the real item tooltip) and its name.
-- The item's chat link, or nil while the client hasn't loaded it yet.
local function ItemLink(itemID)
    local getInfo = (C_Item and C_Item.GetItemInfo) or GetItemInfo
    if type(getInfo) == "function" then
        local ok, _, link = pcall(getInfo, itemID)
        if ok and type(link) == "string" then
            return link
        end
    end
    if C_Item and C_Item.RequestLoadItemDataByID then
        pcall(C_Item.RequestLoadItemDataByID, itemID)
    end
    return nil
end

-- Shift+click links the item in chat, Ctrl+click tries it on, as anywhere in
-- the game's own windows.
local function ItemClick(self)
    if not (IsShiftKeyDown() or IsControlKeyDown()) then
        return
    end
    local link = ItemLink(self.itemID)
    if not link then
        ns.Print("That item is still loading; try again in a moment.")
        return
    end
    if type(HandleModifiedItemClick) == "function" then
        HandleModifiedItemClick(link)
    elseif IsShiftKeyDown() and type(ChatEdit_InsertLink) == "function" then
        ChatEdit_InsertLink(link)
    end
end

local function AddItem(itemID)
    used.items = used.items + 1
    local b = pools.items[used.items]
    if not b then
        b = CreateFrame("Button", nil, content)
        b:SetSize(TEXT_W, ICON)
        b.icon = b:CreateTexture(nil, "ARTWORK")
        b.icon:SetSize(ICON, ICON)
        b.icon:SetPoint("LEFT", 0, 0)
        b.name = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        b.name:SetPoint("LEFT", b.icon, "RIGHT", 8, 0)
        b.name:SetPoint("RIGHT", 0, 0)
        b.name:SetJustifyH("LEFT")
        b:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_LEFT")
            if GameTooltip.SetItemByID then
                GameTooltip:SetItemByID(self.itemID)
            else
                GameTooltip:AddLine(ns.ui.ItemText(self.itemID))
            end
            GameTooltip:AddLine("Shift+click to link it in chat.", 0.5, 0.8, 1)
            GameTooltip:Show()
        end)
        b:SetScript("OnClick", ItemClick)
        b:SetScript("OnLeave", GameTooltip_Hide)
        pools.items[used.items] = b
    end
    b.itemID = itemID
    local icon = C_Item and C_Item.GetItemIconByID and C_Item.GetItemIconByID(itemID)
    b.icon:SetTexture(icon or "Interface\\Icons\\INV_Misc_QuestionMark")
    b.name:SetText(ns.ui.ItemText(itemID))
    cursor = cursor + 4
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", content, "TOPLEFT", 8, -cursor)
    b:Show()
    cursor = cursor + ICON
    return b
end

-- One place a quest's starting item comes from: "Dropped by X (33%)", and
-- under it where. Click an outdoor one to set a waypoint there.
local function AddSource(source)
    used.sources = used.sources + 1
    local b = pools.sources[used.sources]
    if not b then
        b = CreateFrame("Button", nil, content)
        b.what = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        b.what:SetPoint("TOPLEFT", 0, 0)
        b.what:SetJustifyH("LEFT")
        b.what:SetWordWrap(false)
        b.where = b:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        b.where:SetPoint("TOPLEFT", b.what, "BOTTOMLEFT", 0, -1)
        b.where:SetJustifyH("LEFT")
        b.where:SetWordWrap(false)
        local hl = b:CreateTexture(nil, "HIGHLIGHT")
        hl:SetAllPoints()
        hl:SetColorTexture(1, 1, 1, 0.08)
        b:SetScript("OnClick", function(self)
            local src = self.source
            if src and src.m then
                ns.SetWaypoint(src.m, src.x, src.y, src.n)
            end
        end)
        b:SetScript("OnEnter", function(self)
            local src = self.source
            if src and src.m then
                GameTooltip:SetOwner(self, "ANCHOR_LEFT")
                GameTooltip:AddLine(src.n, 1, 0.82, 0)
                GameTooltip:AddLine("Click to set a waypoint here.", 0.5, 0.8, 1)
                GameTooltip:Show()
            end
        end)
        b:SetScript("OnLeave", GameTooltip_Hide)
        pools.sources[used.sources] = b
    end
    b.source = source
    local what, where = ns.StartSourceText(source)
    b.what:SetText(what)
    b.where:SetText(where or "")
    b.what:SetWidth(TEXT_W - 10)
    b.where:SetWidth(TEXT_W - 10)
    cursor = cursor + 3
    b:ClearAllPoints()
    b:SetPoint("TOPLEFT", content, "TOPLEFT", 18, -cursor)
    b:SetSize(TEXT_W - 10, where and 28 or 15)
    b:EnableMouse(source.m ~= nil)
    b:Show()
    cursor = cursor + (where and 28 or 15)
    return b
end

-- ============================================================================
-- Panel
-- ============================================================================

local function CreatePanel()
    local main = ns.mainFrame
    local ok, p = pcall(CreateFrame, "Frame", "LorePathDetailFrame", main, "BasicFrameTemplateWithInset")
    if not ok then
        p = CreateFrame("Frame", "LorePathDetailFrame", main)
        local bg = p:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints()
        bg:SetColorTexture(0.05, 0.05, 0.05, 0.95)
        ns.ui.AddBorder(p, "BORDER")
        p:SetBorderColor(0.4, 0.4, 0.4, 1)
        local close = CreateFrame("Button", nil, p, "UIPanelCloseButton")
        close:SetPoint("TOPRIGHT", 2, 2)
        p.CloseButton = close
    end
    ns.ui.CloseDirectly(p) -- works in combat too
    -- Docked to the main window's right edge, a little shorter, like a drawer.
    p:SetWidth(PANEL_W)
    p:SetPoint("TOPLEFT", main, "TOPRIGHT", -2, -24)
    p:SetPoint("BOTTOMLEFT", main, "BOTTOMRIGHT", -2, 24)
    p:EnableMouse(true)
    p:Hide()
    local title = type(p.TitleText) == "table" and p.TitleText or p:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    if title ~= p.TitleText then
        title:SetPoint("TOP", 0, -6)
    end
    title:SetText("Quest details")

    local scroll = CreateFrame("ScrollFrame", nil, p)
    scroll:SetPoint("TOPLEFT", 6, -28)
    scroll:SetPoint("BOTTOMRIGHT", -8, 8)
    content = CreateFrame("Frame", nil, scroll)
    content:SetSize(PANEL_W - 14, 10)
    scroll:SetScrollChild(content)
    ns.ui.MakeScrollable(scroll, false)
    p.scroll = scroll

    -- Closing the panel (its X, or the main window closing) drops the selection.
    p:SetScript("OnHide", function()
        if ns.detailQuest then
            ns.detailQuest = nil
            if main:IsShown() then
                ns.Refresh()
            end
        end
    end)
    return p
end

local function Render(id)
    local q = ns.Quests[id]
    local UI = ns.ui
    Reset()
    local status = ns.GetStatus(id)
    local style = UI.STATUS_STYLE[status]

    -- Title and status
    AddText(ns.GetQuestNameOrID(id), "GameFontNormalLarge", { 1, 0.82, 0 }, 4)
    local dc = UI.DifficultyColor(q.l or 1)
    AddText(UI.Hex(dc) .. "Requires level " .. (q.l or 1) .. "|r", "GameFontHighlightSmall", nil, 4)
    local sc = (status == S.DONE or status == S.ACTIVE or status == S.REPEATABLE) and style.border or style.text or { 1, 1, 1 }
    local lock = ns.GetLockReason(id)
    local statusText = UI.STATUS_TEXT[status]
    if status == S.LEVEL and lock == "skill" then
        statusText = ns.HasProfession(q.sk) and "Your skill is too low" or "You don't have this profession"
    end
    AddText(statusText, "GameFontHighlightSmall", sc, 2)
    if status == S.BLOCKED then
        local missing = ns.MissingPrereq(id)
        if missing then
            AddText("First finish:", "GameFontDisableSmall", nil, 4)
            AddQuestLink(missing)
        end
    elseif lock == "minrep" and q.mr then
        AddText("Needs " .. ns.ReputationText(q.mr), "GameFontHighlightSmall", { 0.9, 0.9, 0.9 }, 2)
    elseif lock == "skill" then
        AddText("Needs " .. ns.SkillText(q), "GameFontHighlightSmall", { 0.9, 0.9, 0.9 }, 2)
    end
    if q.bc then
        AddText("Breadcrumb: it leads you to another quest.", "GameFontDisableSmall", nil, 2)
    end

    -- Where it starts
    AddHeader("Where")
    local hint = ns.ItemStartHint(id)
    local sources = ns.QuestStarts and ns.QuestStarts[id] or {}
    if q.m then
        AddText(string.format("Starts in %s (%.1f, %.1f)", ns.GetMapName(q.m), q.x, q.y), "GameFontHighlightSmall", nil, 4)
    else
        if q.di then
            AddText("Picked up inside " .. ns.GetMapName(q.di) .. ".", "GameFontHighlightSmall", nil, 4)
        elseif hint and not q.si then
            AddText(hint .. ".", "GameFontHighlightSmall", nil, 4)
        elseif not q.si then
            AddText("Start location unknown.", "GameFontDisableSmall", nil, 4)
        end
    end
    if q.qg then
        local name = NPCName(q.qg)
        if name then
            AddText("Quest giver: " .. name, "GameFontHighlightSmall", nil, 2)
        end
    end
    -- An item that starts the quest, and where it comes from.
    if q.si then
        AddText("Starts from an item:", "GameFontHighlightSmall", nil, 4)
        AddItem(q.si)
        for _, source in ipairs(sources) do
            AddSource(source)
        end
        -- No known source: where players were when the item offered it.
        if #sources == 0 and hint then
            AddText(hint .. ".", "GameFontHighlightSmall", nil, 2)
        end
    end
    -- "Show on map" when the start is known; "Open in quest log" beside it while
    -- the quest is in your log.
    local onQuest = IsOnQuest(id)
    panel.mapButton:SetShown(q.m ~= nil)
    panel.logButton:SetShown(onQuest)
    if q.m or onQuest then
        cursor = cursor + 6
        local x = 8
        for _, b in ipairs({ panel.mapButton, panel.logButton }) do
            if b:IsShown() then
                b:ClearAllPoints()
                b:SetPoint("TOPLEFT", content, "TOPLEFT", x, -cursor)
                x = x + b:GetWidth() + 6
            end
        end
        cursor = cursor + 22
    end

    -- AllTheThings' note, when it has one: where an item drops, what finishing
    -- the quest locks you out of, and so on. Shown even with spoilers hidden,
    -- since most are worth knowing before you start.
    local note = ns.QuestNotes and ns.QuestNotes[id]
    if note then
        AddHeader("Good to know")
        AddText(note, "GameFontHighlightSmall", { 0.65, 0.82, 1 }, 4)
    end

    -- Quest text, best source first: what the game showed you (saved as you play),
    -- then LorePath's community text (real Forever text other players collected),
    -- then the quest link tooltip's goal, then the bundled vanilla text (pfQuest).
    local logText, logObjectives = LogQuestText(id)
    local cached = Cache()[id] or {}
    local community = ns.CommunityText and ns.CommunityText[id] or {}
    local bundled = ns.QuestText and ns.QuestText[id] or {}
    local done = status == S.DONE
    local active = status == S.ACTIVE
    local usedBundled = false

    -- No spoilers: a quest you haven't started keeps its story hidden, and a quest
    -- in your log keeps how it ends hidden, until you press Reveal (which lasts
    -- until you look at another quest) or turn on "Show spoilers" in Settings.
    local revealed = ns.revealedQuest == id or ns.GetSetting("showSpoilers")
    panel.revealButton:Hide()
    local function RevealButton()
        cursor = cursor + 6
        panel.revealButton:ClearAllPoints()
        panel.revealButton:SetPoint("TOPLEFT", content, "TOPLEFT", 8, -cursor)
        panel.revealButton:Show()
        cursor = cursor + 22
    end
    if not done and not active and not revealed then
        AddHeader("Story")
        AddText("Find what awaits you.", "GameFontHighlightSmall", { 0.9, 0.86, 0.75 }, 4)
        RevealButton()
    else

    AddHeader("Objectives")
    local objectives = Objectives(id)
    local tipSummary, tipGoals = QuestLinkText(id)
    if IsOnQuest(id) and #objectives > 0 then
        -- In your log: the live objectives, with your progress.
        for _, o in ipairs(objectives) do
            AddText((o.done and "|cff6bd35f" or "") .. "- " .. o.text .. (o.done and "|r" or ""), "GameFontHighlightSmall", nil, 2, 6)
        end
    else
        -- Otherwise the quest's one-line goal: saved from the game, else the quest
        -- link's tooltip (the game's own current wording, done or not), else bundled.
        local summary = logObjectives or cached.obj or community.o or tipSummary
        if not summary and bundled.o then
            summary, usedBundled = bundled.o, true
        end
        local green = done and { 0.42, 0.83, 0.37 } or nil
        if summary then
            AddText(ns.FillQuestText(summary), "GameFontHighlightSmall", green, 4)
        end
        for _, goal in ipairs(tipGoals) do
            AddText("- " .. goal, "GameFontHighlightSmall", green, 2, 6)
        end
        if not summary and #tipGoals == 0 then
            AddText("Not loaded yet.", "GameFontDisableSmall", nil, 4)
        end
    end

    AddHeader("Description")
    local description = logText or cached.text or community.d
    if not description and bundled.d then
        description, usedBundled = bundled.d, true
    end
    if description then
        AddText(ns.FillQuestText(description), "GameFontHighlightSmall", { 0.9, 0.86, 0.75 }, 4)
    elseif done then
        AddText("You completed this before LorePath could save its text, and LorePath's quest text doesn't have it yet.", "GameFontDisableSmall", nil, 4)
    else
        AddText("Saved the first time a quest giver shows you this quest.", "GameFontDisableSmall", nil, 4)
    end
    local progress = cached.prog or community.p
    if progress then
        AddHeader("Progress")
        AddText(ns.FillQuestText(progress), "GameFontHighlightSmall", { 0.9, 0.86, 0.75 }, 4)
    end
    local completion = cached.done or community.c
    if completion then
        AddHeader("Completion")
        if done or revealed then
            AddText(ns.FillQuestText(completion), "GameFontHighlightSmall", { 0.9, 0.86, 0.75 }, 4)
        else
            -- In your log: how it ends stays hidden until you turn it in (or reveal it).
            AddText("Find out when you turn it in.", "GameFontDisableSmall", nil, 4)
            RevealButton()
        end
    end
    if usedBundled then
        AddText("Text from LorePath's bundled quest database (pfQuest). WoW Forever's wording may differ slightly; the game's own text replaces it once you see the quest.", "GameFontDisableSmall", { 0.55, 0.55, 0.55 }, 6)
    end
    end -- spoiler gate

    -- Rewards: items only. Gold, XP and reputation are still saved as you play
    -- (questCache money/xp/rep), just not shown for now.
    AddHeader("Rewards")
    for _, itemID in ipairs(q.rw or {}) do
        AddItem(itemID)
    end
    if not q.rw then
        AddText("No item rewards.", "GameFontDisableSmall", nil, 4)
    end

    -- The chain around it
    local before = {}
    for _, pre in ipairs(q.pre or {}) do
        if not ns.Quests[pre] or ns.IsEligible(pre) then
            table.insert(before, pre)
        end
    end
    local after = {}
    for _, nextID in ipairs(ns.GetFollowOns(id)) do
        if ns.IsEligible(nextID) then
            table.insert(after, nextID)
        end
    end
    for _, nextID in ipairs(q.nx or {}) do
        if ns.Quests[nextID] and ns.IsEligible(nextID) then
            table.insert(after, nextID)
        end
    end
    if #before > 0 or #after > 0 then
        AddHeader("Storyline")
        if #before > 0 then
            AddText("Comes after:", "GameFontDisableSmall", nil, 4)
            for _, pre in ipairs(before) do
                AddQuestLink(pre)
            end
        end
        if #after > 0 then
            AddText("Leads to:", "GameFontDisableSmall", nil, 6)
            for _, nextID in ipairs(after) do
                AddQuestLink(nextID)
            end
        end
    end

    -- The quest's WarcraftDB page, to copy into a browser (addons can't open one).
    AddText("WarcraftDB (click, then Ctrl+C to copy):", "GameFontDisableSmall", nil, 14)
    local link = panel.linkBox
    link.url = ns.WarcraftDBLink(id)
    link:SetText(link.url)
    link:SetCursorPosition(0)
    link:ClearAllPoints()
    link:SetPoint("TOPLEFT", content, "TOPLEFT", 14, -(cursor + 2))
    link:Show()
    cursor = cursor + 24

    content:SetHeight(cursor + 12)
end

-- The quest's page on WarcraftDB's WoW Forever database.
function ns.WarcraftDBLink(id)
    return "https://forever.warcraftdb.com/data/quest/" .. id
end

-- Shows a quest in the panel, opening it if needed.
function ns.ShowDetail(id)
    if not ns.Quests[id] or not ns.mainFrame then
        return
    end
    if not panel then
        panel = CreatePanel()
        local map = CreateFrame("Button", nil, content, "UIPanelButtonTemplate")
        map:SetSize(110, 20)
        map:SetText("Show on map")
        map:SetScript("OnClick", function()
            ns.ShowQuestStart(ns.detailQuest)
        end)
        panel.mapButton = map

        local log = CreateFrame("Button", nil, content, "UIPanelButtonTemplate")
        log:SetSize(130, 20)
        log:SetText("Open in quest log")
        log:SetScript("OnClick", function()
            ns.OpenInQuestLog(ns.detailQuest)
        end)
        log:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine("Open in quest log", 1, 0.82, 0)
            GameTooltip:AddLine("Shows this quest in the game's quest log, with its live objectives. Shift+click a quest in the graph does the same.", 1, 1, 1, true)
            GameTooltip:Show()
        end)
        log:SetScript("OnLeave", GameTooltip_Hide)
        panel.logButton = log

        -- Read-only text box holding the WarcraftDB address: click selects it all.
        local box = CreateFrame("EditBox", nil, content, "InputBoxTemplate")
        box:SetSize(TEXT_W - 12, 20)
        box:SetAutoFocus(false)
        box:SetFontObject("GameFontHighlightSmall")
        box:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
        box:SetScript("OnMouseUp", function(self) self:SetFocus(); self:HighlightText() end)
        box:SetScript("OnTextChanged", function(self, userInput)
            if userInput and self.url then -- typing can't change it
                self:SetText(self.url)
                self:HighlightText()
            end
        end)
        box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
        box:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
        panel.linkBox = box

        local reveal = CreateFrame("Button", nil, content, "UIPanelButtonTemplate")
        reveal:SetSize(90, 20)
        reveal:SetText("Reveal")
        reveal:SetScript("OnClick", function()
            ns.revealedQuest = ns.detailQuest
            ns.RefreshDetail()
        end)
        reveal:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:AddLine("Reveal the story", 1, 0.82, 0)
            GameTooltip:AddLine("Shows this quest's text until you look at another quest.", 1, 1, 1, true)
            GameTooltip:Show()
        end)
        reveal:SetScript("OnLeave", GameTooltip_Hide)
        panel.revealButton = reveal
    end
    if C_QuestLog.RequestLoadQuestByID then
        C_QuestLog.RequestLoadQuestByID(id)
    end
    local changed = ns.detailQuest ~= id
    if changed then
        ns.revealedQuest = nil -- revealing lasts for one quest at a time
    end
    ns.detailQuest = id
    panel:Show()
    if changed then
        panel.scroll:SetVerticalScroll(0)
    end
    ns.Refresh() -- redraws the graph (gold border on this quest) and this panel
end

-- Click on a quest: show it, or close the panel if it's already showing.
function ns.ToggleDetail(id)
    if panel and panel:IsShown() and ns.detailQuest == id then
        panel:Hide()
    else
        ns.ShowDetail(id)
    end
end

function ns.HideDetail()
    if panel then
        panel:Hide()
    end
end

function ns.RefreshDetail()
    if not panel or not panel:IsShown() then
        return
    end
    if not ns.detailQuest or not ns.Quests[ns.detailQuest] then
        panel:Hide()
        return
    end
    Render(ns.detailQuest)
end
