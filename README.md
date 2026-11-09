# LorePath

**LorePath** is a lightweight WoW Forever addon that maps *your* story. For every zone it draws each questline as a storyline graph, in the style of Attuned's attunement paths. It shows what you've done, what you've missed, and where the next part of each story starts.

It's not a quest helper. There are no map pins and no objective tracking, so it sits happily alongside the default quest UI.

> **Status: prototype (0.1.0).** It covers outdoor zone quests only. Dungeon quests and lore come later.

---

## What it shows

- **Zone list:** every zone with quests your character can do, grouped by continent, each with a progress count (for example *Elwynn Forest 12/75*).
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
- **Waypoints:** click any quest to set the game's own waypoint on where it starts and open the map there. Each storyline also has a **Show next quest** button that finds the next quest you can pick up.

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
| Open the map when setting a waypoint | On | Opens the world map at the quest's start when you click a quest. |
| Window size | 100% | Scales the window from 60% to 140%. |

Settings are saved per account in `LorePathDB`. The settings page also has **Reset to defaults**.

---

## Where the data comes from

| Data | Source |
| :--- | :--- |
| Which quests exist, their chains, level, faction/race/class, start location, rewards | [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT), extracted into `Data/Quests.lua` |
| What you've completed, what's in your log, your level, race, class, faction, professions | The game client, live |
| Quest, zone and item names | The game client, in your language |

Gaps in AllTheThings' Forever data show up in LorePath too. Report missing or wrong quests to AllTheThings so everyone benefits.

### Updating the quest data

```bash
pip install lupa
git clone --depth 1 --filter=blob:none --sparse https://github.com/ATTWoWAddon/AllTheThings.git att
(cd att && git sparse-checkout set db/Camelot)
python3 tools/extract_att.py att
```

`tools/extract_att.py` loads AllTheThings' Forever zone data in a sandboxed Lua runtime, then writes the quest records LorePath needs. It skips repeatable quests, quests AllTheThings marks as unavailable, and quests removed from the game.

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

LorePath is MIT-licensed. The quest data in `Data/Quests.lua` is derived from AllTheThings, which is also MIT-licensed; its licence is included in `Data/AllTheThings-LICENSE.txt`.
