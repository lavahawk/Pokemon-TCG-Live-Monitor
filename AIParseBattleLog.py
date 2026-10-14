import json
import os
import re
import sys
import time
import warnings

import openpyxl
import pyperclip
from pydantic import BaseModel

from BattleDatabase import BattleDatabase, log_hash
from app_settings import (
    is_ai_anonymize_names,
    is_local_only_mode,
    load_api_key,
    load_username,
    save_username,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(BASE_DIR, "TCGExampleSheet.xlsx")
DECK_SHEET = "Limitless Meta"
LIMITLESS_STANDARD_CACHE_FILE = os.path.join(BASE_DIR, ".meta_cache_limitless_standard.json")
LAST_DECK_FILE = os.path.join(BASE_DIR, ".last_deck")
LAST_RANK_FILE = os.path.join(BASE_DIR, ".last_rank")
LOG_DIR = os.path.join(BASE_DIR, "Logs")
# Shared flag file written by the Limitless dashboard manager (StatsUI) when
# the player is actively in a tournament match. Contains JSON:
#   {"in_tournament": true, "opponent": "<opponent username>"}
TOURNAMENT_FLAG_FILE = os.path.join(BASE_DIR, ".in_tournament")
# Shared capture file written by the Limitless dashboard manager (StatsUI)
# containing the current match's chat (with round info). Read when saving a
# battle so the chat can be reviewed alongside the game data.
CHAT_CAPTURE_FILE = os.path.join(BASE_DIR, ".chat_capture.json")

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

db = BattleDatabase()

# A tournament flag older than this is ignored (the Limitless manager may not
# have cleared it, e.g. if the app was closed mid-tournament).
TOURNAMENT_FLAG_MAX_AGE_S = 3 * 3600


def load_tournament_state():
    """Read the shared tournament flag file written by the Limitless manager.

    Returns a dict {"in_tournament": bool, "opponent": str} or an empty dict
    if no tournament match is currently active.
    """
    if not os.path.exists(TOURNAMENT_FLAG_FILE):
        return {}
    try:
        if time.time() - os.path.getmtime(TOURNAMENT_FLAG_FILE) > TOURNAMENT_FLAG_MAX_AGE_S:
            return {}
        with open(TOURNAMENT_FLAG_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict) and payload.get("in_tournament"):
            return {
                "in_tournament": True,
                "opponent": str(payload.get("opponent") or "").strip(),
            }
    except Exception:
        pass
    return {}


def parse_opponent_from_log(battlelog, username):
    """Return the opponent's username from a battle log (or None).

    Player names are taken from whole-line turn headers ("<name>'s Turn" /
    "Turn # N - <name>'s Turn") and the coin-flip lines, so names containing
    dots, spaces or accented characters work.
    """
    if not battlelog or not username:
        return None
    own = normalize_name(username)
    for candidate in log_player_names(battlelog):
        if normalize_name(candidate) != own:
            return candidate
    return None


def log_player_names(battlelog):
    """Every player name seen in the log's turn headers and coin-flip lines."""
    candidates = []
    text = (battlelog or "").replace("\r\n", "\n")
    patterns = (
        r"(?m)^Turn #\s*\d+\s*-\s*(.+?)'s Turn\s*$",
        r"(?m)^(?!Turn #)(.{1,40})'s Turn\s*$",
        r"(?m)^(.{1,40}?) chose (?:heads|tails) for the opening coin flip",
        r"(?m)^(.{1,40}?) won the coin toss",
        r"(?m)^(.{1,40}?) decided to go (?:first|second)",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text):
            name = match.strip()
            if name and name not in candidates:
                candidates.append(name)
    return candidates


# Placeholders used when names are stripped before sending a log to OpenAI.
# "Opponent" matches the game's own wording ("Opponent conceded. X wins.").
AI_SELF_PLACEHOLDER = "Player"
AI_OPPONENT_PLACEHOLDER = "Opponent"


def anonymize_battlelog(battlelog, username):
    """Replace both usernames in a log with Player / Opponent placeholders.

    The user's own name becomes AI_SELF_PLACEHOLDER; every other player name
    found in the log becomes AI_OPPONENT_PLACEHOLDER. Matches are whole-name
    only (not inside card names), longest name first.
    """
    if not battlelog:
        return battlelog
    own = normalize_name(username) if username else ""
    mapping = {}
    for name in log_player_names(battlelog):
        is_self = bool(own) and normalize_name(name) == own
        mapping[name] = AI_SELF_PLACEHOLDER if is_self else AI_OPPONENT_PLACEHOLDER
    if username and username.strip():
        mapping.setdefault(username.strip(), AI_SELF_PLACEHOLDER)
    text = battlelog
    for name in sorted(mapping, key=len, reverse=True):
        if name in (AI_SELF_PLACEHOLDER, AI_OPPONENT_PLACEHOLDER):
            continue
        text = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)",
                      lambda _m, repl=mapping[name]: repl, text, flags=re.IGNORECASE)
    return text


