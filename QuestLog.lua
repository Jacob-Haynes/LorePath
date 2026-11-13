-- From the game's quest log to LorePath: a LorePath button on the quest log,
-- and on the dialog a quest giver opens, that opens the quest in LorePath's
-- window and details panel. (The other way, LorePath to the quest log, is
-- ns.OpenInQuestLog in Core.lua.)

local addonName, ns = ...

local ICON = "Interface\\Icons\\INV_Misc_Book_09"

-- The quest selected in the game's quest log, or nil.
function ns.SelectedLogQuest()
    if C_QuestLog and C_QuestLog.GetSelectedQuest then
        local ok, id = pcall(C_QuestLog.GetSelectedQuest)
        if ok and type(id) == "number" and id > 0 then
            return id
        end
    end
    -- Classic-style quest log: the selection is a log index.
    if type(GetQuestLogSelection) == "function" then
        local index = GetQuestLogSelection()
        if index and index > 0 then
            if C_QuestLog and C_QuestLog.GetInfo then
                local info = C_QuestLog.GetInfo(index)
                if info and info.questID and info.questID > 0 then
                    return info.questID
                end
            end
            if type(GetQuestLogTitle) == "function" then
                local id = select(8, GetQuestLogTitle(index))
                if type(id) == "number" and id > 0 then
                    return id
                end
            end
        end
    end
    return nil
end

-- The quest a quest giver's dialog is showing (offering, asking for items, or
-- rewarding), or nil.
function ns.DialogQuest()
    if type(GetQuestID) == "function" then
        local ok, id = pcall(GetQuestID)
        if ok and type(id) == "number" and id > 0 then
            return id
        end
    end
    return nil
end

-- Opens LorePath on a quest: its zone, its storyline, and its details panel.
function ns.ShowInLorePath(id)
    if not id then
        ns.Print("Select a quest in your quest log first.")
        return false
    end
    if not ns.Quests[id] then
        ns.Print(ns.GetQuestNameOrID(id) .. " isn't in LorePath's quest data.")
        return false
    end
    if not (ns.mainFrame and ns.mainFrame:IsShown()) then
        ns.Toggle(false)
    end
    ns.FocusQuest(id)
    ns.ShowDetail(id)
    return true
end

-- A small book button that opens questFn()'s quest in LorePath.
local function MakeButton(name, questFn, parent, anchor, x, y)
    local b = CreateFrame("Button", name, parent)
    b:SetSize(24, 24)
    b:SetPoint("TOPRIGHT", anchor, "TOPRIGHT", x, y)
    b:SetFrameLevel((parent:GetFrameLevel() or 0) + 10)
    b:SetNormalTexture(ICON)
    b:SetPushedTexture(ICON)
    b:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    b:SetScript("OnClick", function()
        ns.ShowInLorePath(questFn())
    end)
    b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:AddLine("Show in LorePath", 1, 0.82, 0)
        local id = questFn()
        if id and ns.Quests[id] then
            GameTooltip:AddLine("Opens " .. ns.GetQuestNameOrID(id) .. " in its storyline, with its details.", 1, 1, 1, true)
        elseif id then
            GameTooltip:AddLine("LorePath doesn't have this quest.", 0.6, 0.6, 0.6, true)
        else
            GameTooltip:AddLine("Select a quest first.", 0.6, 0.6, 0.6, true)
        end
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", GameTooltip_Hide)
    return b
end

-- Forever's client may have the modern quest log (beside the world map,
-- QuestMapFrame) or the classic window (QuestLogFrame); the button goes on
-- whichever exists, once.
function ns.AttachQuestLogButton()
    if ns.questLogButton then
        return ns.questLogButton
    end
    local details = QuestMapFrame and QuestMapFrame.DetailsFrame
    if type(details) == "table" and details.GetObjectType then
        ns.questLogButton = MakeButton("LorePathQuestLogButton", ns.SelectedLogQuest, details, details, -6, -6)
    elseif type(QuestLogFrame) == "table" and QuestLogFrame.GetObjectType then
        ns.questLogButton = MakeButton("LorePathQuestLogButton", ns.SelectedLogQuest, QuestLogFrame, QuestLogFrame, -40, -40)
    end
    return ns.questLogButton
end

-- The same button on the dialog a quest giver opens (QuestFrame), for the
-- quest it's showing: offered, being handed in, or being rewarded. Once.
function ns.AttachQuestDialogButton()
    if ns.questDialogButton then
        return ns.questDialogButton
    end
    if type(QuestFrame) == "table" and QuestFrame.GetObjectType then
        ns.questDialogButton = MakeButton("LorePathQuestDialogButton", ns.DialogQuest, QuestFrame, QuestFrame, -8, -28)
    end
    return ns.questDialogButton
end
