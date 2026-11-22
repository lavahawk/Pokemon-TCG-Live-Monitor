# Pokemon TCG Live Monitor v2.14.3

## Install
Run **`PokemonTCGLiveMonitor-2.14.3-Free-Setup.exe`**. Install over any 2.x version; your battles and settings are kept. If SmartScreen warns you, click **More info → Run anyway** (the installer isn't signed). Windows 10/11, 64-bit.

## What's new in 2.14.3
- **Tournament games are tagged again when the opponent's game name differs from their Limitless name.** The battle log uses their Pokémon TCG Live screen name, and only the Limitless name was compared, so those games were saved as regular games. Either name now counts.
- **Friend requests** wait up to a minute for the screen name to show up on the match page. If it never does, a Limitless name with a space in it isn't typed into the game (it can't be anyone's game name); it's put on your clipboard instead.

## What's new in 2.14.2
- **Opponent decklist window:** the window sizes itself to the list, and the cards are a little bigger. Every card zooms to the same size on hover, even past the window's edge. An Opacity slider lets you see the game through the window, and it remembers where you left it. **Copy image** puts Limitless's normalized picture of the list on your clipboard, the same as Copy image on the Decks tab.
- **Taskbar icon:** the decklist window and the dashboard show the app's icon on the taskbar, not Python's.
- **The chat goes away after the round.** Three minutes after the round is reported (or Limitless says the match has finished), the chat and the decklist icon hide. A new message or the next round's match brings them back.

## What's new in 2.14
Mostly for playing Limitless online tournaments.

- **Match chat over the game.** The newest messages show as outlined text over the game and fade after about 20 seconds. Rest the mouse on them to open the whole conversation and type a reply; Enter sends it to Limitless and hands the keyboard back to the game.
- **Friend requests to your opponent.** When a round starts, the app asks if you want to add your opponent as a friend. Once you're on the main menu it sends the request in Pokémon TCG Live by itself. It uses the opponent's in-game screen name from the match page, which is often different from their Limitless name. The game is dimmed while it works, and your mouse and keyboard are paused for those few seconds (Esc cancels).
- **Auto Friend Request** on the Limitless tab skips the question and just sends the request each round.
- **Your opponent's decklist in its own window.** When Limitless shows the opponent's list on the match page, it opens with the card scans and copy counts, in your theme. It has its own taskbar button, so you can minimize it separately. A small three-card icon above the chat opens it again, and clicking it again minimizes it.
- **Check-in reloads the page**, so Limitless shows you as checked in right away. Auto check-in tries a few times at most and only plays its sound once.
- **The HUD hides with the game.** Minimize Pokémon TCG Live and the mini HUD, chat and deck icon go with it, then come back when you restore the game.
- **Limitless tab:** Reload Dashboard is now a small refresh button on the right.
