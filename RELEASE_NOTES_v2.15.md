# Pokemon TCG Live Monitor v2.15.4

## Install
Run **`PokemonTCGLiveMonitor-2.15.4-Free-Setup.exe`**. Install over any 2.x version; your battles and settings are kept. If SmartScreen warns you, click **More info → Run anyway** (the installer isn't signed). Windows 10/11, 64-bit.

## What's new in 2.15.4
- **A notice when your next round is up.** A small card at the top of the game shows the round and your opponent, with one ding. When Auto Check-In checks you in, the card flashes yellow and says so. It doesn't take the focus from the game and fades out after a few seconds (click it to close it sooner).
- **No need to open the Limitless tab.** Check-in and round detection run in the background as long as the app is open and you've signed in to Limitless once. Between rounds the app now keeps checking the dashboard every 10 seconds for over an hour after your last match, so the next pairing is found right away. Outside a tournament the hidden dashboard reloads every few minutes so it never goes stale.
- **Opponent decklist window:** the title just says the round ("ROUND 2"), and the cards sit straight on the window, without the inner panel, deck name and card counts.

## What's new in 2.15.3
- **The opponent decklist's see-through slider only fades the background.** It used to fade the whole window, cards and text included. It's now the same slider as on the dashboard, in the same spot at the bottom left: the glass and the panel behind the cards fade, and the cards, text and buttons stay solid. A resize grip sits at the bottom right, as on the dashboard.

## What's new in 2.15.2
- **Battle log export clicks are quicker and don't fight your mouse.** The app used to wait for your mouse to stop moving before each click (up to 1.5 seconds), then pin the cursor to the button. Now it clicks right away and pauses your mouse and keyboard only for the moment of the click, with the cursor hidden. That's about half a second per click, the same way friend requests work. Esc stops the export.
- The Continue cover never takes the focus from the game.

## What's new in 2.15.1
- **The Continue button is covered sooner after a battle.** On some PCs you could click Continue before the battle log was saved. The app now checks for the end of a battle about twice as often, and covers Continue even when another window has the focus. Before, clicking the game to bring it back pressed Continue too.
- **The cover stays up through the end-screen animation.** A brief match of the battle HUD on the end screen used to take the cover down just before BATTLE LOG showed. The HUD now has to be back for a full second.
- **Faster on PCs where the battle HUD isn't recognized.** Until the app has seen the HUD once, it looks for the end screen several times a second while the game has the focus, instead of every 1.5 seconds.

## What's new in 2.15.0
- **A tour for new installs.** The first time the HUD shows up over the game, a short tour starts. It points at the ▲ arrow, opens the app, and goes through each tab: your stats, the deck pages, Meta, In Person, the Limitless tools (check-in, friend requests, chat and decklists), TrainerHill, Japan Data, PokeData and the settings that matter most.
- **Example games during the tour.** The tour fills the app with a made-up Gardevoir deck (and a few Dragapult games) so every chart has something in it. They're kept in a separate file and are deleted when the tour ends or you skip it. Your own battles are never touched.
- **Skip it any time** with Skip tour or Esc. Arrow keys move back and forward.
- **See it again** from Settings → Startup → Show the tutorial again. If you already have battles saved, the tour doesn't start on its own after updating.
