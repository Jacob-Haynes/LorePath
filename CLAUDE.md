# LorePath: notes for working on it

The README covers what LorePath does, where its data comes from, and how to update data, test and release. This file holds the things the README doesn't: facts about the WoW Forever client and the data sources, learned in game or the hard way, and how changes are made here.

## WoW Forever client facts

All checked in game. The client is mainline-based, but don't assume retail behaviour without checking.

- **Quest log:** the modern one beside the world map. `QuestMapFrame.DetailsFrame` and `QuestMapFrame_OpenToQuestDetails` exist; `QuestLogFrame` is nil, so classic quest-log code paths never run.
- **Selected quest:** `C_QuestLog.GetSelectedQuest` works.
- **Professions:** `GetProfessions` / `GetProfessionInfo` return the skill line (7th value) and rank.
- **Map pins:** `WorldMapFrame:AddDataProvider` and `MapCanvasDataProviderMixin` exist (issue #11).
- **Quest versions:** finishing one version of a quest (for example Call of Earth in Zephras Isle) marks **every** version completed, and sometimes the first step of another version's chain too. So "completed" can't pick which version a character did; `OneVersionEach` in `Core.lua` falls back to the race's home area.
- **Level ranges:** the Looking for Group activities (`C_LFGList.GetActivityInfoTable`: `minLevelSuggestion`, `maxLevelSuggestion`) have real ranges for zones, dungeons and battlegrounds. The Dungeon Finder (`GetLFGDungeonInfo`) gives each dungeon a single level, so don't use it for ranges. Scarlet Monastery's wings are separate activities ("Scarlet Monastery - Graveyard").
- **WoW Forever's own races:** race 95 (Alliance) and 96 (Horde), both starting on Zephras Isle (map 2521).

## Data source quirks

- **AllTheThings** (`tools/extract_att.py`):
  - `ResolveQuestData({aqd = Alliance, hqd = Horde, shared})` is one quest with per-faction fields; it's extracted into `fv`.
  - `qss` is the item that starts a quest (`si`); `crs` lists creatures, but ATT rarely says where creatures are.
  - A quest with no recorded giver isn't necessarily picked up inside an instance; only mark `di` when ATT names a giver.
  - Instance wings are headers with their own `lvl`; their names are in `LocalizationDB.lua`.
  - `u=1` (never implemented) also marks hidden steps of real chains: A Quick Craft (95818) needs 95817, `u=1`, after 95816. ATT often gives such a chain no faction (`r`); only the vendor (`n(..., {r=2})`) selling its start item says whose it is. `settle_chains` in the extractor fills both in.
  - ATT files some quests under an instance they aren't given in (Quel'Serrar is under Onyxia's Lair, given in Dire Maul).
  - Places that aren't zones are headers straight under a continent, with the maps they span: Timbermaw Hold is `h(-388, {maps = {1448, 1452}})` under Kalimdor. Their quests go in the zone they start in, if it's one of those maps, else the first; without that they'd land on the continent's page.
- **pfQuest** (`tools/extract_pfquest.py`, `tools/extract_quest_starts.py`): creatures and objects are placed by the game's zone **area** IDs, not map IDs; `AREA_TO_MAP` converts them. A creature can spawn both outdoors and in an instance (Blackfathom Tide Priestess), so a dungeon quest's item source is placed in the dungeon.
- **Regenerating data:** run the extractor against the ATT commit named in `Data/Quests.lua`'s header unless you mean to update the data too, so a feature's diff contains only its own change. `tools/diff_quests.py --check` summarises what changed.

## How changes are made

- **Branches and PRs:** each change on its own branch (and worktree), then a PR into `main`. Open and merge PRs only when asked. Commit messages and PRs say `Refs #N`, never `Closes`: issues are closed by hand once the change is seen working in game.
- **Tests:** `python3 tools/test/run_tests.py` must pass before committing. Add checks for every change; the harness (`tools/test/harness.lua`) fakes the WoW API and records textures, colours and chat output.
- **Changelog:** add a line under `## Unreleased` in `CHANGELOG.md` with each user-visible change.
- **Releases:** prepare the version bump (`LorePath.toc`) and changelog heading uncommitted, for review; commit, push and tag only when asked. Tags with "beta" publish as CurseForge betas; others as full releases.
- **Slash commands:** only `/lp`, `/lp config` and `/lp share`. Don't add commands; anything a player needs gets a button or a setting, and debugging aids stay out of the shipped addon.
- **CurseForge page:** `media/curseforge-description.md` isn't uploaded automatically; when it changes, it's pasted into the project page by hand.
- **English only:** LorePath supports English clients; data files carry English names.
