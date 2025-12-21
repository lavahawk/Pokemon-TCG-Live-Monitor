# Overlay UI - Complete Redesign

## What Was Fixed

### ✅ 1. Click-Through Functionality
**Problem**: Overlay blocked all interaction with the game below it.

**Solution**: Added `Qt.WindowType.WindowTransparentForInput` flag to window properties. The overlay is now completely transparent to mouse clicks - you can click through it as if it's not there.

### ✅ 2. Game Window Following
**Problem**: Overlay stayed in a fixed screen position, didn't move with the game window.

**Solution**: 
- Added `find_game_window()` method that locates Pokemon TCG Live using win32gui
- Added `follow_game_window()` method that runs every second via QTimer
- Overlay now positions itself in the bottom-right corner of the game window with a 10px margin
- Automatically follows when the game window moves

### ✅ 3. Minimize Function Fixed
**Problem**: The old minimize/maximize just hid widgets but didn't resize the window frame, leaving an empty container.

**Solution**: Removed broken expand/collapse functionality entirely. The overlay is now always ultra-compact (140x24 pixels) showing only essential info in one line.

### ✅ 4. Professional Minimal Design
**Problem**: Emojis were "cringe", bright cyan (#00d4ff) was "ugly", overall too intrusive.

**Solution**:
- **Removed ALL emojis** - now uses plain text labels (R: for rank, Max: for max rank)
- **New color scheme**: Dark gray background (rgba(20,20,20,220)) with subtle gray border (rgba(80,80,80,180))
- **Muted text**: Light gray text (rgba(220,220,220,255)) instead of bright cyan
- **Smaller size**: Reduced from 260px wide to 140px wide, 24px tall
- **Subtle styling**: 4px border radius, minimal padding, professional appearance

### ✅ 5. Ultra-Compact Display
**Problem**: Old UI was too large and cluttered.

**Solution**: Single-line display showing only critical info:
```
R:76 | Max:82 | 5-2
```
- R: Current rank
- Max: Maximum rank achieved
- W-L: Today's wins-losses

## What It Does Now

1. **Follows Game Window**: Automatically positions in bottom-right corner of Pokemon TCG Live
2. **Click-Through**: Doesn't interfere with gameplay at all
3. **Auto-Updates**: Refreshes stats every 3 seconds
4. **Session Tracking**: Shows today's win-loss record from Excel
5. **Max Rank**: Tracks your highest rank achievement
6. **Minimal Size**: Only 140x24 pixels, stays out of the way

## How to Use

### Launch Overlay
```bash
python OverlayUI.py
```

Or use the batch file:
```bash
Start_Overlay.bat
```

### Full System (Monitor + Overlay)
```bash
Start_Complete_System.bat
```

The overlay will:
- Automatically find and attach to Pokemon TCG Live window
- Position itself in the bottom-right corner
- Update stats every 3 seconds
- Follow the game if you move the window
- Allow complete click-through (you can click the game through it)

## Technical Details

### Window Properties
- **FramelessWindowHint**: No title bar or borders
- **WindowStaysOnTopHint**: Always visible above game
- **Tool**: Lightweight window type
- **WindowTransparentForInput**: Click-through enabled
- **WA_TranslucentBackground**: Transparent background support

### Update Intervals
- **Stats Refresh**: Every 3 seconds
- **Position Update**: Every 1 second (follows game window)

### Dependencies
- PySide6 (Qt framework)
- win32gui (Windows API for window detection)
- win32process (Process information)
- psutil (Process utilities)
- pandas (Excel reading for stats)

## Comparison: Before vs After

| Feature | Old Overlay | New Overlay |
|---------|-------------|-------------|
| Click-through | ❌ Blocked clicks | ✅ Full click-through |
| Window following | ❌ Static position | ✅ Follows game |
| Minimize | ❌ Broken | ✅ Removed (always compact) |
| Design | ❌ Emojis, bright cyan | ✅ Professional, subtle |
| Size | 260x200+ pixels | 140x24 pixels |
| Intrusiveness | High | Minimal |

## Files Changed

- `OverlayUI.py` - Complete rewrite (215 lines → 215 lines, all new)
- All old documentation still applies for features/installation
- Launcher scripts unchanged

## Next Steps (Optional)

If you want even more features:
- Auto-hide when game loses focus
- Global hotkey to toggle visibility
- Notification toasts for battle completion
- Settings panel for customization
- Choose position (corners, edges)

Let me know if you want any of these added!
