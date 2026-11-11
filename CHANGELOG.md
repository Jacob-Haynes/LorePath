# Changelog

## Unreleased

- **One version of each quest:** quests that come in several versions, one per starting area, now show once. The Shaman totem quests (Call of Earth, and Zephras Isle's Call of Fire) appeared once per starting area on the Class page. LorePath shows the version you've done or have, else the one that starts nearest your race's home. Breadcrumbs that only lead into a hidden version are hidden too, since you couldn't complete them; every other breadcrumb stays.
- **Progress colours in the zone list:** zone, dungeon, raid, Class and profession names are grey until you start them, then go from red through orange (40%) and WoW's gold (80%) towards green as you finish their quests. Only finished ones are fully green.

## 1.1.0-beta1

- **Quest search:** a search box above the zone list finds quests by name (any words, any order) or ID. Up to 50 results replace the zone list, showing each quest's zone, status and level; click one to jump to it. Escape clears the search. `/lp search <name>` opens LorePath with the search filled in.
- **Class and Professions pages:** at the top of the zone list. **Class** shows every quest for your class from all zones, with chains that travel between zones as one storyline. **Professions** has a page per profession you have; a new **Show professions you don't have** setting lists the rest, greyed out. Tooltips on these pages say which zone each quest is in.
- **Zone list icons:** every zone, dungeon and raid in the zone list has an icon, with a tick on zones you've finished. Continent, Dungeons and Raids headings have icons too, and so does the zone name above the graph. The icons come from AllTheThings' data, with a generic icon where it has none.
- **Open in quest log:** a quest you're on has an **Open in quest log** button in its details, and Shift+clicking it in the graph does the same. It opens the game's quest log at that quest, with its live objectives. Not in combat.
- **Show in LorePath:** a LorePath book button on the game's quest log opens the selected quest in LorePath, in its storyline with its details. `/lp quest` does the same, and `/lp quest <ID>` opens any quest.
- **Drag from anywhere:** the graph pans when you drag from a quest box or a storyline header too, not only from empty space, so a busy zone is easy to move around. A press that doesn't move is still a click.
- **Share your quest text:** `/lp share` shows a code holding the quest text you've saved that LorePath doesn't have yet (titles, objectives, descriptions, progress and closing text, and rewards), with your character names replaced by `$N`. Paste it into a **Share quest text** issue on GitHub, and once it's reviewed, the next release gives everyone the story of WoW Forever's own quests.
- **Profession requirements** read "Needs Leatherworking 225" instead of "Needs skill 225".
- **10 more profession quests:** the Blacksmithing and Leatherworking specialisation quests from AllTheThings' Professions data.

## 1.0.1

- **No spoilers:** quests you haven't started show "Find what awaits you." in their details, with a **Reveal** button, instead of their objectives and story. Quests in your log show their objectives and description, but not how they end. Completed quests show everything. A new **Show spoilers** setting (and `/lp spoilers`) shows everything always.
- **Quest details:** the WarcraftDB link is now at the very bottom of the panel.

## 1.0.0

The first full release. Everything from the betas, plus:

- **WarcraftDB link:** each quest's details include its WarcraftDB address, ready to copy into a browser.
- **Reset to defaults** (on the settings page) also re-opens collapsed storylines and zone list headings, and shows the zone list again. Your saved quest text is kept.
- **Sturdier:** an error in one part of LorePath (for example, saving a quest's text) is reported once in chat and no longer stops the rest from working.
- **Rewards:** the details panel lists item rewards. Gold, XP and reputation rewards are saved as you play but not shown for now.
- **Quest text:** two community texts now read correctly for every gender and class.

## 0.1.0-beta6

- **Quest details panel:** click a quest to open a panel beside the window, showing:
  - requirements, where it starts and who gives it;
  - objectives and description, plus progress and completion text;
  - item rewards;
  - the quests before and after it.

  Click the same quest again to close it.
- **Ctrl+click** a quest to set its waypoint (a plain click used to).
- **Quest text saved as you play:** when a quest giver shows a quest, when you accept it, when you hand items in, at the turn-in screen, and everything in your log at login. Your character's name is stored as `$N`.
- **Filling gaps for quests from before you installed LorePath:**
  - community text, seeded with 250 quests, 126 of them with no other source of text (almost all WoW Forever's own);
  - the game's own quest link goal and requirements;
  - bundled vanilla quest text from pfQuest, covering 3,285 quests.
- **Recipe, mount and toy rewards** are now listed (79 quests gained rewards).
- **Repeatable quests** show as "+N repeatable" in totals, so a page of dailies no longer reads 0/0.
- **Tidier footer:** level colours and tips moved into a "?" tooltip.

## 0.1.0-beta5

- **Dungeon and raid quests:** 565 quests on their own pages, under Dungeons and Raids headings. LorePath opens on the instance you're in.
- **Repeatable quests** in blue, with a Repeatable tick box, a setting and `/lp repeatable` to show or hide them. They never count toward progress.
- **Back button** after jumping to a quest. The zone list scrolls to the selected zone.

## 0.1.0-beta4

- **Clickable next step:** "Next" and "First finish" in a storyline header jump to that quest, even in another zone.
- **"Show on map"** replaces "Show next quest".

## 0.1.0-beta3

- **Reputation requirements:** quests that need more reputation say so; quests you've outgrown are marked as no longer available.
- **Bigger, clearer status markers.** Quests that are too high level show their level in red.

## 0.1.0-beta2

- **New look,** styled after Attune: tinted quest boxes, square connectors, a stone background.
- **Collapsing:** storylines collapse, finished ones start collapsed, and continent headings and the whole zone list can be collapsed or hidden.
- **Quest log colours:** quest levels use the quest log's difficulty colours.

## 0.1.0-beta1

- **First beta:** every quest your character can do, by zone, as storyline graphs, with done/missing status and waypoints. Includes a minimap button, settings page and key binding.
