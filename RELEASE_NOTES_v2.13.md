# Pokemon TCG Live Monitor v2.13.2

## Install
Run **`PokemonTCGLiveMonitor-2.13.2-Free-Setup.exe`**. Install over any 2.x version; your battles and settings are kept. If SmartScreen warns you, click **More info → Run anyway** (the installer isn't signed). Windows 10/11, 64-bit.

## What's new
- **Auto-export keeps trying until the log is saved.** Clicking or moving the mouse mid-export, or switching windows for a moment, no longer cancels it. *(2.13.2)*
- **Advanced is now Settings**, split into General, Battle tracking, Data & weights, Your data and Troubleshooting, with a list on the left to jump between them. *(2.13.2)*
- **Auto-export is quicker to block Continue.** The cover goes up the moment the BATTLE LOG button shows, before its text is checked, so a fast click on Continue no longer skips the export. *(2.13.1)*
- **Fixed exports that gave up halfway** when the button was still animating. *(2.13.1)*
- **OCR Bounding Box Debug** (Settings → Troubleshooting). Shows the areas the app reads, live, over the game. Turn on Edit boxes to drag the rank and deck-name boxes into place if they're off on your screen. It also saves the last few end-of-battle screens to `Logs/end_screens`, handy for bug reports. *(2.13.1)*
- **Meta tab loads instantly.** New tournaments download a few at a time in the background.
- **New Matchups grid.** Win % and W-L-T in each cell. Too few games shows a range instead. Hover or click a cell for details. Choose This set or All data, or export to CSV.
- **Trend uses the app's own data**, so it's instant and works offline. Shows which decks are rising and falling.
- **Search.** Matches move to the top: deck names, then Pokémon, then cards. Enter goes to the next one. The filter button hides the rest. Click a deck and type to jump instead.
- **Data sources** are separate toggles: Online, In-person, Japan.
- **Sharper Pokémon sprites** on scaled displays.
- **Text size is a slider** (80–200%), and text no longer gets cut off at larger sizes.
- **Rename a deck by double-clicking its name.** Type another deck's name to merge them.
- **Clearer labels.** Win rates are marked Adjusted, Actual or Expected vs meta.
- **TrainerHill Deck Diff** loads your list for you.
