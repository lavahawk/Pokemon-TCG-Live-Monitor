# Pokemon TCG Live Monitor v2.13.0

A faster, clearer Meta tab built on the app's own data.

## Install
Grab **`PokemonTCGLiveMonitor-2.13.0-Free-Setup.exe`** below and run it.

- It ships with its own Python and Tesseract, so there's nothing else to download.
- No admin rights needed. If you're on any 2.x version, just install over it; your battles and settings stay put.
- SmartScreen will probably complain since the installer isn't signed. Click **More info → Run anyway**. The `.sha256` is there if you want to check the file.
- Windows 10 or 11, 64-bit.

## What's new
- **Meta data keeps itself current.** The Meta tab opens instantly with your saved data, and new tournaments download a few at a time in the background, so your PC never has to do it all at once. The status line shows how fresh it is.
- **Matchups, redone.** Each cell shows the win % and the W-L-T record, blue when the row deck is ahead and red when it's behind. Pick **This set** (games since the latest expansion) or **All data**, and export the grid as CSV.
  - When there aren't enough games to call a matchup, the cell shows a range (like 38–62%) on stripes instead of a single number.
  - Hover or click a cell for a card showing both decks at either end of a bar, leaning toward the winner.
  - Decks with two Pokémon show both sprites.
- **Trend from the app's own data.** It loads instantly and works offline, with a headline of which decks are rising and falling.
- **Better search on the Meta tab.** Type in **Search** and the matches move to the top: deck names first, then Pokémon, then cards in the lists. The best one is highlighted; press Enter for the next. The filter button next to it shows only the matches. Or click a deck and just type to jump to one without reordering anything.
- **Data sources are simple toggles.** Online, In-person and Japan are all on by default; turn off any you don't want.
- **Sharp Pokémon sprites** on high-resolution screens (125%, 150% scaling and up).
- **Clearer labels.** Win rates say what they are: *Adjusted* (weighted and steadied for small samples), *Actual* (your raw record), or *Expected vs meta*. The Meta table's Record and Win % say *Weighted* while custom weights are on.
- **TrainerHill Deck Diff fills in your list.** From a deck's Decklist menu, *Deck diff (list filled in)* opens TrainerHill with your list already loaded.
