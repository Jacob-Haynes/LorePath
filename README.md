# LorePath

"Hold your own hand"

**LorePath** is a lightweight WoW Forever addon that maps *your* story. For every zone it draws each questline as a storyline graph, in the style of Attuned's attunement paths. It shows what you've done, what you've missed, and where the next part of each story starts.

It's not a quest helper. There are no map pins and no objective tracking, so it sits happily alongside the default quest UI.

> **Status: prototype (0.1.0).** It covers outdoor zone, dungeon and raid quests. Lore comes later.

---

## What it shows

- **Zone list:** every zone with quests your character can do, grouped by continent, each with a progress count (for example *Elwynn Forest 12/75*). Dungeons and raids get their own pages, under **Dungeons** and **Raids** headings. Inside an instance, the window opens on its page.
- **Storylines:** each zone's quest chains, drawn left to right from the first quest to the last. Lines join each quest to the ones it unlocks.
- **Other quests:** standalone quests with no chain, listed under each zone's storylines.
- **Only your quests:** quests for another faction, race or class are left out. Profession quests show only if you have that profession.
- **Quest colours:**

  | Colour | Meaning |
  | :--- | :--- |
  | Green | Completed |
  | Gold | In your quest log |
  | Blue | Available now |
  | Orange | Needs a higher level |
  | Grey | Needs an earlier quest first |
  | Dark grey | A breadcrumb you went past |

