-- LorePath core: who the player is, which quests they can do, each quest's status,
-- and how a zone's quests group into storylines. No UI code lives here.

local addonName, ns = ...

ns.CHAT_PREFIX = "|cffd4a017[LorePath]|r "

function ns.Print(msg)
    DEFAULT_CHAT_FRAME:AddMessage(ns.CHAT_PREFIX .. tostring(msg))
end

-- Status values, in the order a storyline progresses through them.
ns.STATUS = {
    DONE = "done",           -- completed (or an alternative version was)
    ACTIVE = "active",       -- in your quest log
    AVAILABLE = "available", -- you can pick it up now
    LEVEL = "level",         -- prerequisites done, but your level, skill or reputation is too low
    BLOCKED = "blocked",     -- an earlier quest isn't done yet
    MISSED = "missed",       -- a breadcrumb you skipped past (or reputation went too high); it can't be taken any more
    REPEATABLE = "repeatable", -- a daily or repeatable quest you can take now; it's never "done"
}

-- Repeatable quests (rp=1 in the data) never count towards progress: the game
-- doesn't record them as completed.
function ns.IsRepeatable(id)
    local q = ns.Quests[id]
    return q and q.rp == 1 or false
end

-- ============================================================================
-- Player
-- ============================================================================

local player = { race = 0, class = 0, faction = 0, level = 1, skills = {}, professions = {} }
ns.player = player

-- skill line -> rank, and skill line -> { name, icon } for the professions you have.
local function ReadProfessions()
    local skills, info = {}, {}
    if type(GetProfessions) ~= "function" or type(GetProfessionInfo) ~= "function" then
        return skills, info
    end
    local indices = { pcall(GetProfessions) }
    if not indices[1] then
        return skills, info
    end
    -- Slots can be empty (nil) in the middle, so walk all of them rather than ipairs.
    for slot = 2, 7 do
        local index = indices[slot]
        if index then
            local okInfo, name, icon, rank, _, _, _, skillLine = pcall(GetProfessionInfo, index)
            if okInfo and skillLine then
                skills[skillLine] = rank or 0
                info[skillLine] = { name = name, icon = icon }
            end
        end
    end
    return skills, info
end

function ns.RefreshPlayer()
    local _, _, raceID = UnitRace("player")
    local _, _, classID = UnitClass("player")
    local factionTag = UnitFactionGroup("player")
    player.race = raceID or 0
    player.class = classID or 0
    player.faction = (factionTag == "Horde" and 1) or (factionTag == "Alliance" and 2) or 0
    player.level = UnitLevel("player") or 1
    player.skills, player.professions = ReadProfessions()
    wipe(ns.standings)
end

-- ============================================================================
-- Reputation
-- ============================================================================

-- Standing thresholds, as cumulative reputation from Neutral = 0 (the scale ATT
-- and the client both use). Index = standing ID (1 Hated ... 8 Exalted).
local STANDING_MIN = { -42000, -6000, -3000, 0, 3000, 9000, 21000, 42000 }
local STANDING_NAMES = { "Hated", "Hostile", "Unfriendly", "Neutral", "Friendly", "Honored", "Revered", "Exalted" }

ns.standings = {} -- factionID -> cumulative standing, or false when the client doesn't know it

-- Standing name for a raw reputation value, e.g. 3000 -> "Friendly".
function ns.StandingName(value)
    local index = 1
    for i, min in ipairs(STANDING_MIN) do
        if value >= min then
            index = i
        end
    end
    return _G["FACTION_STANDING_LABEL" .. index] or STANDING_NAMES[index]
end

-- C_Reputation.GetFactionDataByID on the mainline client Forever runs on;
-- GetFactionInfoByID on older clients.
local function FactionData(factionID)
    if C_Reputation and C_Reputation.GetFactionDataByID then
        local ok, data = pcall(C_Reputation.GetFactionDataByID, factionID)
        if ok and type(data) == "table" then
            local standing = data.currentStanding
            if standing == nil and data.reaction and STANDING_MIN[data.reaction] then
                standing = STANDING_MIN[data.reaction]
            end
            return data.name, standing
        end
    end
    if type(GetFactionInfoByID) == "function" then
        local ok, name, _, standingID, _, _, barValue = pcall(GetFactionInfoByID, factionID)
        if ok and name then
            if barValue == nil and standingID and STANDING_MIN[standingID] then
                barValue = STANDING_MIN[standingID]
            end
            return name, barValue
        end
    end
    return nil, nil
