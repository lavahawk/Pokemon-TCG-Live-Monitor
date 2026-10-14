# Pokemon TCG Live Monitor v2.6

This one's mostly about getting the opponent's deck right, making the deck pages actually clickable, and cleaning up the Meta tab, which had gotten pretty cluttered. There's a bunch of smaller stuff too.

## Install
Grab **`PokemonTCGLiveMonitor-2.6.0-Setup.exe`** below and run it.

- It ships with its own Python and Tesseract, so there's nothing else to download.
- No admin rights needed. If you're on any 2.x version, just install over it; your battles and settings stay put.
- SmartScreen will probably complain since the installer isn't signed. Click **More info → Run anyway**. The `.sha256` is there if you want to check the file.
- Windows 10 or 11, 64-bit.

## Opponent deck
- After a battle the overlay now shows the 3 most likely decks with their icons and odds. Just click the right one.
- The confidence number finally means something. It used to sit around 90 no matter what; now it's how sure the app actually is. Under 50% it'll ask you which deck it was instead of guessing.
- The guess is based on the cards your opponent actually played (and how many copies), checked against ~95k public decklists. When two decks are close, it goes with the more popular one.

## Deck page
- More of it is clickable now:
  - Meta Score and Score · your games (which now show a ±) take you to your deck's row in the Meta tab.
  - Meta faced scrolls down to your matchups.
  - The Last 10 squares jump to that game.
- Every recent game has Replay, Cards played and Deck archetype buttons.
- You can link a decklist to a deck. Just export it from PTCGL while the import window is open and it's picked up from your clipboard. Once a list is linked you get card suggestions (stuff most lists run that yours doesn't), a comparison in Meta → Cards, and shortcuts to TrainerHill's Deck Diff, Card Usage and Deck Profile.

## Meta tab
- Way less text. The status line is a single line now (hover it for the details), the colour legend lives on the Sources heading, and the weights note only shows up on the columns it affects when custom weights are on.
- Hover text on the table is short. If you want the formulas, hover the column headings (try **Score**).
- New Cards view: see what a deck's lists usually play and how yours compares.
- Japan Data now runs on Limitless City League results.

## Other stuff
- Import sounds: turn it off, pick from 6 sounds, set the volume (Advanced → Preferences · Sound).
- Better browser tabs (Limitless, TrainerHill, Replay, PokeData, In Person), with some ad blocking built in.
- The battle database editor got fixed up: proper Replay / Log / Delete buttons, the last 50 games, and it refreshes on its own.
- Auto-export clicks hold the cursor in place for a split second, so moving your mouse during the click won't make it miss anymore.

You can now double click the pokeballs, maybe something is inside?

## Also since v2.5
- Meta data now covers the whole format: 850+ online events, in-person results and Japanese City Leagues. You can add a Limitless API key under Advanced → Meta Data if you want.
- The win rate chart on deck pages is interactive, and the dashboard one can be filtered by deck.
