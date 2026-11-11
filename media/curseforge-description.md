# LorePath

**See your story, zone by zone.**

LorePath draws every zone's, dungeon's, raid's and battleground's questlines as storyline maps, in the style of attunement path views. At a glance you can see which quests you've done, which you've missed and where the next part of each story starts. Click any quest to read its story.

Built for **WoW Forever**, on English game clients. It's lightweight: its map pins only show where quests start, and there's no objective tracking, so it works alongside the default quest UI.

## Features

- **Storyline maps:** each page's quest chains, drawn from the first quest to the last, with lines showing what unlocks what. Storylines collapse, and finished ones start collapsed. Drag anywhere on the graph to pan, even from a quest.
- **A zone list that tells you where to go:**
  - every zone, dungeon, raid and battleground with quests for you, each with an icon and WoW Forever's level range;
  - names coloured by progress, from grey (not started), then red through orange and yellow to green (finished);
  - finished sections start collapsed, and LorePath opens on the zone or instance you're in.
- **Class and Professions pages:** every quest for your class, and for each of your professions, in one place, with chains that cross zones shown whole.
- **Search:** find any quest by name or ID from the box above the zone list.
- **Only your quests:** quests for another faction, race or class are left out. Quests that come in one version per starting area, like the Shaman totem quests, show once.
- **Clear status at a glance:** completed, in your log, available (coloured by difficulty, like your quest log), repeatable (blue), too high level, needs an earlier quest, and skipped.
- **Telling icons:** a portal for quests picked up inside a dungeon or raid, your class or profession icon, or the icon of the item that starts the quest.
- **Quest details:** click a quest to open a panel showing:
  - requirements, where it starts and who gives it;
  - **Good to know:** tips such as where a quest's item drops, or what finishing it locks you out of (also in the tooltip);
  - its objectives and description, plus progress and completion text;
  - its item rewards (Shift+click to link one in chat);
  - the quests before and after it;
  - a WarcraftDB link to copy.

  No spoilers: quests you haven't started show "Find what awaits you" until you press Reveal, and how a quest ends stays hidden until you turn it in. Turn on **Show spoilers** to see everything.
- **Your story, saved:** LorePath saves the quest text you see as you play, so you can go back and reread it. For quests you did before installing it, it fills in from:
  - community text, including many of WoW Forever's own quests;
  - the game's own quest summaries;
  - bundled text for every vanilla quest.
- **Share your quest text:** press **Share quest text** in the settings (or type `/lp share`) to send the text you've collected, so everyone gets the story of WoW Forever's own quests.
- **Quest log, both ways:** open a quest you're on in the game's quest log, or open the quest log's selected quest in LorePath.
- **Jump around:** click "Next" or "First finish" in a storyline to jump to that quest, even in another zone or dungeon. **Back** takes you back.
- **Waypoints:** Ctrl+click a quest, or use **Show on map**, to set the game's own waypoint where it starts.
- **Minimap button:** left-click to open, right-click for settings, drag to move.
- **Settings** under *Options → AddOns → LorePath*: hide finished storylines, show or hide standalone and repeatable quests, show professions you don't have, spoilers, window size, and more.

## Commands

| Command | What it does |
| --- | --- |
| `/lp` | Open or close LorePath |
| `/lp config` | Open settings |
| `/lp share` | Share the quest text you've collected |

You can also bind a key under *Options → Key Bindings → AddOns → LorePath*.

## Coming later

Storylines are currently named after their first quest. Lore for zones, places and characters, and a searchable codex, are planned.

## Credits

- **Quest data and notes:** [AllTheThings](https://github.com/ATTWoWAddon/AllTheThings)' WoW Forever database (MIT). If a quest is missing or its chain is wrong, please report it to AllTheThings too, so everyone benefits.
- **Vanilla quest text:** [pfQuest](https://github.com/shagu/pfQuest) (MIT), originally from VMaNGOS.
- **Community quest text:** collected in game by LorePath's players.

Bugs and ideas: [GitHub](https://github.com/Jacob-Haynes/LorePath)
