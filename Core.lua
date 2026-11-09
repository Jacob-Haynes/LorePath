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
    LEVEL = "level",         -- prerequisites done, but your level (or skill) is too low
    BLOCKED = "blocked",     -- an earlier quest isn't done yet
    MISSED = "missed",       -- a breadcrumb you skipped past; it can't be taken any more
}

-- ============================================================================
-- Player
-- ============================================================================

local player = { race = 0, class = 0, faction = 0, level = 1, skills = {} }
ns.player = player

local function ReadProfessions()
    local skills = {}
    if type(GetProfessions) ~= "function" or type(GetProfessionInfo) ~= "function" then
        return skills
    end
    local indices = { pcall(GetProfessions) }
    if not indices[1] then
        return skills
    end
    -- Slots can be empty (nil) in the middle, so walk all of them rather than ipairs.
    for slot = 2, 7 do
        local index = indices[slot]
        if index then
            local okInfo, _, _, rank, _, _, _, skillLine = pcall(GetProfessionInfo, index)
            if okInfo and skillLine then
                skills[skillLine] = rank or 0
            end
        end
    end
    return skills
end

function ns.RefreshPlayer()
    local _, _, raceID = UnitRace("player")
    local _, _, classID = UnitClass("player")
    local factionTag = UnitFactionGroup("player")
    player.race = raceID or 0
    player.class = classID or 0
    player.faction = (factionTag == "Horde" and 1) or (factionTag == "Alliance" and 2) or 0
    player.level = UnitLevel("player") or 1
    player.skills = ReadProfessions()
end

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
function ns.IsEligible(id)
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
    if q.sk and player.skills[q.sk] == nil then
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
        if ns.IsDone(pre) then
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
    if ns.IsDone(id) then
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
    if ns.MissingPrereq(id) then
        return S.BLOCKED
    end
    if q and q.l and player.level < q.l then
        return S.LEVEL
    end
    if q and q.sk and q.sl and (player.skills[q.sk] or 0) < q.sl then
        return S.LEVEL
    end
    return S.AVAILABLE
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
    return ns.GetQuestName(id) or ("Quest #" .. id)
end

function ns.GetMapName(mapID)
    local info = mapID and C_Map and C_Map.GetMapInfo and C_Map.GetMapInfo(mapID)
    return info and info.name or ("Map " .. tostring(mapID))
end

-- ============================================================================
-- Zones and storylines
-- ============================================================================

local zoneQuests -- zone mapID -> list of quest IDs (built once)

local function BuildZoneIndex()
    zoneQuests = {}
    for id, q in pairs(ns.Quests) do
        local list = zoneQuests[q.z]
        if not list then
            list = {}
            zoneQuests[q.z] = list
        end
        table.insert(list, id)
    end
end

-- Quests in a zone that this character can do.
function ns.GetZoneQuests(zoneID)
    if not zoneQuests then
        BuildZoneIndex()
    end
    local list = {}
    for _, id in ipairs(zoneQuests[zoneID] or {}) do
        if ns.IsEligible(id) then
            table.insert(list, id)
        end
    end
    return list
end

-- done, total for a zone. Missed breadcrumbs don't count against you.
function ns.GetZoneProgress(zoneID)
    local done, total = 0, 0
    for _, id in ipairs(ns.GetZoneQuests(zoneID)) do
        local status = ns.GetStatus(id)
        if status ~= ns.STATUS.MISSED then
            total = total + 1
            if status == ns.STATUS.DONE then
                done = done + 1
            end
        end
    end
    return done, total
end

-- Zones that have at least one quest for this character, with their continent.
function ns.GetZones()
    if not zoneQuests then
        BuildZoneIndex()
    end
    local zones = {}
    for zoneID in pairs(zoneQuests) do
        if #ns.GetZoneQuests(zoneID) > 0 then
            table.insert(zones, { id = zoneID, continent = ns.ZoneContinents[zoneID] or 0 })
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
--   "blocked", id, preID   - waiting on a quest outside this storyline
--   "complete"             - every quest done
function ns.GetNextStep(storyline)
    local S = ns.STATUS
    local active, levelID, blockedID
    -- nodes are in column order, so earlier quests in the story come first
    for _, node in ipairs(storyline.nodes) do
        local status = ns.GetStatus(node.id)
        if status == S.AVAILABLE then
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
