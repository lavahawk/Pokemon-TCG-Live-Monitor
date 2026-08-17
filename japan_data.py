"""
Japan Data module for Pokemon TCG Live Monitor.

Pulls Japanese meta insights from pokekameshi.com (Pokeka Meshi) and related
sources, translates deck names to English (optionally via the OpenAI API key,
aligned with the top Limitless deck names), and consolidates them into a
format comparable to the US/Limitless meta data so the two can be compared
and eventually merged by set list.

Sources:
  - Tier list:      https://pokekameshi.com/strongestdeck-tire/
  - Data lab weekly reports: https://pokekameshi.com/taikairesult-*/
  - Tournament results: https://pokekameshi.com/pokemontaikaiwinYYYYMMDD/
  - Archetype pages: https://pokekameshi.com/category/archetype/
  - Deck code -> card list: https://www.pokemon-card.com/deck/confirm.html/deckID/<CODE>/

Translation strategy:
  - A static JP->EN map covers the common archetypes (no API cost).
  - If AI translation is enabled (recommended) and an OpenAI API key is
    present, the first hard pull sends the JP deck names together with the
    top 50+ Limitless deck names so the AI aligns the JP names to the exact
    English archetype names we already use. The result is stored permanently
    in a translation cache file and is NOT re-fetched on every app open.
    Only an explicit "Hard Refresh" button re-runs the AI translation.
"""

import os
import re
import json
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, ".meta_cache_japan.json")
TRANSLATION_CACHE_FILE = os.path.join(BASE_DIR, ".japan_translation_cache.json")
LIMITLESS_STANDARD_CACHE_FILE = os.path.join(BASE_DIR, ".meta_cache_limitless_standard.json")

CACHE_TTL = 3600  # 1 hour for the meta data itself
TRANSLATION_TTL = 60 * 60 * 24 * 30  # 30 days for the AI translation cache

POKEKAMESHI_BASE = "https://pokekameshi.com"
TIER_LIST_URL = POKEKAMESHI_BASE + "/strongestdeck-tire/"
ARCHETYPE_URL = POKEKAMESHI_BASE + "/category/archetype/"
CITYLEAGUE_URL = POKEKAMESHI_BASE + "/category/cityleague/"
WIN_DECK_URL = POKEKAMESHI_BASE + "/category/pokemoncard-windeckrecipe/"
SITEMAP_URL = POKEKAMESHI_BASE + "/sitemap.xml"
DECK_CONFIRM_URL = "https://www.pokemon-card.com/deck/confirm.html/deckID/{code}/"
DECK_THUMBS_URL = "https://www.pokemon-card.com/deck/thumbs.html/deckID/{code}/"