def is_tournament_battle(battlelog, username):
    """Determine whether a battle is a Limitless tournament game.

    A battle is only tagged as a tournament game if the player is actively in
    a tournament match (per the shared flag file) AND the battle-log opponent
    matches the tournament opponent. This prevents false positives from simply
    being enrolled in a tournament days in advance.
    """
    state = load_tournament_state()
    if not state.get("in_tournament"):
        return False
    tournament_opponent = state.get("opponent")
    if not tournament_opponent:
        # No opponent known — be conservative and don't tag.
        return False
    log_opponent = parse_opponent_from_log(battlelog, username)
    if not log_opponent:
        return False
    return normalize_name(log_opponent) == normalize_name(tournament_opponent)


def prompt_string(title, prompt, *, secret=False):
    if _console_available():
        return input(f"{prompt}\n> ").strip()
    from qt_dialogs import ask_string
    return ask_string(title, prompt, secret=secret)


def ensure_username():
    username = load_username()
    if username:
        return username
    username = prompt_string(
        "Enter Your TCG Live Username",
        "No username was found.\n\nPlease enter your TCG Live username:",
    )
    if username:
        save_username(username.strip())
    return (username or "").strip()


def load_meta_rows():
    """Rows of the meta sheet (.meta_cache_limitless_standard.json), or []."""
    try:
        with open(LIMITLESS_STANDARD_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def card_evidence(battlelog, username, rows=None):
    """What the opponent's revealed cards say about their deck.

    Returns {"cards": set of card names they showed, "pokemon": the Pokemon
    among them, "ranked": [(archetype, probability)] best first} using the
    card usage of public decklists in the meta sheet (card_usage.classify).
    Empty when the sheet has no card data yet."""
    empty = {"cards": set(), "pokemon": set(), "ranked": [], "explain": ""}
    rows = rows if rows is not None else load_meta_rows()
    if not battlelog or not any(r.get("cards") for r in rows):
        return empty
    try:
        import card_usage
        card_usage.set_known_cards(c["name"] for r in rows for c in r.get("cards") or [])
        opponent = parse_opponent_from_log(battlelog, username)
        copies = card_usage.log_card_counts(battlelog, opponent, username)
        seen = set(copies)
        pokemon_names = {c["name"] for r in rows for c in r.get("cards") or [] if c.get("cat") == "P"}
        ranked_rows = card_usage.classify(copies, rows)
        return {"cards": seen, "pokemon": seen & pokemon_names, "copies": copies,
                "ranked": [(r["deck"], p) for r, p in ranked_rows],
                "explain": card_usage.explain(ranked_rows, copies, rows)}
    except Exception as exc:
        print(f"[Cards] evidence failed: {exc}")
        return empty


def _deck_words(name):
    return {w for w in re.findall(r"[a-z]+", (name or "").lower())
            if w not in ("ex", "mega", "with", "box", "and", "s", "the", "deck", "control", "toolbox")}


def deck_fits_cards(deck, pokemon_seen):
    """True when every Pokemon word in a deck name shows up among the
    Pokemon the opponent revealed ("Dragapult Dusknoir" needs both)."""
    words = _deck_words(deck)
    seen = set().union(*(_deck_words(p) for p in pokemon_seen)) if pokemon_seen else set()
    return bool(words) and words <= seen


CARD_PICK_MIN = 0.85  # a card-based pick replaces an AI name that contradicts the cards


def load_possible_decks():
    cache_rows = load_meta_rows()

    if cache_rows:
        ranked = sorted(
            cache_rows,
            key=lambda row: int((row or {}).get("count", 0) or 0),
            reverse=True,
        )
        names = []
        seen = set()
        for row in ranked:
            deck_name = str((row or {}).get("deck") or "").strip()
            if not deck_name or deck_name.lower() == "other":
                continue
            normalized = normalize_name(deck_name)
            if normalized in seen:
                continue
            seen.add(normalized)
            names.append(deck_name)
            if len(names) >= 50:
                break
        if names:
            return names

    if not os.path.exists(EXCEL_FILE):
        return []
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                message="Pyarrow will become a required dependency of pandas.*",
            )
            import pandas as pd
        deck_df = pd.read_excel(EXCEL_FILE, DECK_SHEET, usecols="B", skiprows=0, nrows=60)
        return [str(value).strip() for value in deck_df.iloc[:, 0].dropna().tolist() if str(value).strip()]
    except Exception:
        return []


