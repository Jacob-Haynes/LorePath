# LorePath

"Hold your own hand"

**LorePath** is a lightweight WoW Forever addon that maps *your* story. For every zone, dungeon, raid and battleground it draws each questline as a storyline graph, in the style of Attune's attunement paths. It shows what you've done, what you've missed and where the next part of each story starts. Click any quest to read its story.

It's not a quest helper. Its world map pins only show where quests start, and there's no objective tracking, so it sits happily alongside the default quest UI.

LorePath supports English game clients only.

> **Version 1.1.0.** Lore beyond quest text (zones, characters, a codex) is planned.

---

## What it shows

- **Class and Professions:** at the top of the zone list, **Class** gathers every quest for your class from all zones, so class chains that travel (say, from a capital city to another zone) show as one storyline. **Professions** has a page for each profession you have, with its quests. Their tooltips say which zone each quest is in. Quests your skill is too low for say what they need, for example *Needs Leatherworking 225*.
- **Attunements:** under **Attunements** in the zone list, a page for each chain that unlocks a dungeon or raid (Onyxia's Lair, Upper Blackrock Spire, Scholomance, Shadowforge City), with your faction's quests as one storyline across zones, and the key it ends in, ticked once you have it. They're listed by hand in `Data/Attunements.lua`, since AllTheThings doesn't model attunements.
- **Zone list:** every zone with quests your character can do, grouped by continent, each with a progress count (for example *Elwynn Forest 12/75 +3*, where "+3" is repeatable quests). Dungeons, raids and battlegrounds get their own pages under **Dungeons**, **Raids** and **Battlegrounds** headings (Scarlet Monastery's Graveyard and Library wings have their own too), and inside an instance the window opens on its page. Zones, dungeons, raids and battlegrounds show WoW Forever's suggested level range in a column before the count, read from the game's Looking for Group list; hover a row for its full name, range and progress. Names are coloured by progress: grey before you start, then a gradient from red through orange and yellow to green as you go, fully green once finished. Each zone, dungeon and raid has an icon, with a tick once you've finished it, and headings show their continent's icon. Headings collapse, and a heading whose quests are all done starts collapsed (unless it holds the page you're on). The whole list can be hidden to give the graph more room.
- **Storylines:** each page's quest chains, drawn left to right from the first quest to the last, with lines joining each quest to the ones it unlocks. A storyline that starts from a quest in another zone, or goes on into one, shows those quests as faded, blue-bordered tiles at its ends, with that zone's icon (*< From Elwynn Forest*, *Continues in Westfall >*); click one to go there. A storyline wider than the window wraps into bands, one under the other. Each storyline can be collapsed, and finished ones start collapsed. **Expand all** and **Collapse all** sit at the top.
- **Other quests:** standalone quests with no chain, under each page's storylines.
- **Only your quests:** quests for another faction, race or class are left out. Profession quests show only if you have that profession (or, with **Show professions you don't have**, greyed out on the Professions page). Quests that come in one version per starting area, like the Shaman totem quests, show once: the version you did, else the one from your race's home. Breadcrumbs that only lead to quests you can't do are left out.
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

  Quests you pick up inside a dungeon or raid show its entrance portal, class quests your class icon, profession quests the profession's icon, quests started by an item that item's icon, and breadcrumbs a letter. The "?" button in the footer explains the level colours.
- **Tooltips:** hover a quest for its level, status, what it needs (earlier quests, reputation, skill), what comes before and after it, where it starts, its item rewards, and AllTheThings' note on it when there is one.
- **Quest details:** click a quest to open a panel beside the window, and click it again to close it. The panel shows:
  - requirements;
  - where it starts and who gives it, or the item that starts it and what drops or holds that item (click an outdoor one for a waypoint);
  - **Good to know:** AllTheThings' note on the quest, when it has one (where an item drops, what finishing it locks you out of, and so on);
  - its objectives and description, plus progress and completion text;
  - its item rewards (Shift+click one to link it in chat, Ctrl+click to try it on);
  - the quests before and after it, as links;
  - its address on WarcraftDB, to copy, at the bottom.

  **No spoilers by default:** a quest you haven't started shows "Find what awaits you." with a **Reveal** button, instead of its objectives and story. A quest in your log shows its objectives and description, but not how it ends. A completed quest shows everything. Reveal lasts until you look at another quest. **Show spoilers** in the settings shows everything always.
- **Search:** type part of a quest's name, or its ID, in the box above the zone list. The list shows up to 50 matching quests you can do, with their zone, status and level; click one to jump to it. Escape clears the search.
- **Jumping around:** in a storyline's header, click **Next**, **In progress** or **First finish** to jump to that quest, even in another zone or dungeon. **Back** returns you.
- **Waypoints:** Ctrl+click a quest, or use **Show on map** (in its details, or in a storyline's header for the next quest), to set the game's own waypoint where it starts and open the map there.
- **World map pins:** a "!" where each quest starts on the zone map you're viewing: gold for quests at your level, grey for low-level ones, red for quests you're not high enough level for yet (a blue "!" for repeatable quests). Each of the three has its own entry under **LorePath quests** in the world map's filter menu, and in the settings. Only quests at your level are on by default. Quests that start at the same spot share a pin, with a count. Hover a pin for the quest's tooltip, click it to set a waypoint there, or Shift+click it to open the quest in LorePath.
- **Quest log, both ways:** for a quest you're on, **Open in quest log** in its details, or Shift+click it, opens the game's quest log at that quest. The other way, the LorePath book button on the game's quest log opens the selected quest in LorePath with its details.

### Controls

| Action | How |
| :--- | :--- |
| Open or close | Left-click the minimap button, `/lp`, the addons menu by the minimap, or a key binding (*Options → Key Bindings → AddOns → LorePath*) |
| Settings | Right-click the minimap button or the addons-menu entry, the **Settings** button in the window, `/lp config`, or *Options → AddOns → LorePath* |
| Find a quest | Type in the search box above the zone list; Escape clears it |
| Quest details | Click a quest; click it again to close the panel |
| Waypoint | Ctrl+click a quest, or **Show on map** |
| Open in your quest log | Shift+click a quest you're on, or **Open in quest log** in its details |
| Choose which quests show on the world map | **LorePath quests** in the world map's filter menu, or the settings page; click a pin for a waypoint, Shift+click it to open the quest in LorePath |
| Open a quest log quest in LorePath | The LorePath book button on the game's quest log |
| Collapse | Click a storyline's or heading's +/−, or **Expand all** / **Collapse all** |
| Hide the zone list | The arrow button left of the zone name |
| Show or hide repeatable quests | The **Repeatable** tick box, or the settings page |
| Reveal a quest's story | **Reveal** in its details; or **Show spoilers** in the settings for every quest |
| Show or hide the minimap button | The settings page |
| Share the quest text you've collected | **Share quest text** on the settings page, or `/lp share`, then paste the code into a [Share quest text](https://github.com/Jacob-Haynes/LorePath/issues/new/choose) issue |
| Move the window | Drag its title bar |
| Move the minimap button | Drag it around the minimap |
| Scroll | Mouse wheel, or Shift + wheel to scroll sideways |
| Pan around a large graph | Drag with the left mouse button, from anywhere on the graph, even on a quest or a storyline header |
| Close | Escape |

`/lorepath` works the same as `/lp`, and `/lp help` lists the commands and shows your version.

### Settings

The settings page scrolls, and groups its options under three headings.

| Option | Default | What it does |
| :--- | :--- | :--- |
| **Window** | | |
| Show minimap button | On | Left-click opens LorePath, right-click opens settings. |
| Open on the zone you're in | On | Each time the window opens, it jumps to your current zone (or instance). Off: it reopens on the last page you looked at. |
| Window size | 100% | Scales the window from 60% to 140%. |
| **Quests** | | |
| Hide finished storylines | Off | Leaves out storylines where every quest is done. |
| Show standalone quests | On | Lists quests that aren't part of a chain under each page's storylines. |
| Show repeatable quests | On | Shows daily and repeatable quests, in blue. Same as the **Repeatable** tick box. |
| Show professions you don't have | Off | Lists every profession under **Professions**, with the ones you don't have greyed out and their quests locked. |
| Show quest levels on tiles | On | Shows each quest's minimum level on its tile. Quests that are too high level always show it, in red. |
| Show spoilers | Off | Shows the full story of every quest in its details. Off: quests you haven't started, and how quests in your log end, stay hidden until you press **Reveal**. |
| **World map** | | |
| Open the map when setting a waypoint | On | Opens the world map at the quest's start when you set a waypoint. |
| Show quests on the map: quests at your level | On | A gold "!" on the zone map where each quest at your level starts. Also in the world map's filter menu, like the next two. |
| Show quests on the map: low-level quests | Off | A grey "!" where quests too low to give you much experience start. |
| Show quests on the map: quests above your level | Off | A red "!" where quests you're not high enough level for yet start. |

**Reset to defaults** on the settings page puts every setting back, re-opens collapsed storylines and headings, and shows the zone list again. It keeps your saved quest text.

### What LorePath saves

Everything is saved per account in `LorePathDB` (`WTF/Account/<account>/SavedVariables/LorePath.lua`):
- **Settings:** the settings above, plus where the minimap button sits and the last page you looked at.
- **Window layout:** which storylines and headings are collapsed, and whether the zone list is hidden.
- **Quest text (`questCache`):** what the game shows you, saved as you play: description, objectives, progress and completion text. Your character's name is stored as `$N`. Gold, XP and reputation rewards are saved too, but not shown yet. So is where each quest was offered (`start`): by a creature or object (its ID) or an item, and your map and position, or just the instance when you're inside one.
- **Character names (`characters`):** your account's character names, so `/lp share` and `tools/merge_quest_text.py` can replace any that slip into quest text with `$N`.

### Sharing quest text

WoW Forever's own quests aren't in any quest database, so the only source for their story is what players see in game. LorePath saves it as you play; `/lp share` sends it to everyone:

1. Press **Share quest text** on the settings page, or type `/lp share`. A window shows a share code (it starts with `LP1:`) holding the quest text you've saved that LorePath doesn't ship yet: titles, objectives, descriptions, progress and closing text, plus gold, XP and reputation rewards, and where quests that LorePath has no start for were offered. Your character names are replaced with `$N`; nothing else about you is in it.
2. Click the code, press Ctrl+C, and paste it into a new **Share quest text** issue. A big collection comes as several codes; send each one in its own issue.
3. A check replies on the issue with what it added, and adds the text to a pull request. Once a maintainer has reviewed and merged it, the next release has it.

---

## Where the data comes from

| Data | Source |
| :--- | :--- |
| Which quests exist, their chains, level, faction/race/class, profession and reputation requirements, repeatables, start location, quest giver, item rewards, and dungeon and raid pages | [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT), extracted into `Data/Quests.lua`: 4,334 quests on 50 zone pages and 33 instance pages (28 dungeon pages, counting Scarlet Monastery's two wings, 1 raid and 4 battlegrounds). Also each quest's starting item, where it's picked up inside an instance, and AllTheThings' notes on 89 quests, in `Data/QuestNotes.lua` |
| What you've completed, what's in your log, your level, race, class, faction, professions and reputation | The game client, live |
| Quest, zone, item, NPC and faction names | The game client, in your language |
| Level ranges of zones, dungeons, raids and battlegrounds | The game client's Looking for Group list, live |
| What drops or holds an item that starts a quest, with chances and locations | [pfQuest](https://github.com/shagu/pfQuest)'s item, creature and object data (MIT, originally from VMaNGOS), in `Data/QuestStarts.lua`: sources for 56 item-started quests |
| Quest text: description, objectives, progress and completion text | In this order:<br>1. **What you've seen:** saved from the game as you play (when a quest giver shows a quest, when you accept it, when you hand items in, at the turn-in screen, and your quest log at login).<br>2. **Community text:** `Data/CommunityText.lua`, collected by players, including WoW Forever's own quests (250 quests so far).<br>3. **The game's own quest-link tooltip:** the quest's goal and requirements, even for quests completed long ago.<br>4. **Bundled vanilla text:** [pfQuest](https://github.com/shagu/pfQuest)'s English quest database (MIT, originally from VMaNGOS), in `Data/QuestText.lua`: 3,285 vanilla quests, not WoW Forever's own. |

Missing quests, or wrong chains, levels or start points, come from AllTheThings' Forever data. Please report them to AllTheThings too, so everyone benefits. Wrong or missing quest text is LorePath's own.

### Updating the quest data

```bash
pip install lupa
git clone --depth 1 --filter=blob:none --sparse https://github.com/ATTWoWAddon/AllTheThings.git att
(cd att && git sparse-checkout set db/Camelot)
python3 tools/extract_att.py att
```

`tools/extract_att.py` loads AllTheThings' Forever zone, dungeon and raid, profession and PvP data (`Categories/Zones.lua`, `Instances.lua`, `Professions.lua` and `PVP.lua`, plus header names from `LocalizationDB.lua`) in a sandboxed Lua runtime, then writes the quest records LorePath needs to `Data/Quests.lua` and AllTheThings' quest notes to `Data/QuestNotes.lua`.
- **Kept:** repeatable quests, flagged `rp`.
- **Skipped:** quests AllTheThings marks unavailable, and quests added after or removed by Forever's build.
- **Faction versions:** a quest with separate Alliance and Horde versions keeps both, in `fv`.
- **Recorded:** the headers of `Data/Quests.lua` and `Data/QuestNotes.lua` name the AllTheThings commit the data came from.

To see what changed, compare against the committed file:

```bash
git show HEAD:Data/Quests.lua > /tmp/Quests.old.lua
python3 tools/diff_quests.py /tmp/Quests.old.lua Data/Quests.lua
```

The [Sync quest data from AllTheThings](.github/workflows/sync-att-data.yml) workflow does this every Monday, or on demand from the Actions tab:
- **If the quest data changed,** it opens or updates a PR from the `data/att-sync` branch with the summary.
- **It fails instead** if the quest count drops by more than 10%, a zone disappears, the data doesn't load, or the tests fail. The tests include a check for quests that would show twice (see [Tests](#tests)).
- **Merging and releasing stay manual.**
- **Repository setting:** opening the PR needs *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests* turned on.

`Data/QuestText.lua`, the bundled vanilla text, is a one-off import and isn't part of the weekly sync, because vanilla quest text doesn't change. `python3 tools/extract_pfquest.py` rebuilds it if ever needed, for example after new vanilla quests appear in `Data/Quests.lua`. Likewise `python3 tools/extract_quest_starts.py` rebuilds `Data/QuestStarts.lua`, where item-started quests' items come from, after the quest data gains new ones.

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

This runs the addon's Lua against a fake WoW API with the real quest data, as characters of several races and classes (Human, Orc, Tauren and WoW Forever's own race among them), about 370 checks in all. It covers:
- eligibility, reputation, repeatable quests, faction versions and one version per starting area;
- quest statuses and storyline building;
- zone, dungeon, raid, battleground, Class and profession pages, and level ranges;
- the zone list: icons, progress colours and collapsing;
- search, jumping and **Back**, and dragging the graph;
- the detail panel, its text sources, notes and spoiler hiding;
- quest icons, the quest log both ways and linking rewards;
- saving and sharing quest text, including the merge tool;
- world map pins: which quests get one, grouping, colours, tooltips, clicks and refreshing;
- waypoints, the minimap button, slash commands and every setting;
- **Reset to defaults**;
- error safety: any error the addon catches fails the run;
- quests in the data twice (below).

It can't check how things look in game.

**Quests in the data twice.** AllTheThings sometimes has one quest under two IDs (Amongst the Ruins was 908 and 6921), so it showed once as done or in your log and once as still available. The tests look for quests with the same name on one page that one character could have together (same faction or none, overlapping races and classes) and that aren't steps of one storyline or versions of each other. When one turns up, usually after an AllTheThings sync, the test lists the pair and someone decides once:
- **one quest twice:** add it to `EXTRA_VERSIONS` in `Core.lua`, so only one shows;
- **really two quests** (a quest for each faction's cloth quartermaster, say): add it to `SEPARATE` in `tools/test/run_tests.py`, with a comment saying why.

The test also fails if a `SEPARATE` entry is no longer needed, so the list stays short. Quests with no name in LorePath's text (about 900, mostly WoW Forever's own) can't be checked this way.

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
   - **Left out of the package:** `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `tools` and `media`.

## Licence

LorePath is MIT-licensed. Its bundled data:
- **`Data/Quests.lua`** and **`Data/QuestNotes.lua`** are derived from AllTheThings, also MIT-licensed. Its licence is in `Data/AllTheThings-LICENSE.txt`.
- **`Data/QuestText.lua`** and **`Data/QuestStarts.lua`** come from pfQuest (MIT, licence in `Data/pfQuest-LICENSE.txt`), which took the data from the VMaNGOS project.
- **`Data/CommunityText.lua`** was collected in game by LorePath's players.

The quest text itself is Blizzard's.
