# Pokemon TCG Live Monitor v2.15.11

## Install
Run **`PokemonTCGLiveMonitor-2.15.11-Free-Setup.exe`**. Install over any 2.x version; your battles and settings are kept. If SmartScreen warns you, click **More info → Run anyway** (the installer isn't signed). Windows 10/11, 64-bit.

## What's new in 2.15.11
- **A much bigger replay board, staggered so you can tell the sides apart.** The Replay tab hides the side panels and staggers the two boards: your opponent's up and to the left with a red outline, yours down and to the right with a blue one and a **You** tag, and the turn and stadium bar between them. Each hand sits in the corner beside its own board. The board resizes with the window to the biggest size that fits. **Side panels** (on the timeline) brings back the replay site's controls, card detail and action log; your choice is kept. If the replay site ever changes and the custom layout stops fitting, the tab falls back to the site's own layout on its own.
- **A replay timeline with highlights.** A bar across the bottom steps through the game one action at a time (click, drag, mouse wheel, or the arrow keys). It shows each turn, coloured by player, and marks the big moments: knock outs, prizes taken, attacks and evolutions. **◀ Highlight / Highlight ▶** (or Shift+arrows) jump between them, and hovering shows what happened at that point.
- The Replay tab's header row steps aside once a replay is loaded (more room for the board); **Open in browser** is on the timeline.
- **Thanks to:** the Support tab now credits the people behind the projects the app runs on (Robin Schulz and the Limitless team, serukaizen's replay viewer, Brad at TrainerHill, TCGCSV, TCGdex, PokeData and more), with links to their sites, socials and Patreon or Ko-fi pages.

## What's new in 2.15.10
- **Fewer antivirus false alarms.** Updates no longer run the installer invisibly from the Temp folder: the download goes to the app's own folder in AppData and the installer shows its progress window while it updates. The installer stops the running app without starting PowerShell, and 39 unused helper programs that came with Python's packages (pip.exe and the like) are no longer installed. Everything works as before. If you'd rather updates install with no window at all, turn on **Settings → Advanced → Install updates in the background**.
- **Settings are easier to find.** Six sections, the everyday ones first: General, Battle tracking, Startup & updates (the update check and version now live here), Your data, Stats & meta, and Advanced (background updates, OCR debug, tools, closing the app).
- Fixed: Settings → OCR Bounding Box Debug → **Open end-of-battle pictures** opened the tournament screenshots folder since 2.15.9.

## What's new in 2.15.9
- **Auto Screenshot of end screens.** After each Limitless tournament game, the app saves a picture of the end screen (the one with the Battle Log button) before it exports the log, as proof of the result. The pictures go to **Pictures \ TCG Live Monitor \ End screens**, named by date and opponent. It's on by default; turn it off with **Auto Screenshot** on the Limitless tab, and the folder button next to it opens the pictures. It needs the battle log auto-export on.
- **The opponent decklist opens where you left it.** It keeps its last position and size from round to round (the first time it opens centered, sized to the deck).

## What's new in 2.15.8
- **Auto Report works when your opponent reports first.** If they reported before you, the app used to think the match was over and skip your report. It now checks the match chat to see whether *you* have reported, and reports the game you haven't. If Limitless has already closed the match (a loss report settles it), the app leaves it alone instead of showing a "couldn't report" notice.

## What's new in 2.15.7
- **Auto Report.** After a Limitless tournament game, the app reports your win or loss on your match page by itself, using the result from the battle log, and the in-game notice flashes yellow to say what it reported. It's on by default; turn it off with **Auto Report** on the Limitless tab, and the app asks first instead ("You won game 1 against … Report it?"), with a button for the other result in case the log got it wrong. You don't need the Limitless tab open. In a best of three, each game is reported in turn. If the report doesn't show up on Limitless, the notice tells you to report it on the match page.
- **Notices and the chat don't cover each other.** The cards above the HUD (the opponent's deck, Reset?, concede question, manual-mode and update notices, friend request and report questions) stack in a fixed order, and the match chat always sits above them.

## What's new in 2.15.6
- **Deck names are read more accurately from the main menu.** The app now reads a slightly bigger area around the name (long names used to be cut off, and so were the bottoms of letters like g and y). It enlarges the text to the same size at any window size, smooths out the dotted background, and reads it as a single line. On test pictures at 1920x1080 it got every name right, up from about 8 in 10. Captures that aren't a deck name (another screen in the way) are no longer saved as one.
- **New installs start see-through:** the dashboard's background starts at 75 % and the opponent decklist's at 50 % (its slider now goes down to 30 %). If you've already moved a slider, your setting is kept.

## What's new in 2.15.5
- **Limitless page buttons work in the app.** On the Limitless tab, **Open as Image** and the card links used to do nothing, because they open a new tab. They now open in a small window in the app's style (with its own taskbar button). Links to other sites (Docs, Discord, X) open in your browser. Limitless's Copy buttons can use the clipboard, downloads save to your Downloads folder, and Limitless's own notifications show as the in-game notice.
- **Opponent decklist title:** the round and whose deck it is, e.g. "ROUND 2 · LEBOBBO'S DECK".

## What's new in 2.15.4
- **A notice when your next round is up.** A small card at the top of the game shows the round and your opponent, with one ding. When Auto Check-In checks you in, the card flashes yellow and says so. It doesn't take the focus from the game and fades out after a few seconds (click it to close it sooner).
- **No need to open the Limitless tab.** Check-in and round detection run in the background as long as the app is open and you've signed in to Limitless once. Between rounds the app now keeps checking the dashboard every 10 seconds for over an hour after your last match, so the next pairing is found right away. Outside a tournament the hidden dashboard reloads every few minutes so it never goes stale.
- **Opponent decklist window:** the cards sit straight on the window, without the inner panel, deck name and card counts.

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
