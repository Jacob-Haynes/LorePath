# LorePath

**See your story, zone by zone.**

LorePath draws every zone's, dungeon's and raid's questlines as storyline maps, in the style of attunement path views. At a glance you can see which quests you've done, which you've missed and where the next part of each story starts. Click any quest to read its story.

Built for **WoW Forever**, on English game clients. It's lightweight: no map pins and no objective tracking, so it works alongside the default quest UI.

## Features

- **Storyline maps:** each zone's quest chains, drawn from the first quest to the last, with lines showing what unlocks what. Storylines collapse, and finished ones start collapsed.
- **Dungeons and raids** get their own pages, and LorePath opens on the instance you're in.
- **Only your quests:** quests for another faction, race or class are left out. Profession quests show only if you have that profession, and reputation requirements are shown.
- **Clear status at a glance:** completed, in your log, available (coloured by difficulty, like your quest log), repeatable (blue), too high level, needs an earlier quest, and skipped.
- **Progress counts** for every zone and storyline. Repeatable quests are counted separately.
- **Quest details:** click a quest to open a panel showing:
  - requirements, where it starts and who gives it;
  - its objectives and description, plus progress and completion text;
  - its item rewards;
  - the quests before and after it;
  - a WarcraftDB link to copy.

  No spoilers: quests you haven't started show "Find what awaits you" until you press Reveal, and how a quest ends stays hidden until you turn it in. Turn on **Show spoilers** to see everything.
- **Your story, saved:** LorePath saves the quest text you see as you play, so you can go back and reread it. For quests you did before installing it, it fills in from:
  - community text, including many of WoW Forever's own quests;
  - the game's own quest summaries;
  - bundled text for every vanilla quest.
- **Jump around:** click "Next" or "First finish" in a storyline to jump to that quest, even in another zone or dungeon. **Back** takes you back.
- **Waypoints:** Ctrl+click a quest, or use **Show on map**, to set the game's own waypoint where it starts.
- **Repeatable quests** in blue, which you can show or hide with one tick box.
- **Minimap button:** left-click to open, right-click for settings, drag to move.
- **Settings** under *Options → AddOns → LorePath*: hide finished storylines, show or hide standalone and repeatable quests, window size, and more.

## Commands

| Command | What it does |
| --- | --- |
| `/lp` | Open or close LorePath |
| `/lp here` | Open on the zone you're in |
| `/lp config` | Open settings |
| `/lp repeatable` | Show or hide repeatable quests |
| `/lp spoilers` | Show or hide the story of quests you haven't started |
| `/lp minimap` | Show or hide the minimap button |

You can also bind a key under *Options → Key Bindings → AddOns → LorePath*.

## Coming later

Storylines are currently named after their first quest. Lore for zones, places and characters, and a searchable codex, are planned.

## Credits

- **Quest data:** [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT). If a quest is missing or its chain is wrong, please report it to AllTheThings too, so everyone benefits.
- **Vanilla quest text:** [pfQuest](https://github.com/shagu/pfQuest) (MIT), originally from VMaNGOS.
- **Community quest text:** collected in game by LorePath's players.

Bugs and ideas: [GitHub](https://github.com/Jacob-Haynes/LorePath)
