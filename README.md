# LorePath

"Hold your own hand"

**LorePath** is a lightweight WoW Forever addon that maps *your* story. For every zone, dungeon and raid it draws each questline as a storyline graph, in the style of Attune's attunement paths. It shows what you've done, what you've missed and where the next part of each story starts. Click any quest to read its story.

It's not a quest helper. There are no map pins and no objective tracking, so it sits happily alongside the default quest UI.

LorePath supports English game clients only.

> **Version 1.0.0.** Lore beyond quest text (zones, characters, a codex) is planned.

---

## What it shows

- **Class and Professions:** at the top of the zone list, **Class** gathers every quest for your class from all zones, so class chains that travel (say, from a capital city to another zone) show as one storyline. **Professions** has a page for each profession you have, with its quests. Their tooltips say which zone each quest is in. Quests your skill is too low for say what they need, for example *Needs Leatherworking 225*.
- **Zone list:** every zone with quests your character can do, grouped by continent, each with a progress count (for example *Elwynn Forest 12/75 +3*, where "+3" is repeatable quests). Dungeons, raids and battlegrounds get their own pages under **Dungeons**, **Raids** and **Battlegrounds** headings (Scarlet Monastery's Graveyard and Library wings have their own too), and inside an instance the window opens on its page. Zones, dungeons and raids show WoW Forever's suggested level range after their name, read from the game's Looking for Group list (`/lp levels` lists them all). Names are coloured by progress: grey before you start, then red, orange at 40%, WoW's gold at 80% and on towards green, turning fully green only once finished. Each zone, dungeon and raid has an icon, with a tick once you've finished it, and headings show their continent's icon. Headings collapse, and the whole list can be hidden to give the graph more room.
- **Storylines:** each page's quest chains, drawn left to right from the first quest to the last, with lines joining each quest to the ones it unlocks. Each storyline can be collapsed, and finished ones start collapsed. **Expand all** and **Collapse all** sit at the top.
- **Other quests:** standalone quests with no chain, under each page's storylines.
- **Only your quests:** quests for another faction, race or class are left out. Profession quests show only if you have that profession.
- **Quest boxes:**

  | Look | Meaning |
  | :--- | :--- |
  | Green box, ✓ | Completed |
  | Gold box, ? | In your quest log |
  | Dark box, yellow ! | Available now. The name is coloured by difficulty, as in your quest log |
  | Blue box, blue ! | Repeatable (daily and repeatable quests). Never counts toward progress |
  | Dark box, grey !, red level | Too high level, or your profession skill or reputation is too low |
  | Dimmed box, padlock | Needs an earlier quest first |
  | Dimmest box, ✗ | Skipped: a breadcrumb you went past, or a quest your reputation is now too high for |

  Class quests show your class icon, quests you pick up inside a dungeon or raid its entrance portal, and breadcrumbs a letter. The "?" button in the footer explains the level colours.
- **Tooltips:** hover a quest for its level, status, what it needs (earlier quests, reputation, skill), what comes before and after it, where it starts, its item rewards, and AllTheThings' note on it when there is one.
- **Quest details:** click a quest to open a panel beside the window, and click it again to close it. The panel shows:
  - requirements;
  - where it starts and who gives it;
  - **Good to know:** AllTheThings' note on the quest, when it has one (where an item drops, what finishing it locks you out of, and so on);
  - its objectives and description, plus progress and completion text;
  - its item rewards (Shift+click one to link it in chat, Ctrl+click to try it on);
  - the quests before and after it, as links;
  - its address on WarcraftDB, to copy, at the bottom.

  **No spoilers by default:** a quest you haven't started shows "Find what awaits you." with a **Reveal** button, instead of its objectives and story. A quest in your log shows its objectives and description, but not how it ends. A completed quest shows everything. Reveal lasts until you look at another quest. **Show spoilers** in the settings, or `/lp spoilers`, shows everything always.
- **Search:** type part of a quest's name, or its ID, in the box above the zone list. The list shows up to 50 matching quests you can do, with their zone, status and level; click one to jump to it. Escape clears the search. `/lp search <name>` opens LorePath with the search filled in.
- **Jumping around:** in a storyline's header, click **Next**, **In progress** or **First finish** to jump to that quest, even in another zone or dungeon. **Back** returns you.
- **Waypoints:** Ctrl+click a quest, or use **Show on map** (in its details, or in a storyline's header for the next quest), to set the game's own waypoint where it starts and open the map there.
- **Quest log, both ways:** for a quest you're on, **Open in quest log** in its details, or Shift+click it, opens the game's quest log at that quest. The other way, the LorePath book button on the game's quest log, or `/lp quest`, opens the selected quest in LorePath with its details.

### Controls

| Action | How |
| :--- | :--- |
| Open or close | Left-click the minimap button, `/lp`, the addons menu by the minimap, or a key binding (*Options → Key Bindings → AddOns → LorePath*) |
| Open on your current zone | `/lp here` |
| List level ranges | `/lp levels` |
| Settings | Right-click the minimap button or the addons-menu entry, the **Settings** button in the window, `/lp config` (or `/lp settings`, `/lp options`), or *Options → AddOns → LorePath* |
| Find a quest | Type in the search box above the zone list, or `/lp search <name>`; Escape clears it |
| Quest details | Click a quest; click it again to close the panel |
| Waypoint | Ctrl+click a quest, or **Show on map** |
| Open in your quest log | Shift+click a quest you're on, or **Open in quest log** in its details |
| Open a quest log quest in LorePath | The LorePath book button on the game's quest log, or `/lp quest` (`/lp quest <ID>` for any quest) |
| Collapse | Click a storyline's or heading's +/−, or **Expand all** / **Collapse all** |
| Hide the zone list | The arrow button left of the zone name |
| Show or hide repeatable quests | The **Repeatable** tick box, `/lp repeatable`, or the settings page |
| Reveal a quest's story | **Reveal** in its details; or **Show spoilers** / `/lp spoilers` for every quest |
| Show or hide the minimap button | `/lp minimap`, or the settings page |
| Share the quest text you've collected | `/lp share`, then paste the code into a [Share quest text](https://github.com/Jacob-Haynes/LorePath/issues/new/choose) issue |
| Move the window | Drag its title bar |
| Move the minimap button | Drag it around the minimap |
| Scroll | Mouse wheel, or Shift + wheel to scroll sideways |
| Pan around a large graph | Drag with the left mouse button, from anywhere on the graph, even on a quest or a storyline header |
| Close | Escape |

`/lorepath` works the same as `/lp`, and `/lp help` lists the commands and shows your version.

### Settings

| Option | Default | What it does |
| :--- | :--- | :--- |
| Show minimap button | On | Left-click opens LorePath, right-click opens settings. |
| Open on the zone you're in | On | Each time the window opens, it jumps to your current zone (or instance). Off: it reopens on the last page you looked at. |
| Hide finished storylines | Off | Leaves out storylines where every quest is done. |
| Show standalone quests | On | Lists quests that aren't part of a chain under each page's storylines. |
| Show professions you don't have | Off | Lists every profession under **Professions**, with the ones you don't have greyed out and their quests locked. |
| Show repeatable quests | On | Shows daily and repeatable quests, in blue. Same as the **Repeatable** tick box. |
| Show spoilers | Off | Shows the full story of every quest in its details. Off: quests you haven't started, and how quests in your log end, stay hidden until you press **Reveal**. |
| Show quest levels on tiles | On | Shows each quest's minimum level on its tile. Quests that are too high level always show it, in red. |
| Open the map when setting a waypoint | On | Opens the world map at the quest's start when you set a waypoint. |
| Window size | 100% | Scales the window from 60% to 140%. |

**Reset to defaults** on the settings page puts every setting back, re-opens collapsed storylines and headings, and shows the zone list again. It keeps your saved quest text.

### What LorePath saves

Everything is saved per account in `LorePathDB` (`WTF/Account/<account>/SavedVariables/LorePath.lua`):
- **Settings:** the settings above, plus where the minimap button sits and the last page you looked at.
- **Window layout:** which storylines and headings are collapsed, and whether the zone list is hidden.
- **Quest text (`questCache`):** what the game shows you, saved as you play: description, objectives, progress and completion text. Your character's name is stored as `$N`. Gold, XP and reputation rewards are saved too, but not shown yet.
- **Character names (`characters`):** your account's character names, so `/lp share` and `tools/merge_quest_text.py` can replace any that slip into quest text with `$N`.

### Sharing quest text

WoW Forever's own quests aren't in any quest database, so the only source for their story is what players see in game. LorePath saves it as you play; `/lp share` sends it to everyone:

1. Type `/lp share`. A window shows a share code (it starts with `LP1:`) holding the quest text you've saved that LorePath doesn't ship yet: titles, objectives, descriptions, progress and closing text, plus gold, XP and reputation rewards. Your character names are replaced with `$N`; nothing else about you is in it.
2. Click the code, press Ctrl+C, and paste it into a new **Share quest text** issue. A big collection comes as several codes; send each one in its own issue.
3. A check replies on the issue with what it added, and adds the text to a pull request. Once a maintainer has reviewed and merged it, the next release has it.

---

## Where the data comes from

| Data | Source |
| :--- | :--- |
| Which quests exist, their chains, level, faction/race/class, profession and reputation requirements, repeatables, start location, quest giver, item rewards, and dungeon and raid pages | [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT), extracted into `Data/Quests.lua`: 4,184 quests on 50 zone pages and 27 dungeon and raid pages |
| What you've completed, what's in your log, your level, race, class, faction, professions and reputation | The game client, live |
| Quest, zone, item, NPC and faction names | The game client, in your language |
| Quest text: description, objectives, progress and completion text | In this order:<br>1. **What you've seen:** saved from the game as you play (when a quest giver shows a quest, when you accept it, when you hand items in, at the turn-in screen, and your quest log at login).<br>2. **Community text:** `Data/CommunityText.lua`, collected by players, including WoW Forever's own quests (250 quests so far).<br>3. **The game's own quest-link tooltip:** the quest's goal and requirements, even for quests completed long ago.<br>4. **Bundled vanilla text:** [pfQuest](https://github.com/shagu/pfQuest)'s English quest database (MIT, originally from VMaNGOS), in `Data/QuestText.lua`: 3,285 vanilla quests, not WoW Forever's own. |

Missing quests, or wrong chains, levels or start points, come from AllTheThings' Forever data. Please report them to AllTheThings too, so everyone benefits. Wrong or missing quest text is LorePath's own.

### Updating the quest data

```bash
pip install lupa
git clone --depth 1 --filter=blob:none --sparse https://github.com/ATTWoWAddon/AllTheThings.git att
(cd att && git sparse-checkout set db/Camelot)
python3 tools/extract_att.py att
```

`tools/extract_att.py` loads AllTheThings' Forever zone data (`Categories/Zones.lua`) and dungeon and raid data (`Categories/Instances.lua`) in a sandboxed Lua runtime, then writes the quest records LorePath needs.
- **Kept:** repeatable quests, flagged `rp`.
- **Skipped:** quests AllTheThings marks unavailable, and quests added after or removed by Forever's build.
- **Recorded:** the header of `Data/Quests.lua` names the AllTheThings commit the data came from.

To see what changed, compare against the committed file:

```bash
git show HEAD:Data/Quests.lua > /tmp/Quests.old.lua
python3 tools/diff_quests.py /tmp/Quests.old.lua Data/Quests.lua
```

The [Sync quest data from AllTheThings](.github/workflows/sync-att-data.yml) workflow does this every Monday, or on demand from the Actions tab:
- **If the quest data changed,** it opens or updates a PR from the `data/att-sync` branch with the summary.
- **It fails instead** if the quest count drops by more than 10%, a zone disappears, the data doesn't load, or the tests fail.
- **Merging and releasing stay manual.**
- **Repository setting:** opening the PR needs *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests* turned on.

`Data/QuestText.lua`, the bundled vanilla text, is a one-off import and isn't part of the weekly sync, because vanilla quest text doesn't change. `python3 tools/extract_pfquest.py` rebuilds it if ever needed, for example after new vanilla quests appear in `Data/Quests.lua`.

### Adding players' quest text

Shared codes arrive through the **Share quest text** issue form. The `Add shared quest text` workflow (`.github/workflows/community-text.yml`) runs on each one:
- it merges the code into `Data/CommunityText.lua` with `tools/merge_quest_text.py --replace`, so later submissions replace earlier wording for the same quest (wording usually only changes when the game does);
- runs the tests, commits to the `data/community-text` branch, and opens or updates one PR from it;
- replies on the issue with what was added.

Review the PR's text before merging. The workflow needs two things set up once:
- a `quest-text` label, which the issue form applies: `gh label create quest-text --description "Quest text shared with /lp share"`;
- **Settings > Actions > General > Allow GitHub Actions to create and approve pull requests**, the same setting the AllTheThings sync needs.

To add the quest text someone has collected to `Data/CommunityText.lua`, so everyone gets it in the next release, take their saved file (`WTF/Account/<account>/SavedVariables/LorePath.lua`), or your own, and run:

```bash
python3 tools/merge_quest_text.py --dry-run path/to/LorePath.lua   # see what it would add
python3 tools/merge_quest_text.py path/to/LorePath.lua
```

What it does:
- **Scope:** only adds text for quests LorePath knows, and never overwrites existing community text unless you pass `--replace`.
- **Clean-up:** strips character names (to `$N`), colour codes and links, and skips text the bundled vanilla text already has.
- **Rewards:** carries saved gold, XP and reputation rewards over too.
- **Safety:** loads each file in a sandbox with no Lua libraries.

Review the diff before committing. A saved file also contains the player's character names and settings.

### Tests

```bash
pip install lupa
python3 tools/test/run_tests.py
```

This runs the addon's Lua against a fake WoW API with the real quest data, as Human, Orc and other characters, about 190 checks in all. It covers:
- eligibility, reputation and repeatable quests;
- quest statuses and storyline building;
- dungeon and raid pages;
- jumping and **Back**;
- the detail panel, its text sources and spoiler hiding;
- saving quest text as you play;
- waypoints, the minimap button and every setting;
- **Reset to defaults**;
- error safety: any error the addon catches fails the run.

It can't check how things look in game.

---

## Installing

1. **Get it:** install from [CurseForge](https://www.curseforge.com/projects/1793930) (or the CurseForge app), or download the latest release zip from GitHub Releases. Cloning this repository also works, but brings the `tools` and `media` folders along.
2. **Copy it:** put the `LorePath` folder into WoW Forever's `Interface/AddOns` folder. To find it, in the Battle.net app, pick WoW Forever, click the gear icon, choose **Show in Explorer** (**Show in Finder** on macOS), and open the Forever folder.
3. **Start it:** start the game, or `/reload`, and type `/lp`.

## Releasing

1. Bump `## Version` in `LorePath.toc` and add the release to `CHANGELOG.md`.
2. Push a tag (`v*`). [BigWigsMods/packager](https://github.com/BigWigsMods/packager) builds the addon, attaches it to a GitHub Release and uploads it to CurseForge.
   - **CurseForge:** project 1793930, set by `## X-Curse-Project-ID` in `LorePath.toc`, using the `CF_API_KEY` repository secret.
   - **Release type:** tags containing "beta" or "alpha" upload as beta or alpha files; other tags are full releases.
   - **Release notes:** `CHANGELOG.md`.
   - **Left out of the package:** `README.md`, `CHANGELOG.md`, `tools` and `media`.

## Licence

LorePath is MIT-licensed. Its bundled data:
- **`Data/Quests.lua`** is derived from AllTheThings, also MIT-licensed. Its licence is in `Data/AllTheThings-LICENSE.txt`.
- **`Data/QuestText.lua`** comes from pfQuest (MIT, licence in `Data/pfQuest-LICENSE.txt`), which took it from the VMaNGOS project.
- **`Data/CommunityText.lua`** was collected in game by LorePath's players.

The quest text itself is Blizzard's.