# Static JP -> EN translation map for common archetypes (no API cost).
JP_DECK_TRANSLATION = {
    "ドラパルト": "Dragapult",
    "ドラパルトex": "Dragapult ex",
    "バシャーモex": "Blaziken ex",
    "バシャドラパ": "Blaziken Dragapult",
    "メガルカリオ": "Mega Lucario",
    "タケルライコ": "Raging Bolt",
    "ゲッコウガ": "Greninja",
    "ゾロアーク": "N's Zoroark",
    "フーディン": "Alakazam",
    "ピッピ": "Clefairy",
    "ガブリアス": "Cynthia's Garchomp",
    "ミュウツー": "Rocket's Mewtwo",
    "リザードン": "Charizard",
    "カビゴン": "Snorlax",
    "ルギア": "Lugia",
    "アルセウス": "Arceus",
    "パオジアン": "Chien-Pao",
    "テツノカイナ": "Iron Hands",
    "サーナイト": "Gardevoir",
    "ロストバレット": "Lost Box",
    "ロストギラティナ": "Lost Giratina",
    "ミライドン": "Miraidon",
    "コライドン": "Koraidon",
    "イダイナキバ": "Great Tusk",
    "ハピナス": "Blissey",
    "ミュウ": "Mew VMAX",
    "ディンルー": "Ting-Lu",
    "カイリュー": "Dragonite",
    "バンギラス": "Tyranitar",
    "ハバタクカミ": "Flutter Mane",
    "テツノブジン": "Iron Valiant",
    "ガルーラボックス": "Kangaskhan Box",
    "ガルーラバレット": "Kangaskhan Bullet",
    "プリズムバレット": "Prism Bullet",
    "カミツオロチ": "Iron Thorns ex",
    "メガニウム": "Meganium",
    "オーロット": "Trevenant",
    "ヤドキング": "Slowking",
    "ルカリオ": "Lucario",
    "オーガポン": "Ogerpon",
    "レックウザ": "Rayquaza",
    "メガレックウザ": "Mega Rayquaza",
    "ジュペッタ": "Banette",
    "ドリュウズ": "Excadrill",
    "メタグロス": "Metagross",
    "ストリンダー": "Toxtricity",
    "オーロンゲ": "Grimmsnarl",
    "おまつりおんど": "Festival Ground",
    "テツノイバラ": "Iron Thorns",
    "テツノイバラex": "Iron Thorns ex",
    "ドデカバシ": "Dondozo",
    "ばけがくれ": "Bakegakure",
    "アブソル": "Absol",
    "イワパレス": "Garganacl",
    "ノココッチ": "Dudunsparce",
    "フーディン": "Alakazam",
    "ガブリアス": "Garchomp",
    "ミロカロス": "Milotic",
    "サーフゴー": "Gholdengo",
    "バチュル": "Joltik",
    "ヒバニー": "Scorbunny",
    "ニンジャスピナー": "Ninja Spinner",
    "ストームエメラルダ": "Storm Emerald",
    "ニンジャスピナー環境": "Ninja Spinner format",
    # Additional archetypes from recent tournament/tier data
    "ジュナイパー": "Decidueye",
    "フシギバナ": "Venusaur",
    "バシャーモ": "Blaziken",
    "オリーヴァ": "Arboliva",
    "バクフーン": "Typhlosion",
    "ライボルト": "Manectric",
    "パンプジン": "Pumpkaboo",
    "イイネイヌ": "Fidough",
    "マリィのオーロンゲ": "Marnie's Grimmsnarl",
    "シロナのガブリアス": "Cynthia's Garchomp",
    "メガゲッコウガ": "Mega Greninja",
    "メガドリュウズ": "Mega Excadrill",
    "タケルライコex": "Raging Bolt ex",
    "メガルカリオex": "Mega Lucario ex",
    "メガレックウザex": "Mega Rayquaza ex",
    "カミツオロチex": "Iron Thorns ex",
    "ドラパルトexデッキ": "Dragapult ex",
    "ヤドキングデッキ": "Slowking",
    "バシャーモex＋ドラパルトex": "Blaziken ex Dragapult ex",
    "ガルーラボックス": "Kangaskhan Box",
    "タケルライコ": "Raging Bolt",
    "ドラゴン": "Dragon",
    "メガニウムex": "Meganium ex",
    "ドデカバシ": "Dondozo",
    "ミミッキュ": "Mimikyu",
    "ドラメシヤ": "Dreepy",
    "テツノブジンex": "Iron Valiant ex",
    "エンペルト": "Empoleon",
    "リザードンex": "Charizard ex",
    "セグレイブ": "Baxcalibur",
    "ガラルファイヤー": "Galarian Articuno",
    "ラティアス": "Latias",
    "ラティオス": "Latios",
    "ライコウ": "Raikou",
    "エンテイ": "Entei",
    "スイクン": "Suicune",
    "ドンカラス": "Honchkrow",
    "ソウブレイズ": "Ceruledge",
    "メガミミロップ": "Mega Lopunny",
    "ブリジュラス": "Archaludon",
    "タイジキングダム": "Tai Kingdom",
    "スターミー": "Starmie",
    "ファイアロー": "Talonflame",
    "メタング": "Metang",
    "バテレン追放令": "Fan of Waves",
    "ハンバリー": "Hambly",
    "ソルロック": "Solrock",
    "ルナトーン": "Lunatone",
    "ルガルガン": "Lycanroc",
    "ゾロアークex": "Zoroark ex",
    "Nのゾロアークex": "N's Zoroark ex",
    "エースバーン": "Cinderace",
    "ダイケンキ": "Samurott",
    "マッギヨ": "Mabostiff",
    "ウミトリオ": "Wugtrio",
    "ドオー": "Clodsire",
    "イトマル": "Nymble",
    "ベラカス": "Pawmo",
    "オリガミ": "Origami",
    "ユキメノコ": "Froslass",
    "ミミロップ": "Lopunny",
    "ブイズバレット": "Eeveelution Bullet",
    "メガユキノオー": "Mega Abomasnow",
    "フリーザー": "Articuno",
    "サンダー": "Zapdos",
    "ファイヤー": "Moltres",
    "ゲノセクト": "Genesect",
    "ミュウex": "Mew ex",
    "マシマシラ": "Munkidori",
    "オーリム": "Future Booster",
    "ヒガナ": "Hibana",
    "テラパゴス": "Terapagos",
    "ガラルマタドガス": "Galarian Weezing",
    "ヨクバリス": "Greedent",
    "アカツキex": "Akatsuki ex",
    "グランブル": "Granbull",
    "シンオウの化石": "Hisuian Fossil",
    "マリィ": "Marnie",
    "ネス": "N",
    "グソクムシャ": "Golisopod",
    "ミジュ": "Miju",
    "メガジガルデ": "Mega Zygarde",
    "シャンデラ": "Chandelure",
    "マンデー": "Monday",
    "シャリタツ": "Tatsugiri",
    "ガチゴラス": "Bangura",
    "コントロール": "Control",
    "ホウオウ": "Ho-Oh",
    "キノノタミ": "Kinanotami",
    "メガシンヤ": "Mega Shin",
    "メガヤンマ": "Mega Yanma",
    "テラスタルバレット": "Terastal Bullet",
    "しんちょう警備隊": "Shinchou Guard",
    "ご幸非": "Gokou",
    "ニンフィア": "Sylveon",
    "メガシャンデラ": "Mega Chandelure",
    "メガヤンマ": "Mega Yanma",
    "シェイミ": "Shaymin",
    "ガラガラ": "Marowak",
    "フライゴン": "Flygon",
    "ガチグマ": "Ursaluna",
    "ダイオウドウ": "Donphan",
    "ブーピッグ": "Grumpig",
    "ウソッキー": "Sudowoodo",
}

