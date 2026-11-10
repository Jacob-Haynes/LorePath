# Changelog

## Unreleased

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
