# Modern Overlay UI Design for Pokemon TCG Live Monitor

## Research Summary

Based on successful game overlay implementations (RaidAssist for Destiny 2, Hearthstone Deck Tracker, etc.):

### Best Practices Found

1. **Framework**: **PySide6/PyQt6** (Qt framework)
   - Most common for Windows game overlays
   - Excellent transparency support
   - Window attachment capabilities
   - Hardware-accelerated rendering

2. **Window Behavior**:
   - Frameless window (`Qt.WindowType.FramelessWindowHint`)
   - Always on top (`Qt.WindowType.WindowStaysOnTopHint`)
   - Transparent background (`WA_TranslucentBackground`)
   - Draggable for repositioning
   - Optional click-through mode

3. **Modern Design Elements**:
   - Semi-transparent dark background (90% opacity)
   - Subtle border glow/accent colors
   - Smooth fade animations
   - Minimal, compact design
   - Easy collapse/expand
   - Hotkey toggle support

## Proposed Design for TCG Live Monitor

### UI Components

```
┌─────────────────────────────────────┐
│  🎮 TCG Live Monitor          [−][×]│  ← Header (draggable)
├─────────────────────────────────────┤
│  ✓ Battle Log Detected              │  ← Status indicator
│  🎯 Rank: 76                         │  ← OCR rank
│  🃏 Deck: Charizard ex               │  ← OCR deck name
├─────────────────────────────────────┤
│  📊 Session Stats:                   │
│  Wins: 3 | Losses: 1 | W/R: 75%     │
│  Time: 45m                           │
├─────────────────────────────────────┤
│  [📝 View Logs] [⚙️ Settings]       │  ← Action buttons
└─────────────────────────────────────┘
```

### Minimal/Collapsed Mode

```
┌───────────────────┐
│ TCG: 3-1 | R:76 [↕]│  ← Ultra compact
└───────────────────┘
```

### Technical Specifications

**Position**: 
- Attached to Pokemon TCG Live window
- Auto-repositions when window moves
- Option for screen corner fixed position

**Appearance**:
- Background: `rgba(26, 26, 26, 0.9)` (dark semi-transparent)
- Accent: `#00d4ff` (cyan, matching Pokemon blue)
- Border: 2px with subtle glow
- Rounded corners: 10px
- Font: Segoe UI, 10pt

**Features**:
- Real-time battle detection indicator
- OCR rank display (updates on menu detection)
- OCR deck name display
- Session statistics (from Excel)
- Notification toasts for events
- Minimize to system tray
- Global hotkey (Ctrl+Alt+M) to toggle

**Animations**:
- Fade in/out (200ms)
- Smooth expand/collapse (300ms)
- Pulsing indicator when detecting

## Implementation Plan

### Phase 1: Backend Integration (CURRENT)
- ✅ OCR rank detection working
- ✅ Menu validation working
- [ ] Integrate into TCGLiveMonitor.py
- [ ] Save to Excel with rank/deck

### Phase 2: Basic Overlay
- [ ] Create `OverlayUI.py` with PySide6
- [ ] Frameless, transparent window
- [ ] Draggable positioning
- [ ] Display rank, deck, status
- [ ] Minimize/maximize

### Phase 3: Advanced Features
- [ ] Attach to game window
- [ ] Auto-hide when game not focused
- [ ] System tray integration
- [ ] Hotkey support
- [ ] Notification toasts

### Phase 4: Full GUI Replace
- [ ] Settings panel in overlay
- [ ] Log viewer in overlay
- [ ] Statistics dashboard
- [ ] Replace all command-line prompts

## Recommended Libraries

```
PySide6==6.8.1           # Qt framework
pywin32==306             # Window management
keyboard==0.13.5         # Global hotkeys
plyer==2.1.0             # Cross-platform notifications
```

## Color Scheme

**Dark Theme** (Primary):
- Background: `#1a1a1a` (90% opacity)
- Text: `#ffffff`
- Accent: `#00d4ff` (Pokemon blue)
- Success: `#4caf50`
- Warning: `#ff9800`
- Error: `#f44336`

**Destiny-inspired Theme** (Alternative):
- Background: `#0d1421`
- Accent: `#f1c40f` (gold)
- Highlight: `#e74c3c` (red)

## Window Attachment Strategy

Two approaches:

### 1. Window-Relative Positioning (Recommended)
```python
import win32gui
import win32process

def find_game_window():
    hwnd = win32gui.FindWindow(None, "Pokémon TCG Live")
    if hwnd:
        rect = win32gui.GetWindowRect(hwnd)
        # Position overlay relative to game window
        return rect
```

### 2. Child Window Overlay (Advanced)
```python
# Set overlay as child of game window
win32gui.SetParent(overlay_hwnd, game_hwnd)
```

## User Experience Flow

1. **Launch**: Monitor starts in background
2. **Detection**: Battle log detected → notification toast
3. **Menu Return**: Wait for menu → OCR rank/deck
4. **Update**: Overlay updates with new info
5. **Stats**: Real-time W/L ratio, session time
6. **Minimize**: Collapse to tiny widget or tray

## Next Steps

1. ✅ Test validation (DONE)
2. **Integrate into workflow** (NEXT)
3. Create basic overlay prototype
4. Test with game running
5. Iterate on UX
