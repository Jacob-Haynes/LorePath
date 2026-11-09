# Chronicler

**Chronicler** is a lightweight WoW Forever addon that maps *your* story. For every zone it draws each questline as a storyline graph, in the style of Attuned's attunement paths. It shows what you've done, what you've missed, and where the next part of each story starts.

It's not a quest helper. There are no map pins and no objective tracking, so it sits happily alongside the default quest UI.

> **Status: prototype (0.1.0).** It covers outdoor zone quests only. Dungeon quests, lore and settings come later.

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
| Open or close | `/chron`, or a key binding (*Options → Key Bindings → AddOns → Chronicler*) |
| Open on your current zone | `/chron here` |
| Scroll | Mouse wheel, or Shift + wheel to scroll sideways |
| Pan around a large graph | Drag with the left mouse button |
| Close | Escape |

---

## Where the data comes from

| Data | Source |
| :--- | :--- |
| Which quests exist, their chains, level, faction/race/class, start location, rewards | [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT), extracted into `Data/Quests.lua` |
| What you've completed, what's in your log, your level, race, class, faction, professions | The game client, live |
| Quest, zone and item names | The game client, in your language |

Gaps in AllTheThings' Forever data show up in Chronicler too. Report missing or wrong quests to AllTheThings so everyone benefits.

### Updating the quest data

```bash
pip install lupa
git clone --depth 1 --filter=blob:none --sparse https://github.com/ATTWoWAddon/AllTheThings.git att
(cd att && git sparse-checkout set db/Camelot)
python3 tools/extract_att.py att
```

`tools/extract_att.py` loads AllTheThings' Forever zone data in a sandboxed Lua runtime, then writes the quest records Chronicler needs. It skips repeatable quests, quests AllTheThings marks as unavailable, and quests removed from the game.

### Tests

```bash
python3 tools/test/run_tests.py
```

This runs the addon's Lua against a fake WoW API with the real quest data, as a Human Warrior and an Orc Warrior. It checks eligibility, quest statuses, storyline building, waypoints, and that the window and tooltips render without errors. It can't check how things look in game.

---

## Installing

1. Download the latest release zip, or clone this repository.
2. Copy the `Chronicler` folder into WoW Forever's `Interface/AddOns` folder. To find it, in the Battle.net app, pick WoW Forever, click the gear icon, choose **Show in Explorer** (**Show in Finder** on macOS), and open the Forever folder.
3. Start the game (or `/reload`), and type `/chron`.

## Releasing

Tagged pushes (`v*`) build the addon with [BigWigsMods/packager](https://github.com/BigWigsMods/packager) and attach it to a GitHub Release. The `tools` folder and this README are left out of the package. CurseForge upload needs a `## X-Curse-Project-ID` in `Chronicler.toc` and a `CF_API_KEY` repository secret.

## Licence

Chronicler is MIT-licensed. The quest data in `Data/Quests.lua` is derived from AllTheThings, which is also MIT-licensed; its licence is included in `Data/AllTheThings-LICENSE.txt`.