- **Tooltips:** hover a quest to see its level, what it needs, what comes before and after it, where it starts, and its rewards.
- **Quest details:** click a quest to open a panel beside the window with its requirements, where it starts (and who gives it), its objectives and text, its rewards (items, plus gold and XP once you've accepted it or seen it at the quest giver) and the quests before and after it. Click the same quest again to close the panel.
- **Waypoints:** Ctrl+click a quest, or use **Show on map** in its details, to set the game's own waypoint where it starts and open the map there. Each storyline also has a **Show on map** button for its next quest, and clicking **Next** or **First finish** in a storyline's header jumps to that quest.

### Controls

| Action | How |
| :--- | :--- |
| Open or close | Left-click the minimap button, `/lp`, the addons menu by the minimap, or a key binding (*Options → Key Bindings → AddOns → LorePath*) |
| Open on your current zone | `/lp here` |
| Settings | Right-click the minimap button, the **Settings** button in the window, `/lp config`, or *Options → AddOns → LorePath* |
| Show or hide the minimap button | `/lp minimap`, or the settings page |
| Move the minimap button | Drag it around the minimap |
| Scroll | Mouse wheel, or Shift + wheel to scroll sideways |
| Pan around a large graph | Drag with the left mouse button |
| Close | Escape |

### Settings

| Option | Default | What it does |
| :--- | :--- | :--- |
| Show minimap button | On | Left-click opens LorePath, right-click opens settings. |
| Open on the zone you're in | On | Each time the window opens, it jumps to your current zone. Off: it reopens on the last zone you looked at. |
| Hide finished storylines | Off | Leaves out storylines where every quest is done. |
| Show standalone quests | On | Lists quests that aren't part of a chain under each zone's storylines. |
| Show quest levels on tiles | On | Shows each quest's minimum level on its tile. |
| Open the map when setting a waypoint | On | Opens the world map at the quest's start when you set a waypoint. |
| Window size | 100% | Scales the window from 60% to 140%. |

Settings are saved per account in `LorePathDB`. The settings page also has **Reset to defaults**.

---

## Where the data comes from

| Data | Source |
| :--- | :--- |
| Which quests exist, their chains, level, faction/race/class, start location, rewards | [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT), extracted into `Data/Quests.lua` |
| What you've completed, what's in your log, your level, race, class, faction, professions | The game client, live |
| Quest, zone and item names | The game client, in your language |
| Quest text (objectives, description, closing text) and gold/XP rewards | Saved from the game as you play: when a quest giver shows a quest, when you accept it, at the turn-in screen, and everything in your log at login. Kept per account in `LorePathDB` |
| Quest text for quests you haven't seen since installing LorePath | [pfQuest](https://github.com/shagu/pfQuest)'s English quest database (MIT, originally from VMaNGOS), extracted into `Data/QuestText.lua`. It covers vanilla quests only, not WoW Forever's own, and the game's text replaces it once you see the quest |

Gaps in AllTheThings' Forever data show up in LorePath too. Report missing or wrong quests to AllTheThings so everyone benefits.

### Updating the quest data

```bash
pip install lupa
git clone --depth 1 --filter=blob:none --sparse https://github.com/ATTWoWAddon/AllTheThings.git att
(cd att && git sparse-checkout set db/Camelot)
python3 tools/extract_att.py att
```

`tools/extract_att.py` loads AllTheThings' Forever zone data in a sandboxed Lua runtime, then writes the quest records LorePath needs. It skips repeatable quests, quests AllTheThings marks as unavailable, and quests removed from the game. The header of `Data/Quests.lua` records the AllTheThings commit the data came from.

To see what changed, compare against the committed file:

```bash
git show HEAD:Data/Quests.lua > /tmp/Quests.old.lua
python3 tools/diff_quests.py /tmp/Quests.old.lua Data/Quests.lua
```

The [Sync quest data from AllTheThings](.github/workflows/sync-att-data.yml) workflow does this every Monday (or on demand from the Actions tab). If the quest data changed, it opens or updates a PR from the `data/att-sync` branch with the summary. It fails instead if the quest count drops by more than 10%, a zone disappears, the data doesn't load, or the tests fail. Merging and releasing stay manual.

`Data/QuestText.lua` (the bundled vanilla quest text) is a one-off import: vanilla quest text doesn't change, so it isn't part of the weekly sync. `python3 tools/extract_pfquest.py` rebuilds it if ever needed, for example after new vanilla quests appear in `Data/Quests.lua`.

### Adding players' quest text

LorePath saves the quest text each player sees (with their name swapped for `$N`). To add what someone has collected to `Data/CommunityText.lua`, so everyone gets it in the next release, take their saved file from `WTF/Account/<account>/SavedVariables/LorePath.lua` (or your own) and run:

```bash
python3 tools/merge_quest_text.py --dry-run path/to/LorePath.lua   # see what it would add
python3 tools/merge_quest_text.py path/to/LorePath.lua
```

It only adds text for quests LorePath knows, never overwrites existing community text (unless `--replace`), strips character names, colour codes and links, skips text the bundled vanilla text already has, and loads each file in a sandbox with no Lua libraries. Review the diff before committing.

### Tests

```bash
python3 tools/test/run_tests.py
```

This runs the addon's Lua against a fake WoW API with the real quest data, as a Human Warrior and an Orc Warrior. It checks eligibility, quest statuses, storyline building, waypoints, the minimap button, every setting, and that the window, settings page and tooltips build without errors. It can't check how things look in game.

---

## Installing

1. Download the latest release zip, or clone this repository.
2. Copy the `LorePath` folder into WoW Forever's `Interface/AddOns` folder. To find it, in the Battle.net app, pick WoW Forever, click the gear icon, choose **Show in Explorer** (**Show in Finder** on macOS), and open the Forever folder.
3. Start the game (or `/reload`), and type `/lp`.

## Releasing

Tagged pushes (`v*`) build the addon with [BigWigsMods/packager](https://github.com/BigWigsMods/packager) and attach it to a GitHub Release. The `tools` folder and this README are left out of the package. It also uploads to CurseForge (project 1793930, set by `## X-Curse-Project-ID` in `LorePath.toc`) using the `CF_API_KEY` repository secret. Tags containing "beta" or "alpha" upload as beta or alpha files.

## Licence

LorePath is MIT-licensed. The quest data in `Data/Quests.lua` is derived from AllTheThings, which is also MIT-licensed; its licence is included in `Data/AllTheThings-LICENSE.txt`. The bundled quest text in `Data/QuestText.lua` comes from pfQuest (MIT, licence in `Data/pfQuest-LICENSE.txt`), which took it from the VMaNGOS project; the quest text itself is Blizzard's.