def _load_limitless_deck_names(limit=60):
    """Load the top English deck names from the Limitless standard cache."""
    names = []
    if not os.path.exists(LIMITLESS_STANDARD_CACHE_FILE):
        return names
    try:
        with open(LIMITLESS_STANDARD_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        ranked = sorted(
            rows,
            key=lambda row: int((row or {}).get("count", 0) or 0),
            reverse=True,
        )
        seen = set()
        for row in ranked:
            deck_name = str((row or {}).get("deck") or "").strip()
            if not deck_name or deck_name.lower() == "other":
                continue
            norm = _normalize(deck_name)
            if norm in seen:
                continue
            seen.add(norm)
            names.append(deck_name)
            if len(names) >= limit:
                break
    except Exception:
        pass
    return names


def _normalize(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _load_translation_cache():
    if not os.path.exists(TRANSLATION_CACHE_FILE):
        return {}
    try:
        with open(TRANSLATION_CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_translation_cache(data):
    try:
        with open(TRANSLATION_CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _translation_cache_fresh():
    if not os.path.exists(TRANSLATION_CACHE_FILE):
        return False
    try:
        age = time.time() - os.path.getmtime(TRANSLATION_CACHE_FILE)
        return age < TRANSLATION_TTL
    except Exception:
        return False


def _clean_deck_name(raw):
    """Clean a raw deck entry name, stripping tournament noise.

    Removes suffixes like placement notes like 'スクランブルバトル大阪：6-1',
    sizes like '(9名)', ':優勝', etc. Returns a clean Japanese archetype name.
    """
    text = (raw or "").strip()
    if not text:
        return ""

    # Remove trailing placement/size/tournament info.
    # e.g. "バシャーモデッキ スクランブルバトル大阪：6-1" -> "バシャーモデッキ"
    #      "ライボルトデッキ (9名)" -> "ライボルトデッキ"
    text = re.sub(r"\s*\(\s*\d+\s*名\s*\)", "", text)
    # "スクランブルバトル大阪：6-1" / ":優勝" / ":6-1"
    text = re.sub(r"\s*[:：]\s*[\d\-]+[\d]*$", "", text.strip())
    text = re.sub(r"\s*[:：]\s*(優勝|準優勝|ベスト4|ベスト8|\d+\s*位).*$", "", text.strip())
    # Remove a standalone trailing "スクランブルバトル 大阪" style tournament tag
    # only if it appears as a clearly separate segment after the deck name.
    text = re.sub(r"\s+(?:スクランブルバトル|ジムババトル|バトルフェス|カップ|フェス|杯).*$", "", text, flags=re.IGNORECASE)

    return text.strip()


def translate_deck_name(jp_name, ai_enabled=False, api_key=None, force=False):
    """Translate a Japanese deck name to English.

    Priority:
      1. Static JP_DECK_TRANSLATION map (exact or substring match).
      2. AI translation cache (permanent, refreshed only on hard pull).
      3. AI live call (only when ai_enabled and api_key present and force).
    Falls back to the raw JP name if nothing matches.
    """
    jp_name = (jp_name or "").strip()
    if not jp_name:
        return ""

    # Strip trailing "デッキ" (deck) so "バシャーモデッキ" matches "バシャーモ".
    core = re.sub(r"デッキ\s*$", "", jp_name).strip()
    if not core:
        core = jp_name

    # Build a combined lookup: exact name and its "デッキ"-stripped form.
    candidates = [jp_name, core]

    # 1. Static map (exact)
    for cand in candidates:
        if cand in JP_DECK_TRANSLATION:
            return JP_DECK_TRANSLATION[cand]

    # 1b. Static map (substring / token match) on the stripped core first.
    for jp_key, en_val in JP_DECK_TRANSLATION.items():
        if jp_key and jp_key in core:
            return en_val

    # 2. AI translation cache
    cache = _load_translation_cache()
    for cand in candidates:
        if cand in cache:
            return cache[cand]

    # 3. AI live call (only on hard pull)
    if ai_enabled and api_key and force:
        en = _ai_translate(candidates, api_key).get(jp_name) or _ai_translate(candidates, api_key).get(core)
        if en:
            cache[jp_name] = en
            _save_translation_cache(cache)
            return en

    return jp_name


def _ai_translate(jp_names, api_key):
    """Use the OpenAI API to translate JP deck names, aligned with Limitless names.

    Returns {jp_name: en_name}. Only called on an explicit hard pull.
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    limitless_names = _load_limitless_deck_names(60)
    names_json = json.dumps(jp_names, ensure_ascii=False)
    align_json = json.dumps(limitless_names, ensure_ascii=False)

    prompt = (
        "You are translating Japanese Pokemon TCG deck archetype names to English.\n"
        "Here are the English deck names we already use (from Limitless). Align each "
        "Japanese deck name to the closest matching English archetype name from this "
        "list when possible. If none matches, provide the standard English archetype "
        "name. Return ONLY a JSON object mapping each Japanese name to its English name.\n\n"
        f"English deck names to align with:\n{align_json}\n\n"
        f"Japanese deck names to translate:\n{names_json}"
    )

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You translate Pokemon TCG deck names and return JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    try:
        payload = json.loads(completion.choices[0].message.content)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _save_cache(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _cache_fresh():
    if not os.path.exists(CACHE_FILE):
        return False
    try:
        age = time.time() - os.path.getmtime(CACHE_FILE)
        return age < CACHE_TTL
    except Exception:
        return False


def _get_session():
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        session.headers.update({
            "User-Agent": "TCGLiveMonitor/2.3 (+https://github.com/lavahawk)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        retry = Retry(total=3, connect=3, read=3, backoff_factor=0.4,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "POST"))
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    except Exception:
        return None


def _fetch_html(url, session=None):
    if session is None:
        session = _get_session()
    if session is None:
        return ""
    try:
        response = session.get(url, timeout=20)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return ""


def _extract_deck_codes(html):
    """Find deck codes like pyUUyU-MV0ErE-MpXUyR in HTML."""
    return re.findall(r"[A-Za-z0-9]{6}-[A-Za-z0-9]{6}-[A-Za-z0-9]{6}", html)


def _is_noise_heading(text):
    """Return True if a heading is navigation/structural, not a deck name."""
    if not text:
        return True
    noise = (
        "デッキ検索", "シティリーグ検索", "ポケカデータラボ", "Sponsored",
        "広告", "目次", "ページガイド", "自主大会", "デッキ分布",
        "優勝", "準優勝", "ベスト", "本記事", "この記事", "Tierとは",
        "インプットデータ", "参考デッキレシピ", "詳細はこちら",
        "ホーム", "メニュー", "シェア", "トップ", "サイドバー",
        "各タイプ", "デッキ一覧", "新着記事", "ポケカお役立ち",
        "SiteMap", "Profile", "PTCGL", "シティリーグ",
        "ポケカ飯ポータル", "カテゴリー", "最近の投稿", "アーカイブ",
        "関連記事", "コメント", "タグ", "検索", "フォロー", "シェアする",
        "ポケカ飯", "ポケモンカードゲーム", "トレーナーズ", "おすすめ",
        "人気記事", "新着", "ランキング", "カードリスト", "環境デッキ",
        "ジムババトルデッキまとめ", "スクランブルバトルデッキまとめ",
        "自主大会結果まとめ", "デッキまとめ", "優勝デッキまとめ",
    )
    for n in noise:
        if n in text:
            return True
    # Skip pure navigation / very short fragments
    if len(text) < 2:
        return True
    return False


def _extract_tier_decks(html):
    """Parse the tier list page into deck entries.

    Returns list of {tier, deck_jp, code, event, placement, url}.
    """
    decks = []
    current_tier = None
    # Tier headings: <h2>Tier1</h2> ... <h3>deck name</h3>
    for match in re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", html, flags=re.DOTALL | re.IGNORECASE):
        level = int(match.group(1))
        text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if level == 2 and re.match(r"^Tier\s*\d", text, flags=re.IGNORECASE):
            current_tier = re.search(r"(\d)", text).group(1)
        elif level == 3 and current_tier and text and not _is_noise_heading(text):
            decks.append({
                "tier": int(current_tier),
                "deck_jp": text,
                "code": None,
                "event": None,
                "placement": None,
                "url": None,
            })
    # Attach deck codes found in the page to the nearest preceding deck.
    codes = _extract_deck_codes(html)
    for i, deck in enumerate(decks):
        if i < len(codes):
            deck["code"] = codes[i]
    return decks


def _extract_tournament_decks(html):
    """Parse a tournament result page into deck entries.

    Returns list of {deck_jp, count, code, image, tweet_url}.
    """
    decks = []
    # Deck headings: <h3>deck name ...</h3> or <h2>deck name</h2>
    for match in re.finditer(r"<h([23])[^>]*>(.*?)</h\1>", html, flags=re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if not text or _is_noise_heading(text):
            continue
        # Remove trailing tournament/placement info: "スクランブルバトル大阪：6-1", "：優勝", "(9名)"
        cleaned = _clean_deck_name(text)
        if not cleaned:
            continue
        decks.append({
            "deck_jp": cleaned,
            "count": 1,
            "code": None,
            "image": None,
            "tweet_url": None,
        })
    codes = _extract_deck_codes(html)
    for i, deck in enumerate(decks):
        if i < len(codes):
            deck["code"] = codes[i]
    return decks


def _extract_datalab_report(html):
    """Parse a data lab weekly report (taikairesult-*) into tournaments.

    Returns list of {name, size, date, region, format, tweet_url, placings}.
    """
    tournaments = []
    # Tournament headings: <h3>name (NN名)</h3>
    for match in re.finditer(r"<h3[^>]*>(.*?)</h3>", html, flags=re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if not text or _is_noise_heading(text):
            continue
        size_match = re.search(r"\((\d+)名\)", text)
        tournaments.append({
            "name": text,
            "size": int(size_match.group(1)) if size_match else None,
            "date": None,
            "region": None,
            "format": None,
            "tweet_url": None,
            "placings": [],
        })

    # Extract date/region/format from the 開催日 line following each heading.
    # Pattern: 開催日：YYYY/MM/DD <region> <format>
    date_pattern = re.compile(r"開催日[：:]\s*(\d{4})/(\d{1,2})/(\d{1,2})\s*([^\n<]*)")
    date_matches = list(date_pattern.finditer(html))
    for t, dm in zip(tournaments, date_matches):
        year, month, day = int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
        t["date"] = f"{year:04d}-{month:02d}-{day:02d}"
        rest = dm.group(4).strip()
        # Region is usually the first token; format contains 個人戦/チーム
        t["region"] = rest.split()[0] if rest else None
        if "チーム" in rest:
            t["format"] = "team"
        elif "個人戦" in rest:
            t["format"] = "individual"
        else:
            t["format"] = None

    # Associate placing lines with tournaments by HTML position.
    # Build a list of (position, place, deck) tuples.
    place_map = {"優勝": "1st", "準優勝": "2nd", "ベスト4": "top4", "ベスト8": "top8"}
    placing_entries = []
    for pm in re.finditer(r"(優勝|準優勝|ベスト4|ベスト8)[：:]\s*([^\n<]+)", html):
        placing_entries.append((pm.start(), place_map.get(pm.group(1), pm.group(1)), pm.group(2).strip()))

    # For each tournament, collect placing entries that fall between this
    # tournament's heading and the next one.
    heading_positions = []
    for match in re.finditer(r"<h3[^>]*>(.*?)</h3>", html, flags=re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if text and not _is_noise_heading(text):
            heading_positions.append(match.start())

    for i, t in enumerate(tournaments):
        start = heading_positions[i] if i < len(heading_positions) else 0
        end = heading_positions[i + 1] if i + 1 < len(heading_positions) else len(html)
        block = []
        for pos, place, deck_jp in placing_entries:
            if start <= pos < end:
                block.append({"place": place, "deck_jp": deck_jp})
        t["placings"] = block

    return tournaments


def _consolidate_rows(decks, translate_fn):
    """Consolidate deck entries into comparable meta rows.

    Returns list of rows in the same shape as Limitless meta rows:
    {deck, count, share, wins, losses, win_pct, bayes_win_pct, ci_low_pct,
     ci_high_pct, confidence_label, icons, deck_url, source}
    """
    from deck_analytics import bayesian_binomial_summary

    counts = {}
    for d in decks:
        raw = d.get("deck_jp", "").strip()
        if not raw:
            continue
        # Normalize the deck name so fragmented entries merge together.
        cleaned = _clean_deck_name(raw)
        if not cleaned:
            continue
        en = translate_fn(cleaned)
        if not en:
            continue
        # Increment count by the entry's weight (default 1).
        weight = max(1, int(d.get("count", 1) or 1))
        counts[en] = counts.get(en, 0) + weight

    total = sum(counts.values()) or 1
    rows = []
    for en, count in counts.items():
        summary = bayesian_binomial_summary(count, 0, 0)
        rows.append({
            "deck": en,
            "count": count,
            "share": round(count / total * 100, 1),
            "wins": count,
            "losses": 0,
            "ties": 0,
            "win_pct": round(summary.get("observed", 0.0) * 100.0, 1),
            "bayes_win_pct": round(summary.get("bayes_mean", 0.0) * 100.0, 1),
            "ci_low_pct": round(summary.get("ci_low", 0.0) * 100.0, 1),
            "ci_high_pct": round(summary.get("ci_high", 0.0) * 100.0, 1),
            "confidence_label": summary.get("confidence_label"),
            "icons": [],
            "deck_url": None,
            "source": "japan",
        })
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows


def _is_non_deck_text(text):
    """Return True if a placing text is clearly not a deck archetype name.

    Filters out player names, venue names, generic labels like 不明, and
    placeholder text that appears in result posts.
    """
    t = (text or "").strip()
    if not t:
        return True
    # Player-name markers
    if re.search(r"選手|さん$|くん$|様$|チーム$", t):
        return True
    # Non-archetype labels
    if t in ("不明", "なし", "—", "-", "--", "？", "??") or not re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", t):
        return True
    # Organization / not a deck
    if re.search(r"(非営利団体|動物園|株式会社|大学|同好会|コミュニティ|オフ会)", t):
        return True
    # Very short fragments unlikely to be decks
    if len(t) < 2:
        return True
    return False


def _split_multi_decks(text):
    """Split a placing like 'ドラパルト、ドラパルト、おまつりおんど' into parts."""
    return [p.strip() for p in re.split(r"[、,・/+×]", text) if p.strip()]


def _is_non_deck(text):
    """Heuristic: is this text a real deck archetype (has a Pokemon/card name)?"""
    t = (text or "").strip()
    if not t or len(t) < 2:
        return True
    if _is_non_deck_text(t):
        return True
    return False


def _is_non_abbrev_deck_text(text):
    """Fast abuse-name filter used by _is_non_deck_text."""
    if text in ("不明", "なし", "—", "--", "その他"):
        return True
    return False


def _datalab_placings_to_decks(datalab_reports):
    """Convert data lab report placings into weighted deck entries.

    Each placing is weighted by tournament size × placement tier, mirroring
    the data lab's CSP-style point table. Returns a list of deck entries
    {deck_jp, count} where count = weight.
    """
    weights = {
        "1st": 4.0,
        "2nd": 3.0,
        "top4": 2.0,
        "top8": 1.0,
    }
    decks = []
    for report in datalab_reports:
        for tournament in report.get("tournaments", []):
            size = int(tournament.get("size") or 0) or 32  # default 32 min
            # Scale weight by tournament size relative to a 32-player baseline.
            size_factor = size / 32.0
            for placing in tournament.get("placings", []):
                place = placing.get("place")
                base = weights.get(place, 1.0)
                raw = placing.get("deck_jp", "").strip()
                if not raw:
                    continue
                # Split multi-deck entries (team tournaments list several decks).
                for part in _split_multi_decks(raw):
                    if _is_non_deck(part) or _is_noise_heading(part):
                        continue
                    part = _clean_deck_name(part)
                    if not part:
                        continue
                    # Weight by placement tier; scale mildly by tournament size
                    # but cap so total counts stay comparable to the tier list
                    # (which produce modest counts), not thousands.
                    size_factor = min(1.5, size / 64.0)
                    weight = round(base * size_factor, 1)
                    decks.append({
                        "deck_jp": part,
                        "count": weight,
                        "place": place,
                    })
    return decks


def _datalab_slugs():
    """Return a list of recent data lab report slugs (taikairesult-*)."""
    # These are the most recent weekly reports for the current environment.
    # In a future version this is discovered from the sitemap automatically.
    return [
        "taikairesult-m6-3w",
        "taikairesult-m6-2w",
        "taikairesult-m6-1w",
        "taikairesult-m5-10w",
        "taikairesult-m5-9w",
    ]


def _tournament_slugs():
    """Return a list of recent tournament result page slugs."""
    # Daily winning-deck pages from the last few days.
    return [
        "pokemontaikaiwin20260816",
        "pokemontaikaiwin20260814",
        "pokemontaikaiwin20260809",
        "pokemontaikaiwin20260807",
        "pokemontaikaiwin20260802",
    ]


def fetch_japan_data(ai_enabled=False, api_key=None, force=False, use_cache=True):
    """Fetch and consolidate Japan meta data.

    Returns a dict in the same shape as the Limitless meta cache:
    {schema_version, rows, tournaments_processed, total_entries, fetched_at,
     source, timeframe, datalab_reports}
    """
    if use_cache and _cache_fresh():
        cached = _load_cache()
        if cached and isinstance(cached.get("rows"), list):
            return cached

    session = _get_session()
    tier_html = _fetch_html(TIER_LIST_URL, session)
    tier_decks = _extract_tier_decks(tier_html)

    # Also pull recent tournament pages for more deck variety.
    tournament_decks = []
    for slug in _tournament_slugs():
        html = _fetch_html(POKEKAMESHI_BASE + "/" + slug + "/", session)
        tournament_decks.extend(_extract_tournament_decks(html))

    # Pull data lab weekly reports for point-weighted meta data.
    datalab_reports = []
    for slug in _datalab_slugs():
        html = _fetch_html(POKEKAMESHI_BASE + "/" + slug + "/", session)
        report = _extract_datalab_report(html)
        if report:
            datalab_reports.append({
                "slug": slug,
                "tournaments": report,
            })

    all_decks = list(tier_decks) + list(tournament_decks)

    # Include data lab placing decks (weighted) as additional data sources so
    # the meta reflects independent tournament results too.
    datalab_decks = _datalab_placings_to_decks(datalab_reports)
    all_decks.extend(datalab_decks)

    # Translation: use static map + cache; only call AI on hard pull.
    def translate_fn(jp):
        return translate_deck_name(jp, ai_enabled=ai_enabled, api_key=api_key, force=force)

    rows = _consolidate_rows(all_decks, translate_fn)

    data = {
        "schema_version": 4,
        "rows": rows,
        "tournaments_processed": len(datalab_reports) + 1,
        "total_entries": len(all_decks),
        "fetched_at": time.time(),
        "source": "japan",
        "timeframe": "recent",
        "datalab_reports": datalab_reports,
    }
    _save_cache(data)
    return data


def filter_by_timeframe(data, timeframe):
    """Filter Japan data rows by timeframe.

    timeframe: 'recent', '1w', '1m', '3m', 'all'
    Currently the tier list is a snapshot of the current environment, so all
    rows are treated as 'recent'. This is a placeholder for future set-list
    filtering once per-set data is available.
    """
    if not data:
        return []
    rows = data.get("rows", [])
    if timeframe in ("recent", "all"):
        return rows
    # Future: filter by per-row date/set. For now return all rows.
    return rows


def hard_refresh_translations(api_key):
    """Run a full AI translation pass over all known JP deck names.

    Collects JP names from the current cache + static map, translates them all
    in one AI call aligned with Limitless names, and stores permanently.
    """
    if not api_key:
        return 0
    jp_names = set(JP_DECK_TRANSLATION.keys())
    cached = _load_cache()
    if cached:
        for row in cached.get("rows", []):
            # We only store English in rows; re-collect from raw if available.
            pass
    # Also include names from the raw tier/tournament pages.
    session = _get_session()
    tier_html = _fetch_html(TIER_LIST_URL, session)
    for d in _extract_tier_decks(tier_html):
        if d.get("deck_jp"):
            jp_names.add(d["deck_jp"])
    for slug in ("pokemontaikaiwin20260816", "pokemontaikaiwin20260814"):
        html = _fetch_html(POKEKAMESHI_BASE + "/" + slug + "/", session)
        for d in _extract_tournament_decks(html):
            if d.get("deck_jp"):
                jp_names.add(d["deck_jp"])

    jp_names = [n for n in jp_names if n]
    if not jp_names:
        return 0
    translated = _ai_translate(jp_names, api_key)
    cache = _load_translation_cache()
    cache.update(translated)
    _save_translation_cache(cache)
    return len(translated)


if __name__ == "__main__":
    data = fetch_japan_data()
    print(f"Japan rows: {len(data.get('rows', []))}")
    for row in data.get("rows", [])[:20]:
        print(f"  {row['deck']}: {row['count']} ({row['share']}%)")
