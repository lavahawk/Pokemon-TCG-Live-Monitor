"""
Deck share links: a whole PTCGL decklist packed into a short link, no server.

    https://lavahawk.github.io/Pokemon-TCG-Live-Monitor/d#a<token>~<deck name>
    ptcglmonitor://d#a<token>~<deck name>

The token is the list itself, so the link works with nothing stored anywhere:
the web page (docs/d/) decodes it in the browser and hands it to the app
through the ptcglmonitor:// scheme; the app decodes it too, so a pasted or
copied link still works when the page is down. Browsers never send the part
after '#' to the server.

Token (version 'a'): base64url of a byte stream of varints, one item per card
line in the export's order:
    0                -> next section (Pokémon -> Trainer -> Energy)
    v = rest*8 + q   q 1..7: that many copies; q 0: copies = rest, then a
                     second varint holds the card (so rest is the card ref)
    card ref r       even: share_cards_v1.txt line r // 2
                     odd:  a literal "Name SET NUM" of (r - 1) // 2 UTF-8 bytes
Version 'b' = the same stream raw-deflated (used when it's shorter, e.g. lists
with many cards missing from the table). The table is frozen: links index into
it forever; a newer table would get new version letters.
"""

import base64
import os
import re
import zlib
from urllib.parse import quote, unquote

import decklists

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TABLE_FILE = os.path.join(BASE_DIR, "share_cards_v1.txt")
WEB_BASE = "https://lavahawk.github.io/Pokemon-TCG-Live-Monitor/d/"
SCHEME = "ptcglmonitor"
MAX_TOKEN = 4000      # a 60-card list is ~80 chars; anything far bigger isn't a deck
MAX_NAME = 40
SECTIONS = ("Pokémon", "Trainer", "Energy")

_table = None
_TOKEN = re.compile(r"([ab][A-Za-z0-9_-]{4,%d})(?:~([^\s#?&]*))?" % MAX_TOKEN)


class ShareError(ValueError):
    pass


def table():
    """(list of "Name SET NUM", {line: index})."""
    global _table
    if _table is None:
        with open(TABLE_FILE, "r", encoding="utf-8") as handle:
            rows = [line.rstrip("\n") for line in handle if line.strip() and not line.startswith("#")]
        _table = (rows, {row: i for i, row in enumerate(rows)})
    return _table


def _varint(n, out):
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return


def _read_varint(data, pos):
    shift = value = 0
    while True:
        if pos >= len(data) or shift > 35:
            raise ShareError("truncated link")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text):
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise ShareError("not a deck link") from exc


def encode(text):
    """PTCGL export text -> token."""
    rows, index = table()
    lines = decklists.list_lines(text)
    if not lines:
        raise ShareError("no card lines")
    out = bytearray()
    section = 0
    for line in lines:
        target = SECTIONS.index(line["section"]) if line["section"] in SECTIONS else section
        while section < target:
            out.append(0)
            section += 1
        card = f"{' '.join(line['name'].split())} {line['set']} {line['number']}"
        if card in index:
            ref = index[card] * 2
            literal = b""
        else:
            literal = card.encode("utf-8")
            ref = len(literal) * 2 + 1
        qty = int(line["qty"])
        if 1 <= qty <= 7:
            _varint(ref * 8 + qty, out)
        else:
            _varint(qty * 8, out)
            _varint(ref, out)
        out += literal
    raw = bytes(out)
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = packer.compress(raw) + packer.flush()
    return "b" + _b64(packed) if len(packed) < len(raw) else "a" + _b64(raw)


def decode(token):
    """Token -> PTCGL export text (sections with their line counts, Total Cards)."""
    if not token or len(token) > MAX_TOKEN or token[0] not in "ab":
        raise ShareError("not a deck link")
    data = _unb64(token[1:])
    if token[0] == "b":
        try:
            unpacker = zlib.decompressobj(-15)
            data = unpacker.decompress(data, 16384)
        except zlib.error as exc:
            raise ShareError("damaged link") from exc
    rows, _index = table()
    sections = {name: [] for name in SECTIONS}
    section, pos = 0, 0
    while pos < len(data):
        value, pos = _read_varint(data, pos)
        if value == 0:
            section += 1
            if section >= len(SECTIONS):
                raise ShareError("damaged link")
            continue
        qty, ref = value & 7, value >> 3
        if qty == 0:
            qty = ref
            ref, pos = _read_varint(data, pos)
        if ref % 2 == 0:
            if ref // 2 >= len(rows):
                raise ShareError("this link needs a newer version of the app")
            card = rows[ref // 2]
        else:
            size = (ref - 1) // 2
            raw_card = bytes(data[pos:pos + size])
            pos += size
            card = raw_card.decode("utf-8", "replace")
            if len(raw_card) != size or re.search(r"[\x00-\x1f\x7f]", card):
                raise ShareError("damaged link")
        if not 1 <= qty <= 60 or not decklists._LINE.match(f"{qty} {card}"):
            raise ShareError("damaged link")
        sections[SECTIONS[section]].append(f"{qty} {card}")
    parts = []
    total = 0
    for name in SECTIONS:
        cards = sections[name]
        total += sum(int(c.split()[0]) for c in cards)
        parts.append("\n".join([f"{name}: {len(cards)}"] + cards))  # PTCGL counts lines here
    text = "\n\n".join(parts) + f"\n\nTotal Cards: {total}"
    if not decklists.is_ptcgl_decklist(text):
        raise ShareError("the link doesn't hold a full deck")
    return text


def _clean_name(name):
    name = " ".join((name or "").split())[:MAX_NAME]
    return re.sub(r"[\x00-\x1f<>]", "", name)


def share_url(text, name=None, web=True):
    """The link to share: the web page (clickable in chats) or the app scheme."""
    tail = encode(text)
    name = _clean_name(name)
    if name:
        tail += "~" + quote(name, safe="")
    return (WEB_BASE if web else f"{SCHEME}://d") + "#" + tail


def parse(link):
    """(decklist text, deck name or '') from a web link, an app link or a bare
    token. Raises ShareError when it isn't one."""
    link = (link or "").strip()
    if not link or len(link) > MAX_TOKEN + 400:
        raise ShareError("not a deck link")
    fragment = link.split("#", 1)[1] if "#" in link else link
    match = _TOKEN.fullmatch(fragment.strip())
    if not match:
        raise ShareError("not a deck link")
    text = decode(match.group(1))
    return text, _clean_name(unquote(match.group(2) or ""))


OWN_FILE = os.path.join(BASE_DIR, ".own_share_links")


def remember_own(link):
    """Note a link this app made, so copying it doesn't open the import box."""
    try:
        token = link.split("#", 1)[1].split("~", 1)[0]
        known = _own_tokens()[-49:] + [token]
        with open(OWN_FILE, "w", encoding="utf-8") as handle:
            handle.write("\n".join(known))
    except (OSError, IndexError):
        pass


def _own_tokens():
    try:
        with open(OWN_FILE, "r", encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except OSError:
        return []


def is_own_link(link):
    try:
        return link.strip().split("#", 1)[1].split("~", 1)[0] in _own_tokens()
    except IndexError:
        return False


def looks_like_link(text):
    """Cheap check for clipboard watching: a share link and nothing else."""
    text = (text or "").strip()
    if not text or len(text) > MAX_TOKEN + 400 or "\n" in text:
        return False
    return (text.startswith(WEB_BASE) or text.startswith(f"{SCHEME}://")) and "#" in text