def normalize_name(value):
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


RESULT_PREFIXES = (
    "All Prize cards taken.",
    "Opponent conceded.",
    "You conceded.",
    "Opponent took all of their Prize cards.",
    "No Benched Pokémon for backup.",
    "Knocked Out with no Benched Pokémon.",
    "Opponent was inactive for too long.",
    "You were inactive for too long.",
)


def _result_line(battlelog):
    lines = [line.strip() for line in (battlelog or "").replace("\r\n", "\n").split("\n") if line.strip()]
    for line in reversed(lines):
        if line.endswith(" wins."):
            return line
    return None


def parse_winner_from_log(battlelog, username=None):
    """Return the winner's name from the final '<...>. <name> wins.' line.

    Names may contain dots, spaces or non-ASCII characters (BUG-023), so the
    known result sentences are stripped instead of guessing name characters.
    If the player's own username is given and the line ends with it as a whole
    name (after a sentence, not "MrAsh" for "Ash"), that name is returned exactly.
    """
    line = _result_line(battlelog)
    if not line:
        return None
    body = line[: -len(" wins.")].strip()
    own = (username or "").strip()
    if own and body.casefold().endswith(own.casefold()):
        before = body[: -len(own)].rstrip(" ")
        known = any(body.startswith(prefix) for prefix in RESULT_PREFIXES)
        if not before or before in RESULT_PREFIXES or (not known and before.endswith(".")):
            return own
    for prefix in RESULT_PREFIXES:
        if body.startswith(prefix):
            return body[len(prefix):].strip() or None
    # Unknown sentence before the name: take the text after the last ". "
    return body.rsplit(". ", 1)[-1].strip() or None


def parse_result_from_log(battlelog, username):
    winner = parse_winner_from_log(battlelog, username)
    if not winner or not username:
        return None
    return "Win" if normalize_name(winner) == normalize_name(username) else "Loss"