end

-- The player's cumulative standing with a faction, or nil if the client doesn't know.
function ns.GetStanding(factionID)
    local cached = ns.standings[factionID]
    if cached == nil then
        local _, standing = FactionData(factionID)
        cached = type(standing) == "number" and standing or false
        ns.standings[factionID] = cached
    end
    return cached or nil
end

function ns.GetFactionName(factionID)
    return FactionData(factionID) or ("faction " .. tostring(factionID))
end

-- "Friendly with Darnassus" for a {factionID, value} requirement.
function ns.ReputationText(req)
    return ns.StandingName(req[2]) .. " with " .. ns.GetFactionName(req[1])
end

-- Is a reputation requirement unmet? Unknown standing never locks a quest.
local function BelowMinRep(q)
    local standing = q.mr and ns.GetStanding(q.mr[1])
    return standing ~= nil and standing < q.mr[2]
end

local function AboveMaxRep(q)
    local standing = q.xr and ns.GetStanding(q.xr[1])
    return standing ~= nil and standing >= q.xr[2]
end
ns.BelowMinRep, ns.AboveMaxRep = BelowMinRep, AboveMaxRep

-- ============================================================================
-- Completed quests
-- ============================================================================

local completed = {}

function ns.RefreshCompleted()
    wipe(completed)
    if C_QuestLog and C_QuestLog.GetAllCompletedQuestIDs then
        local ids = C_QuestLog.GetAllCompletedQuestIDs()
        if ids then
            for _, id in ipairs(ids) do
                completed[id] = true
            end
        end
    end
end

local function IsFlaggedCompleted(id)
    if completed[id] then
        return true
    end
    -- Fallback for anything turned in since the last refresh.
    if C_QuestLog and C_QuestLog.IsQuestFlaggedCompleted and C_QuestLog.IsQuestFlaggedCompleted(id) then
        completed[id] = true
        return true
    end
    return false
end

local function IsOnQuest(id)
    return C_QuestLog and C_QuestLog.IsOnQuest and C_QuestLog.IsOnQuest(id) or false
end
ns.IsOnQuest = IsOnQuest

-- ============================================================================
-- Eligibility and status
-- ============================================================================

local function Contains(list, value)
    for _, v in ipairs(list) do
        if v == value then
            return true
        end
    end
    return false
end

