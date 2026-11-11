-- Attunements (issue #16): the steps that unlock a dungeon or raid, as one page
-- each under "Attunements" in the zone list, even when they cross zones.
-- Hand-written: AllTheThings doesn't model attunements. Only attunements whose
-- quests are in WoW Forever's data (Data/Quests.lua) are listed; check new ones
-- in game first. Molten Core's (7848) and Naxxramas' (9121-9123) quests aren't
-- in it, and neither is Blackwing Lair's raid page (Blackhand's Command, 7761, is).
--
-- id: the page is "att:<id>"; name; instance: its dungeon or raid page (for the
-- icon and level range).
-- steps, in order:
--   { quest = ID }            done when completed. Quests for the other faction
--                             are left out the same way as everywhere else, so
--                             both factions' chains can be listed.
--   { item = ID }             done while you have it (bags or bank): the key.
--   { level = N }             done at that level.
--   { rep = { factionID, standing } }  done at that standing (3000 Friendly,
--                             9000 Honored, 21000 Revered, 42000 Exalted).
local _, ns = ...
ns.Attunements = {
    {
        id = "onyxia", name = "Onyxia's Lair", instance = 248,
        steps = {
            -- Alliance: Burning Steppes, Blackrock Depths, Stormwind, then Blackrock Spire.
            { quest = 4182 }, { quest = 4183 }, { quest = 4184 }, { quest = 4185 }, { quest = 4186 },
            { quest = 4223 }, { quest = 4224 }, { quest = 4241 }, { quest = 4242 }, { quest = 4264 },
            { quest = 4282 }, { quest = 4322 }, { quest = 6402 }, { quest = 6403 }, { quest = 6501 },
            { quest = 6502 },
            -- Horde: from Warlord's Command (it drops in Lower Blackrock Spire) to Rexxar.
            { quest = 4903 }, { quest = 4941 }, { quest = 4974 }, { quest = 6566 }, { quest = 6567 },
            { quest = 6568 }, { quest = 6569 }, { quest = 6570 }, { quest = 6582 }, { quest = 6583 },
            { quest = 6584 }, { quest = 6585 }, { quest = 6601 }, { quest = 6602 },
            { item = 16309 }, -- Drakefire Amulet
        },
    },
    {
        id = "ubrs", name = "Upper Blackrock Spire", instance = 250,
        steps = {
            { quest = 4742 }, { quest = 4743 },
            { item = 12344 }, -- Seal of Ascension
        },
    },
    {
        id = "scholomance", name = "Scholomance", instance = 476,
        steps = {
            -- Alliance, from Chillwind Camp.
            { quest = 5066 }, { quest = 5090 }, { quest = 5091 }, { quest = 5092 }, { quest = 5097 },
            { quest = 5533 }, { quest = 5537 }, { quest = 5538 }, { quest = 5801 }, { quest = 5803 },
            { quest = 5505 },
            -- Horde, from the Bulwark.
            { quest = 5093 }, { quest = 5094 }, { quest = 5095 }, { quest = 5096 }, { quest = 5098 },
            { quest = 838 }, { quest = 964 }, { quest = 5514 }, { quest = 5802 }, { quest = 5804 },
            { quest = 5511 },
            { item = 13704 }, -- Skeleton Key
        },
    },
    {
        id = "shadowforge", name = "Shadowforge City", instance = 242,
        steps = {
            { quest = 3801 }, { quest = 3802 },
            { item = 11000 }, -- Shadowforge Key
        },
    },
}