def load_last_deck():
    if not os.path.exists(LAST_DECK_FILE):
        return None
    try:
        with open(LAST_DECK_FILE, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
        return value or None
    except Exception:
        return None


def load_last_rank():
    if not os.path.exists(LAST_RANK_FILE):
        return None
    try:
        with open(LAST_RANK_FILE, "r", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except Exception:
        return None


def latest_log_file():
    if not os.path.isdir(LOG_DIR):
        return None
    log_files = [f for f in os.listdir(LOG_DIR) if f.startswith("battle_log_") and f.endswith(".txt")]
    if not log_files:
        return None
    log_files.sort(reverse=True)
    return os.path.join(LOG_DIR, log_files[0])


def read_battlelog_file(file_path):
    if not file_path:
        return None
    for encoding in ("utf-8", "cp1252"):
        try:
            with open(file_path, "r", encoding=encoding) as handle:
                return handle.read().strip()
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


def save_to_excel(my_deck, opponents_deck, win_or_loss):
    workbook = openpyxl.load_workbook(EXCEL_FILE)
    sheet_name = re.sub(r"[\\/*?:\[\]]", "-", (my_deck or "Unknown Deck")).strip("'")[:31] or "Unknown Deck"
    sheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.create_sheet(title=sheet_name)

    next_row = 1
    while sheet.cell(row=next_row, column=1).value is not None:
        next_row += 1

    sheet.cell(row=next_row, column=1).value = win_or_loss
    sheet.cell(row=next_row, column=2).value = opponents_deck
    workbook.save(EXCEL_FILE)


def load_chat_capture():
    """Read the current match's chat capture written by the Limitless manager.

    Returns a dict {"round": int|None, "opponent": str, "messages": [str]} or
    an empty dict if no chat capture exists.
    """
    if not os.path.exists(CHAT_CAPTURE_FILE):
        return {}
    try:
        with open(CHAT_CAPTURE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            messages = []
            for m in (payload.get("messages") or []):
                if isinstance(m, dict):
                    text = str(m.get("text") or "").strip()
                else:
                    text = str(m).strip()
                if text:
                    messages.append(text)
            return {
                "round": payload.get("round"),
                "opponent": str(payload.get("opponent") or "").strip(),
                "messages": messages,
            }
    except Exception:
        pass
    return {}


def save_to_database(my_deck, opponents_deck, win_or_loss, confidence, log_file_path=None, is_tournament=False,
                     battle_hash=None, deck_source=None):
    # Attach the current match's chat (if any) to the battle record so it can
    # be reviewed alongside the game data.
    chat_capture = load_chat_capture()
    chat_log = None
    if chat_capture.get("messages"):
        chat_log = json.dumps(chat_capture, ensure_ascii=False)
    return db.add_battle(
        my_deck=my_deck,
        opponent_deck=opponents_deck,
        result=win_or_loss,
        my_rank=load_last_rank(),
        confidence=confidence,
        deck_source=deck_source or ("AI" if not is_local_only_mode() and load_api_key() else "Local"),
        log_file=os.path.abspath(log_file_path) if log_file_path else latest_log_file(),
        is_tournament=is_tournament,
        chat_log=chat_log,
        log_hash=battle_hash,
    )


def _console_available():
    """True when an interactive console/stdin is usable for prompts.

    When the monitor runs headless (pythonw / hidden window), stdin is not a
    TTY and prompting would block forever, silently preventing the battle
    from being saved. Tk dialogs would also hang with no user visible UI.
    """
    if os.environ.get("PTCGL_NO_PROMPT"):
        # Run by the monitor: stdout is captured, so a prompt would be invisible.
        return False
    try:
        return bool(sys.stdin is not None and sys.stdin.isatty())
    except Exception:
        return False


def local_fallback_parse(battlelog, username):
    my_deck = load_last_deck()
    if not my_deck and _console_available():
        my_deck = prompt_string(
            "Enter Your Deck",
            "Local-only mode could not find your deck from OCR.\n\nPlease enter your deck name:",
        )

    # The opponent's deck is asked for by the overlay's "Opponent deck" card
    # after saving (deck_confirm.py); store the best guess until then. The
    # cards they revealed vs public decklists beat "first Pokemon played".
    evidence = card_evidence(battlelog, username)
    card_pick = evidence["ranked"][0] if evidence["ranked"] else None
    if card_pick and card_pick[1] >= 0.5:
        print(f"[Cards] {card_pick[0]} ({card_pick[1] * 100:.0f}%) from {len(evidence['cards'])} revealed cards")
        # A clear pick is shown as CARDS; a close call is a GUESS the overlay asks you to confirm.
        firm = card_pick[1] >= CARD_PICK_MIN and deck_fits_cards(card_pick[0], evidence["pokemon"])
        inferred, source = card_pick[0], ("cards" if firm else "guess")
    else:
        inferred, source = infer_opponent_deck_from_log(battlelog), "guess"
    opponents_deck = inferred or "Unknown (local mode)"

    win_or_loss = parse_result_from_log(battlelog, username)
    if not win_or_loss and _console_available():
        win_or_loss = prompt_string(
            "Enter Result",
            "The battle result could not be inferred from the log.\n\nEnter Win or Loss:",
        )
    if not win_or_loss:
        win_or_loss = "Loss"

    # Opponent-deck certainty: the cards' probability, a low number for a
    # "first Pokemon played" guess, 0 when there's nothing to go on.
    if card_pick and inferred == card_pick[0]:
        confidence = int(round(card_pick[1] * 100))
    else:
        confidence = 35 if inferred else 0

    return {
        "My_deck": (my_deck or "").strip() or "Unknown Deck",
        "OpponentsDeck": (opponents_deck or "").strip(),
        "Win_or_Loss": (win_or_loss or "").strip().title(),
        "Confidence": confidence,
        "deck_source": source if inferred else "none",
        "Candidates": merge_candidates(inferred, confidence / 100.0 if inferred else None, [], evidence["ranked"]),
    }


def infer_opponent_deck_from_log(battlelog):
    """Best-effort guess of the opponent's deck from cards they played.

    Local mode has no AI, so look for the opponent's first Basic Pokemon
    played to the Active Spot as the likely deck archetype.
    """
    if not battlelog:
        return None
    opponent = parse_opponent_from_log(battlelog, load_username())
    if not opponent:
        return None
    own = re.escape(opponent)
    matches = re.findall(
        rf"(?m)^{own} played ([\w'\-. ]+?)(?: ex| V| VMAX| VSTAR)? to the Active Spot",
        battlelog.replace(chr(13), ""),
        flags=re.IGNORECASE,
    )
    if matches:
        return matches[0].strip()
    return None


class BattleLogOutput(BaseModel):
    My_deck: str
    OpponentsDeck: str
    Win_or_Loss: str
    Confidence: int


def _flatten_scalar(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, list):
        for item in value:
            flattened = _flatten_scalar(item)
            if flattened not in (None, ""):
                return flattened
        return None
    if isinstance(value, dict):
        for key in ("value", "score", "confidence", "percent", "percentage", "raw", "text"):
            if key in value:
                flattened = _flatten_scalar(value.get(key))
                if flattened not in (None, ""):
                    return flattened
        for nested in value.values():
            flattened = _flatten_scalar(nested)
            if flattened not in (None, ""):
                return flattened
        return None
    return str(value).strip()


def _coerce_text_field(payload, *keys):
    for key in keys:
        if key not in payload:
            continue
        flattened = _flatten_scalar(payload.get(key))
        if flattened is None:
            continue
        text = str(flattened).strip()
        if text:
            return text
    return ""


def _coerce_candidates(payload):
    """The AI's "Candidates": [(deck, probability 0-1 or None)], best first."""
    raw = payload.get("Candidates") or payload.get("candidates") or []
    if isinstance(raw, dict):
        raw = [{"deck": k, "probability": v} for k, v in raw.items()]
    out = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict):
            name = _coerce_text_field(item, "deck", "Deck", "name", "archetype")
            p = _coerce_confidence_value(item.get("probability", item.get("confidence", item.get("p"))), default=-1)
            p = None if p < 0 else p / 100.0
        else:
            name, p = item, None
        name = " ".join(str(name or "").split())
        if name:
            out.append((name, p))
    return out


def merge_candidates(primary, primary_p, alternatives, ranked, limit=3):
    """Up to `limit` (deck, probability or None) for the overlay's multiple
    choice: the pick first, then the AI's alternatives, then the card-evidence
    ranking. A missing probability is taken from the card evidence."""
    card_p = {deck.casefold(): p for deck, p in ranked}
    out, seen = [], set()
    for name, p in [(primary, primary_p)] + list(alternatives) + list(ranked):
        name = " ".join(str(name or "").split())
        key = name.casefold()
        if not name or key in seen or key.startswith("unknown"):
            continue
        seen.add(key)
        out.append((name, p if p is not None else card_p.get(key)))
        if len(out) >= limit:
            break
    return out


def deck_confidence(ai_confidence, deck, ranked):
    """0-100 certainty of the opponent deck. With card evidence it's the mean
    of the AI's own number and the cards' probability for that deck (an AI
    pick the cards don't support drops sharply); without, the AI's number."""
    if not ranked:
        return int(ai_confidence)
    card_p = dict((d.casefold(), p) for d, p in ranked).get(" ".join(str(deck or "").split()).casefold(), 0.0)
    return int(round((ai_confidence + 100 * card_p) / 2))


def _coerce_confidence_value(value, default=0):
    flattened = _flatten_scalar(value)
    if flattened is None or flattened == "":
        return int(default)
    if isinstance(flattened, bool):
        return 100 if flattened else int(default)
    if isinstance(flattened, (int, float)):
        numeric = float(flattened)
    else:
        match = re.search(r"-?\d+(?:\.\d+)?", str(flattened))
        if not match:
            return int(default)
        numeric = float(match.group(0))
    return max(0, min(100, int(round(numeric))))


# Recent OpenAI model used for battle-log parsing. Falls back to older models
# if the primary is unavailable (e.g. revoked or renamed).
AI_MODELS = [
    "gpt-5.4-nano-2026-03-17",
    "gpt-4.1-mini",
    "gpt-4o",
]


def ai_parse(battlelog, username, api_key, anonymize=None, client=None):
    if client is None:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=45.0, max_retries=1)
    possible_decks = load_possible_decks()
    # Card evidence is computed locally from the real log and names.
    evidence = card_evidence(battlelog, username)
    if anonymize is None:
        anonymize = is_ai_anonymize_names()
    you_note = ""
    if anonymize:
        # SEC-09: neither username leaves the machine. "Player" is the user,
        # so My_deck / Win_or_Loss keep their meaning in the reply.
        battlelog = anonymize_battlelog(battlelog, username)
        username = AI_SELF_PLACEHOLDER
        you_note = (f"Player names are anonymized: \"{AI_SELF_PLACEHOLDER}\" (also \"You\" in the log) is me, "
                    f"\"{AI_OPPONENT_PLACEHOLDER}\" is the opponent.\n")
    evidence_text = ""
    if evidence["pokemon"]:
        # ~150 tokens: what the opponent showed (with copies) and how each
        # candidate's usual tournament list explains it - e.g. 1 Zoroark ex is
        # a tech in a Gengar list, 4 make it a Zoroark deck.
        evidence_text = (
            "\nCard evidence (from the log and ~95,000 tournament decklists; percentages = how likely "
            "each archetype is given ALL the opponent's cards and their copy counts):\n"
            + (evidence["explain"] or f"Opponent revealed: {sorted(evidence['pokemon'])}") + "\n"
            + "Name the opponent's deck by its main line (the Pokemon with the most copies that the "
            "archetype is built around), not by a 1-2 copy tech. Prefer a candidate name above when it fits. "
            "In a close call between candidates, pick the more popular one (it is far more likely to be met).\n"
            + f"{username}'s own cards are NOT evidence for the opponent's deck.\n")
    prompt = f"""
You are identifying Pokemon TCG deck archetypes from an official battle log.

Here is the current top-deck list from the latest Limitless scrape, ordered by
how many tournament finishes each has (most popular first). This list is fresh
from today's data:
{possible_decks}

STRICT RULES for deck identification:
1. Identify each deck by its KEY Pokemon cards that actually appear in the log
   (played, drawn, held, or discarded). The deck name is usually its main
   attacker, but sometimes it is named for its engine/support Pokemon instead.
2. Prefer an EXACT match from the list above when the evidence supports it.
3. NEVER name a Pokemon that does not appear anywhere in the log. If the log
   shows Dragapult and Dusknoir but zero Blaziken cards, the answer CANNOT be
   a Blaziken deck.
4. Support/Item/Engine cards (Buddy-Buddy Poffin, Capturing Aroma, etc.) do
   not define the archetype — the Pokemon line does.
5. If no list entry matches the evidence, output the best descriptive
   archetype name yourself (e.g. "Dragapult Dusknoir") rather than forcing a
   wrong match.
6. "My_deck" is {username}'s deck; "OpponentsDeck" is the opponent's.
7. If no battlelog was provided, return blank fields.

Also determine the winner of the battle.
"Confidence" = how likely (0-100) OpponentsDeck is right. Be honest: use the
card evidence, and go low when the opponent showed little or it's a close call.
"Candidates" = the 3 most likely opponent archetypes, best first (the first is
OpponentsDeck), each {{"deck": name, "probability": 0-100}}, summing to <= 100.
{evidence_text}{you_note}
Export the data as JSON with these fields: My_deck, OpponentsDeck, Win_or_Loss, Confidence, Candidates
Battlelog:
<<<BEGIN BATTLELOG>>>
{battlelog}
<<<END BATTLELOG>>>
"""

    last_error = None
    for model in AI_MODELS:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You parse Pokemon TCG battle logs and return JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            payload = json.loads(completion.choices[0].message.content)
            parsed = BattleLogOutput(
                My_deck=_coerce_text_field(payload, "My_deck", "MyDeck", "my_deck"),
                OpponentsDeck=_coerce_text_field(payload, "OpponentsDeck", "OpponentDeck", "opponent_deck", "Opponent"),
                Win_or_Loss=_coerce_text_field(payload, "Win_or_Loss", "WinLoss", "Result", "result").title(),
                Confidence=_coerce_confidence_value(payload.get("Confidence")),
            )
            print(f"[AI] Parsed using model: {model}")
            alternatives = _coerce_candidates(payload)
            result = {
                "My_deck": parsed.My_deck,
                "OpponentsDeck": parsed.OpponentsDeck,
                "Win_or_Loss": parsed.Win_or_Loss,
                "Confidence": deck_confidence(parsed.Confidence, parsed.OpponentsDeck, evidence["ranked"]),
                "deck_source": "ai",
            }
            # Cross-check: an AI name whose Pokemon the opponent never showed,
            # while the revealed cards clearly point to one archetype (seen in
            # real logs: the AI named the user's own deck).
            pick = evidence["ranked"][0] if evidence["ranked"] else None
            if (pick and pick[1] >= CARD_PICK_MIN and evidence["pokemon"]
                    and not deck_fits_cards(parsed.OpponentsDeck, evidence["pokemon"])
                    and deck_fits_cards(pick[0], evidence["pokemon"])):
                print(f"[Cards] AI said {parsed.OpponentsDeck!r}, but the opponent's cards say "
                      f"{pick[0]} ({pick[1] * 100:.0f}%) - using the cards.")
                result.update(OpponentsDeck=pick[0], Confidence=int(round(pick[1] * 100)), deck_source="cards")
            result["Candidates"] = merge_candidates(result["OpponentsDeck"], result["Confidence"] / 100.0,
                                                    alternatives, evidence["ranked"])
            return result
        except Exception as exc:
            last_error = exc
            print(f"[AI] Model {model} failed: {exc}. Trying next...")
    raise last_error


def main():
    username = ensure_username()
    explicit_log_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    if explicit_log_path:
        battlelog = read_battlelog_file(explicit_log_path)
    else:
        # Manual run (dashboard button): clipboard first, then newest saved log.
        battlelog = pyperclip.paste()
        if not battlelog:
            explicit_log_path = latest_log_file()
            battlelog = read_battlelog_file(explicit_log_path)
    if not battlelog:
        print("No battle log found.")
        return

    battle_hash = log_hash(battlelog)
    if db.has_log_hash(battle_hash):
        print("DUPLICATE: this battle log is already in the database.")
        return

    settings_local_only = is_local_only_mode()
    api_key = load_api_key()
    use_local_only = settings_local_only or not api_key

    if use_local_only:
        if settings_local_only:
            print("Local-only mode is enabled. Falling back to manual opponent deck entry.")
        else:
            print("No OpenAI API key found. Falling back to local-only parsing.")
        response_dict = local_fallback_parse(battlelog, username)
    else:
        try:
            response_dict = ai_parse(battlelog, username, api_key)
        except Exception as exc:
            print(f"AI parse failed: {exc}")
            print("Falling back to local-only parsing.")
            response_dict = local_fallback_parse(battlelog, username)

    my_deck = response_dict.get("My_deck") or "Unknown Deck"
    opponents_deck = response_dict.get("OpponentsDeck") or "Unknown"
    win_or_loss = (response_dict.get("Win_or_Loss") or "Loss").title()
    confidence = int(response_dict.get("Confidence") or 0)

    # The battle log is AUTHORITATIVE for the result. The AI's Win_or_Loss is
    # only a guess from card evidence and has been observed to disagree with
    # the log's explicit "... wins." line, corrupting the record. If the log
    # yields a definitive winner, it always wins over the AI's answer.
    log_result = parse_result_from_log(battlelog, username)
    if log_result and log_result != win_or_loss:
        print(
            f"[Result] AI said {win_or_loss} but the battle log shows "
            f"'{parse_winner_from_log(battlelog)} wins.' — trusting the log ({log_result})."
        )
        win_or_loss = log_result
    # `confidence` is the opponent-deck certainty only (it used to be bumped
    # to 90-95 whenever the log confirmed the result, so it always read ~90).

    # Prefer the OCR-detected deck name (from the main menu) over the
    # AI-suggested name. OCR is authoritative for YOUR deck because it reads
    # the actual deck name on screen, whereas the AI infers it from the log.
    ocr_deck = load_last_deck()
    if ocr_deck:
        my_deck = ocr_deck

    print("--------------------------")
    print(
        f"My Deck: {my_deck}  |  Opponent's Deck: {opponents_deck}  |  "
        f"Result: {win_or_loss}  |  Confidence: {confidence}%"
    )
    print("--------------------------")

    try:
        if os.path.exists(EXCEL_FILE):
            save_to_excel(my_deck, opponents_deck, win_or_loss)
            print("Saved successfully to workbook.")
    except Exception as exc:
        print(f"Warning: Could not update workbook: {exc}")

    tournament = False
    try:
        tournament = is_tournament_battle(battlelog, username)
    except Exception as exc:
        print(f"Tournament check failed: {exc}")

    try:
        deck_source = response_dict.get("deck_source") or "none"
        if deck_source in ("ai", "cards") and not (response_dict.get("OpponentsDeck") or "").strip():
            deck_source = "none"  # no deck: ask on the overlay card
        battle_id = save_to_database(my_deck, opponents_deck, win_or_loss, confidence, explicit_log_path,
                                     is_tournament=tournament, battle_hash=battle_hash,
                                     deck_source={"ai": "AI", "cards": "Cards"}.get(deck_source, "Local"))
        if battle_id:
            print(f"Battle saved to database{' (Limitless tournament)' if tournament else ''}.")
            print(f"BATTLE_ID={battle_id}")
            try:
                # Overlay card: shows the AI's pick (click to fix) or asks for the deck.
                from deck_confirm import write_request
                write_request(battle_id, opponents_deck, source=deck_source,
                              needs_input=deck_source not in ("ai", "cards"),
                              my_deck=my_deck, result=win_or_loss, confidence=confidence,
                              candidates=response_dict.get("Candidates") or [])
            except Exception as exc:
                print(f"Warning: Could not request the deck confirmation card: {exc}")
            try:
                from decklists import capture_from_games
                captured = capture_from_games(my_deck, username)
                if captured and captured.get("entry"):
                    print(f"[Decklist] all 60 cards of {my_deck} seen: list saved and linked.")
            except Exception as exc:
                print(f"Warning: decklist auto-capture failed: {exc}")
        else:
            print("DUPLICATE: this battle log is already in the database.")
    except Exception as exc:
        print(f"Warning: Could not save to database: {exc}")


if __name__ == "__main__":
    main()