-- Can this character ever do the quest (faction, race, class, profession)?
-- With ignoreSkill, a profession you don't have doesn't count against it (for
-- the Professions page's "show professions you don't have").
function ns.IsEligible(id, ignoreSkill)
    local q = ns.Quests[id]
    if not q then
        return false
    end
    if q.f and q.f ~= player.faction then
        return false
    end
    if q.rc and not Contains(q.rc, player.race) then
        return false
    end
    if q.cl and not Contains(q.cl, player.class) then
        return false
    end
    if q.sk and not ignoreSkill and player.skills[q.sk] == nil then
        return false
    end
    return true
end

-- Done counts a completed alternative version of the quest too.
function ns.IsDone(id)
    if IsFlaggedCompleted(id) then
        return true
    end
    local q = ns.Quests[id]
    if q and q.alt then
        for _, alt in ipairs(q.alt) do
            if IsFlaggedCompleted(alt) then
                return true
            end
        end
    end
    return false
end

-- Prerequisites this character can actually do. ATT often lists race or faction
-- variants side by side; the ones you can't take don't block you.
local function RelevantPrereqs(q)
    local list = {}
    if not q.pre then
        return list
    end
    for _, pre in ipairs(q.pre) do
        if not ns.Quests[pre] or ns.IsEligible(pre) then
            table.insert(list, pre)
        end
    end
    return list
end

-- Returns the first prerequisite still needed, or nil when enough are done.
-- A repeatable prerequisite always counts as done: the game never flags it
-- completed, so requiring it would lock the quests after it forever.
function ns.MissingPrereq(id)
    local q = ns.Quests[id]
    if not q then
        return nil
    end
    local prereqs = RelevantPrereqs(q)
    if #prereqs == 0 then
        return nil
    end
    local needed = math.min(q.prn or #prereqs, #prereqs)
    local done, firstMissing = 0, nil
    for _, pre in ipairs(prereqs) do
        if ns.IsDone(pre) or ns.IsRepeatable(pre) then
            done = done + 1
        elseif not firstMissing then
            firstMissing = pre
        end
    end
    if done >= needed then
        return nil
    end
    return firstMissing
end

function ns.GetStatus(id)
    local q = ns.Quests[id]
    local S = ns.STATUS
    local repeatable = q and q.rp == 1
    if not repeatable and ns.IsDone(id) then
        return S.DONE
    end
    if IsOnQuest(id) then
        return S.ACTIVE
    end
    if q and q.bc and q.nx then
        for _, nextID in ipairs(q.nx) do
            if ns.IsDone(nextID) or IsOnQuest(nextID) then
                return S.MISSED
            end
        end
    end
    if q and AboveMaxRep(q) then
        return S.MISSED
    end
    if ns.MissingPrereq(id) then
        return S.BLOCKED
    end
    if ns.GetLockReason(id) then
        return S.LEVEL
    end
    return repeatable and S.REPEATABLE or S.AVAILABLE
end

-- Why a quest isn't open to you (yet): "level", "skill", "minrep" (not yet) or
-- "maxrep" (never again), or nil. Ignores prerequisites and completion.
function ns.GetLockReason(id)
    local q = ns.Quests[id]
    if not q then
        return nil
    end
    if AboveMaxRep(q) then
        return "maxrep"
    end
    if q.l and player.level < q.l then
        return "level"
    end
    if q.sk and (player.skills[q.sk] == nil or (q.sl and player.skills[q.sk] < q.sl)) then
        return "skill" -- skill too low, or (on the Professions page) a profession you don't have
    end
    if BelowMinRep(q) then
        return "minrep"
    end
    return nil
end

-- ============================================================================
-- Names (loaded on demand from the client)
-- ============================================================================

local requestedNames = {}

function ns.GetQuestName(id)
    local name = C_QuestLog and C_QuestLog.GetTitleForQuestID and C_QuestLog.GetTitleForQuestID(id)
    if name and name ~= "" then
        return name
    end
    if not requestedNames[id] and C_QuestLog and C_QuestLog.RequestLoadQuestByID then
        requestedNames[id] = true
        C_QuestLog.RequestLoadQuestByID(id)
    end
    return nil
end

function ns.GetQuestNameOrID(id)
    -- The client's name first; the bundled title while it loads (or if it never does).
    return ns.GetQuestName(id)
        or (ns.CommunityText and ns.CommunityText[id] and ns.CommunityText[id].t)
        or (ns.QuestText and ns.QuestText[id] and ns.QuestText[id].t)
        or ("Quest #" .. id)
end

-- Name of an instance page (see ns.InstanceZones): the Encounter Journal's name,
-- then the map's, then the area's, then the English name stored with the data.
local function InstanceName(zoneID, info)
    if info.ej and type(EJ_GetInstanceInfo) == "function" then
        local ok, name = pcall(EJ_GetInstanceInfo, info.ej)
        if ok and type(name) == "string" and name ~= "" then
            return name
        end
    end
    if zoneID > 0 and C_Map and C_Map.GetMapInfo then
        local map = C_Map.GetMapInfo(zoneID)
        if map and map.name and map.name ~= "" then
            return map.name
        end
    end
    if info.ar and C_Map and C_Map.GetAreaInfo then
        local ok, name = pcall(C_Map.GetAreaInfo, info.ar)
        if ok and type(name) == "string" and name ~= "" then
            return name
        end
    end
    return info.n or ("Instance " .. tostring(info.ej or zoneID))
end

-- Name of a map, or of a zone list page (which may be an instance page, or the
-- Class or a profession page).
function ns.GetMapName(mapID)
    if type(mapID) == "string" then
        return ns.SpecialPageName(mapID)
    end
    local instance = mapID and ns.InstanceInfo and ns.InstanceInfo[mapID]
    if instance then
        return InstanceName(mapID, instance)
    end
    local info = mapID and C_Map and C_Map.GetMapInfo and C_Map.GetMapInfo(mapID)
    return info and info.name or ("Map " .. tostring(mapID))
end

-- "dungeon" or "raid" for an instance page, nil for an outdoor zone.
function ns.GetInstanceKind(zoneID)
    return ns.InstanceZones and ns.InstanceZones[zoneID] or nil
end

-- The instance page for where the player is, when they're inside an instance:
-- matched by map ID, by the Encounter Journal's instance for the map, or by the
-- instance's area name. Returns nil outside instances or when nothing matches.
function ns.CurrentInstancePage(mapID)
    if not ns.InstanceInfo then
        return nil
    end
    if mapID and ns.InstanceInfo[mapID] then
        return mapID
    end
    if type(IsInInstance) ~= "function" or not IsInInstance() then
        return nil
    end
    local journalID
    if mapID and type(EJ_GetInstanceForMap) == "function" then
        local ok, id = pcall(EJ_GetInstanceForMap, mapID)
        journalID = ok and id ~= 0 and id or nil
    end
    local zoneText = type(GetRealZoneText) == "function" and GetRealZoneText() or nil
    for page, info in pairs(ns.InstanceInfo) do
        if journalID and info.ej == journalID then
            return page
        end
    end
    if zoneText and zoneText ~= "" and C_Map and C_Map.GetAreaInfo then
        for page, info in pairs(ns.InstanceInfo) do
            if info.ar and C_Map.GetAreaInfo(info.ar) == zoneText then
                return page
            end
        end
    end
    return nil
end

-- ============================================================================
-- Zones and storylines
-- ============================================================================

local zoneQuests -- zone mapID -> list of quest IDs (built once)
local classQuests -- class-restricted quests, from every zone
local professionQuests -- profession skill line -> its quests, from every zone

-- Blacksmithing's specialisations have their own skill lines in the data; they
-- belong on the Blacksmithing page.
local PROFESSION_PARENT = { [9787] = 164, [9788] = 164 } -- Weaponsmith, Armorsmith

function ns.ProfessionOf(q)
    return q.sk and (PROFESSION_PARENT[q.sk] or q.sk) or nil
end

local function BuildZoneIndex()
    zoneQuests, classQuests, professionQuests = {}, {}, {}
    local function Add(t, key, id)
        t[key] = t[key] or {}
        table.insert(t[key], id)
    end
    for id, q in pairs(ns.Quests) do
        Add(zoneQuests, q.z, id)
        if q.cl then
            table.insert(classQuests, id)
        end
        if q.sk then
            Add(professionQuests, ns.ProfessionOf(q), id)
        end
    end
    table.sort(classQuests)
    for _, list in pairs(professionQuests) do
        table.sort(list)
    end
end

-- ============================================================================
-- Class and profession pages (issue #8)
-- ============================================================================
-- Besides zones (map IDs) and instances, the zone list has two kinds of page,
-- keyed by string: "class" (every quest for your class, from all zones, so class
-- chains that travel show as one storyline) and "prof:<skill line>" (one
-- profession's quests).

-- English names and icons, for professions you don't have (the client names the
-- ones you do).
ns.PROFESSIONS = {
    [171] = { name = "Alchemy", icon = "Interface\\Icons\\Trade_Alchemy" },
    [164] = { name = "Blacksmithing", icon = "Interface\\Icons\\Trade_BlackSmithing" },
    [333] = { name = "Enchanting", icon = "Interface\\Icons\\Trade_Engraving" },
    [202] = { name = "Engineering", icon = "Interface\\Icons\\Trade_Engineering" },
    [182] = { name = "Herbalism", icon = "Interface\\Icons\\Trade_Herbalism" },
    [165] = { name = "Leatherworking", icon = "Interface\\Icons\\INV_Misc_ArmorKit_17" },
    [186] = { name = "Mining", icon = "Interface\\Icons\\Trade_Mining" },
    [393] = { name = "Skinning", icon = "Interface\\Icons\\INV_Misc_Pelt_Wolf_01" },
    [197] = { name = "Tailoring", icon = "Interface\\Icons\\Trade_Tailoring" },
    [185] = { name = "Cooking", icon = "Interface\\Icons\\INV_Misc_Food_15" },
    [129] = { name = "First Aid", icon = "Interface\\Icons\\Spell_Holy_SealOfSacrifice" },
    [356] = { name = "Fishing", icon = "Interface\\Icons\\Trade_Fishing" },
    [9787] = { name = "Weaponsmithing", icon = "Interface\\Icons\\INV_Sword_25" },
    [9788] = { name = "Armorsmithing", icon = "Interface\\Icons\\INV_Chest_Plate04" },
}

function ns.ProfessionName(skill)
    local mine = player.professions[skill]
    return (mine and mine.name) or (ns.PROFESSIONS[skill] and ns.PROFESSIONS[skill].name) or ("profession " .. tostring(skill))
end

function ns.ProfessionIcon(skill)
    local mine = player.professions[skill]
    return (mine and mine.icon) or (ns.PROFESSIONS[skill] and ns.PROFESSIONS[skill].icon) or "Interface\\Icons\\INV_Pick_02"
end

function ns.HasProfession(skill)
    return player.skills[skill] ~= nil
end

-- "Alchemy 150", or "Alchemy" when the quest needs no particular skill level.
function ns.SkillText(q)
    local name = ns.ProfessionName(q.sk)
    return q.sl and (name .. " " .. q.sl) or name
end

local function PageSkill(page)
    return tonumber(string.match(page, "^prof:(%d+)$"))
end

function ns.IsSpecialPage(page)
    return type(page) == "string"
end

function ns.SpecialPageName(page)
    if page == "class" then
        local className = UnitClass("player")
        return (className or "Class") .. " quests"
    end
    local skill = PageSkill(page)
    return skill and ns.ProfessionName(skill) or page
end

-- The quests on a Class or profession page. Professions you don't have are
-- included (as locked quests) only when "Show professions you don't have" is on.
local function SpecialPageQuests(page)
    local source, ignoreSkill
    if page == "class" then
        source = classQuests
    else
        local skill = PageSkill(page)
        source = skill and professionQuests[skill] or {}
        ignoreSkill = skill and not ns.HasProfession(skill) and ns.GetSetting("showAllProfessions")
    end
    return source, ignoreSkill
end

-- Quests on a zone list page (a zone, an instance, or the Class or a profession
-- page) that this character can do. Repeatable quests are left out when "Show
-- repeatable quests" is off.
function ns.GetZoneQuests(zoneID)
    if not zoneQuests then
        BuildZoneIndex()
    end
    local source, ignoreSkill
    if ns.IsSpecialPage(zoneID) then
        source, ignoreSkill = SpecialPageQuests(zoneID)
    else
        source = zoneQuests[zoneID] or {}
    end
    local showRepeatable = ns.GetSetting("showRepeatable")
    local list = {}
    for _, id in ipairs(source) do
        if ns.IsEligible(id, ignoreSkill) and (showRepeatable or not ns.IsRepeatable(id)) then
            table.insert(list, id)
        end
    end
    return list
end

-- The Class and Professions groups at the top of the zone list:
-- { { name = "Class", pages = { "class" } }, { name = "Professions", pages = { "prof:171", ... } } },
-- leaving out any page with no quests for you.
function ns.GetSpecialGroups()
    if not zoneQuests then
        BuildZoneIndex()
    end
    local groups = {}
    if #ns.GetZoneQuests("class") > 0 then
        table.insert(groups, { name = "Class", pages = { "class" } })
    end
    local pages = {}
    for skill in pairs(professionQuests) do
        if #ns.GetZoneQuests("prof:" .. skill) > 0 then
            table.insert(pages, "prof:" .. skill)
        end
    end
    table.sort(pages, function(a, b)
        local ha, hb = ns.HasProfession(PageSkill(a)), ns.HasProfession(PageSkill(b))
        if ha ~= hb then
            return ha -- yours first, then the ones you don't have
        end
        return ns.SpecialPageName(a) < ns.SpecialPageName(b)
    end)
    if #pages > 0 then
        table.insert(groups, { name = "Professions", pages = pages })
    end
    return groups
end

-- Does a quest count towards "x / y" progress? Missed breadcrumbs don't count
-- against you, and repeatable quests don't count at all.
function ns.CountsForProgress(id, status)
    return status ~= ns.STATUS.MISSED and not ns.IsRepeatable(id)
end

-- done, total, repeatables for any list of quest IDs. Repeatable quests sit
-- outside done/total (they're never "done"), so they're counted separately.
function ns.CountProgress(ids)
    local done, total, repeatables = 0, 0, 0
    for _, id in ipairs(ids) do
        local status = ns.GetStatus(id)
        if ns.IsRepeatable(id) then
            repeatables = repeatables + 1
        elseif ns.CountsForProgress(id, status) then
            total = total + 1
            if status == ns.STATUS.DONE then
                done = done + 1
            end
        end
    end
    return done, total, repeatables
end

-- done, total, repeatables for a zone.
function ns.GetZoneProgress(zoneID)
    return ns.CountProgress(ns.GetZoneQuests(zoneID))
end

-- Quests that list `id` as a prerequisite (built once, on first use).
local followOns
function ns.GetFollowOns(id)
    if not followOns then
        followOns = {}
        for qid, q in pairs(ns.Quests) do
            for _, pre in ipairs(q.pre or {}) do
                followOns[pre] = followOns[pre] or {}
                table.insert(followOns[pre], qid)
            end
        end
        for _, list in pairs(followOns) do
            table.sort(list)
        end
    end
    return followOns[id] or {}
end

-- Zones (and dungeon/raid pages) that have at least one quest for this character,
-- with their continent.
function ns.GetZones()
    if not zoneQuests then
        BuildZoneIndex()
    end
    local zones = {}
    for zoneID in pairs(zoneQuests) do
        if #ns.GetZoneQuests(zoneID) > 0 then
            table.insert(zones, {
                id = zoneID,
                continent = ns.ZoneContinents[zoneID] or 0,
                instance = ns.GetInstanceKind(zoneID), -- "dungeon", "raid" or nil
            })
        end
    end
    return zones
end

-- Groups a zone's quests into storylines: quests joined by prerequisite or
-- breadcrumb links form one storyline. Quests with no links go into `others`.
-- Each storyline has nodes laid out in columns: { id, col, row }.
function ns.BuildStorylines(zoneID)
    local ids = ns.GetZoneQuests(zoneID)
    local inZone = {}
    for _, id in ipairs(ids) do
        inZone[id] = true
    end

    -- Links inside the zone: parents[child] = { parent, ... }
    local parents, children = {}, {}
    local function Link(parent, child)
        if parent == child or not inZone[parent] or not inZone[child] then
            return
        end
        parents[child] = parents[child] or {}
        children[parent] = children[parent] or {}
        table.insert(parents[child], parent)
        table.insert(children[parent], child)
    end
    for _, id in ipairs(ids) do
        local q = ns.Quests[id]
        for _, pre in ipairs(q.pre or {}) do
            Link(pre, id)
        end
        if q.bc then
            for _, nextID in ipairs(q.nx or {}) do
                Link(id, nextID)
            end
        end
    end

    -- Connected groups (union-find).
    local root = {}
    local function Find(x)
        while root[x] and root[x] ~= x do
            root[x] = root[root[x]] or root[x]
            x = root[x]
        end
        return x
    end
    for _, id in ipairs(ids) do
        root[id] = id
    end
    for child, list in pairs(parents) do
        for _, parent in ipairs(list) do
            local a, b = Find(child), Find(parent)
            if a ~= b then
                root[a] = b
            end
        end
    end
    local groups = {}
    for _, id in ipairs(ids) do
        local key = Find(id)
        groups[key] = groups[key] or {}
        table.insert(groups[key], id)
    end

    -- Column = longest path from a quest with no parent (cycles are cut).
    local depth = {}
    local function Depth(id, visiting)
        if depth[id] then
            return depth[id]
        end
        if visiting[id] then
            return 0
        end
        visiting[id] = true
        local d = 0
        for _, parent in ipairs(parents[id] or {}) do
            d = math.max(d, Depth(parent, visiting) + 1)
        end
        visiting[id] = nil
        depth[id] = d
        return d
    end

    local function Level(id)
        return ns.Quests[id].l or 1
    end

    local storylines, others = {}, {}
    for _, members in pairs(groups) do
        if #members == 1 then
            table.insert(others, members[1])
        else
            local columns, maxCol = {}, 0
            for _, id in ipairs(members) do
                local col = Depth(id, {})
                columns[col] = columns[col] or {}
                table.insert(columns[col], id)
                maxCol = math.max(maxCol, col)
            end
            -- Rows: order each column by where its parents sit, then level, then ID.
            local rowOf, nodes, maxRow = {}, {}, 0
            for col = 0, maxCol do
                local list = columns[col] or {}
                local weight = {}
                for _, id in ipairs(list) do
                    local sum, n = 0, 0
                    for _, parent in ipairs(parents[id] or {}) do
                        if rowOf[parent] then
                            sum, n = sum + rowOf[parent], n + 1
                        end
                    end
                    weight[id] = (n > 0) and (sum / n) or 0
                end
                table.sort(list, function(a, b)
                    if weight[a] ~= weight[b] then
                        return weight[a] < weight[b]
                    end
                    if Level(a) ~= Level(b) then
                        return Level(a) < Level(b)
                    end
                    return a < b
                end)
                for row, id in ipairs(list) do
                    rowOf[id] = row - 1
                    maxRow = math.max(maxRow, row - 1)
                    table.insert(nodes, { id = id, col = col, row = row - 1 })
                end
            end
            -- The storyline is named after its first quest.
            local first = columns[0] and columns[0][1] or members[1]
            local minLevel = math.huge
            for _, id in ipairs(members) do
                minLevel = math.min(minLevel, Level(id))
            end
            table.insert(storylines, {
                first = first,
                nodes = nodes,
                parents = parents,
                cols = maxCol + 1,
                rows = maxRow + 1,
                minLevel = minLevel,
            })
        end
    end

    table.sort(storylines, function(a, b)
        if a.minLevel ~= b.minLevel then
            return a.minLevel < b.minLevel
        end
        return a.first < b.first
    end)
    table.sort(others, function(a, b)
        if Level(a) ~= Level(b) then
            return Level(a) < Level(b)
        end
        return a < b
    end)
    return storylines, others
end

-- What to do next in a storyline. Returns kind, questID, detail:
--   "available", id        - pick this up next
--   "active", id           - already in your log
--   "level", id, level     - next quest needs a higher level
--   "reputation", id, text - next quest needs more reputation ("Friendly with Darnassus")
--   "blocked", id, preID   - waiting on a quest outside this storyline
--   "complete"             - every quest done
-- Repeatable quests are skipped, unless the storyline has nothing else left.
function ns.GetNextStep(storyline)
    local S = ns.STATUS
    local active, levelID, blockedID
    local nodes, repeatables = {}, {}
    for _, node in ipairs(storyline.nodes) do
        table.insert(ns.IsRepeatable(node.id) and repeatables or nodes, node)
    end
    local onlyRepeatables = #nodes == 0
    if onlyRepeatables then
        nodes = repeatables
    end
    -- nodes are in column order, so earlier quests in the story come first
    for _, node in ipairs(nodes) do
        local status = ns.GetStatus(node.id)
        if status == S.AVAILABLE or status == S.REPEATABLE then
            return "available", node.id
        elseif status == S.ACTIVE and not active then
            active = node.id
        elseif status == S.LEVEL and not levelID then
            levelID = node.id
        elseif status == S.BLOCKED and not blockedID then
            blockedID = node.id
        end
    end
    if active then
        return "active", active
    end
    if levelID then
        if ns.GetLockReason(levelID) == "minrep" then
            return "reputation", levelID, ns.ReputationText(ns.Quests[levelID].mr)
        end
        return "level", levelID, ns.Quests[levelID].l
    end
    if blockedID then
        return "blocked", blockedID, ns.MissingPrereq(blockedID)
    end
    return "complete"
end

-- ============================================================================
-- Waypoints
-- ============================================================================

-- Sets the game's own waypoint on where a quest starts and opens the map there.
function ns.ShowQuestStart(id)
    local q = ns.Quests[id]
    if not q or not q.m then
        ns.Print(string.format("No start location known for %s.", ns.GetQuestNameOrID(id)))
        return false
    end
    if C_Map.CanSetUserWaypointOnMap and not C_Map.CanSetUserWaypointOnMap(q.m) then
        ns.Print(string.format("Can't place a waypoint on %s.", ns.GetMapName(q.m)))
        return false
    end
    local point = UiMapPoint.CreateFromCoordinates(q.m, q.x / 100, q.y / 100)
    C_Map.SetUserWaypoint(point)
    if C_SuperTrack and C_SuperTrack.SetSuperTrackedUserWaypoint then
        C_SuperTrack.SetSuperTrackedUserWaypoint(true)
    end
    if ns.GetSetting("openMapOnWaypoint") and not InCombatLockdown() then
        if type(OpenWorldMap) == "function" then
            pcall(OpenWorldMap, q.m)
        elseif WorldMapFrame then
            pcall(ShowUIPanel, WorldMapFrame)
            pcall(WorldMapFrame.SetMapID, WorldMapFrame, q.m)
        end
    end
    ns.Print(string.format("Waypoint set: %s (%s %.1f, %.1f).", ns.GetQuestNameOrID(id), ns.GetMapName(q.m), q.x, q.y))
    return true
end
