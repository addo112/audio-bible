"""
Bible book catalog with English + Asante Twi names, aliases, and Twi number words.

Used for:
- Mapping dataset book names (English) to canonical order
- Recognising spoken references such as "Dwom ti aduonu mmiɛnsa", "Yohane 3:16", "John 3"
- Speaking references aloud in Twi ("Dwom, ti aduonu mmiɛnsa")
"""
import re
import unicodedata

# (English name, Twi display name, extra aliases, number of chapters)
_RAW_BOOKS = [
    ("Genesis", "Genesis", ["mfitiase", "mfitiasee", "gen"], 50),
    ("Exodus", "Exodus", ["eksodus", "exo", "ex"], 40),
    ("Leviticus", "Leviticus", ["lev", "lefitiko"], 27),
    ("Numbers", "Numeri", ["nnipakan"], 36),
    ("Deuteronomy", "Deuteronomium", ["deut", "deuteronomio", "mmara a ɛtɔ so mmienu"], 34),
    ("Joshua", "Yosua", ["josh", "yoswa"], 24),
    ("Judges", "Atemmufoɔ", ["atemmufo", "judg", "atemmufoo"], 21),
    ("Ruth", "Rut", ["rute"], 4),
    ("1 Samuel", "1 Samuel", ["1 sam"], 31),
    ("2 Samuel", "2 Samuel", ["2 sam"], 24),
    ("1 Kings", "1 Ahemfo", ["1 ahemfo", "1 kgs"], 22),
    ("2 Kings", "2 Ahemfo", ["2 ahemfo", "2 kgs"], 25),
    ("1 Chronicles", "1 Berɛsosɛm", ["1 berɛsosɛm", "1 chr", "1 beresosem"], 29),
    ("2 Chronicles", "2 Berɛsosɛm", ["2 berɛsosɛm", "2 chr", "2 beresosem"], 36),
    ("Ezra", "Esra", [], 10),
    ("Nehemiah", "Nehemia", ["neh"], 13),
    ("Esther", "Ester", ["esth"], 10),
    ("Job", "Hiob", ["yob"], 42),
    ("Psalms", "Nnwom", ["dwom", "nnwom", "psalm", "ps", "psa", "ndwom"], 150),
    ("Proverbs", "Mmebusɛm", ["mmebusem", "mmɛbusɛm", "prov", "abebusem"], 31),
    ("Ecclesiastes", "Ɔsɛnkafoɔ", ["osenkafo", "ɔsɛnkafo", "eccl", "osenkafoo"], 12),
    ("Song of Songs", "Nnwom mu Dwom", ["nnwom mu dwom", "song of solomon", "song"], 8),
    ("Isaiah", "Yesaia", ["isa", "yesaya"], 66),
    ("Jeremiah", "Yeremia", ["jer", "yeremiya"], 52),
    ("Lamentations", "Kwadwom", ["lam"], 5),
    ("Ezekiel", "Hesekiel", ["ezek", "esekiel"], 48),
    ("Daniel", "Daniel", ["dan"], 12),
    ("Hosea", "Hosea", ["hos"], 14),
    ("Joel", "Yoel", [], 3),
    ("Amos", "Amos", [], 9),
    ("Obadiah", "Obadia", ["obad"], 1),
    ("Jonah", "Yona", [], 4),
    ("Micah", "Mika", ["mic"], 7),
    ("Nahum", "Nahum", ["nah"], 3),
    ("Habakkuk", "Habakuk", ["hab"], 3),
    ("Zephaniah", "Sefania", ["zeph"], 3),
    ("Haggai", "Hagai", ["hag"], 2),
    ("Zechariah", "Sakaria", ["zech"], 14),
    ("Malachi", "Malaki", ["mal"], 4),
    ("Matthew", "Mateo", ["mateu", "matt", "mat"], 28),
    ("Mark", "Marko", ["mk"], 16),
    ("Luke", "Luka", ["lk"], 24),
    ("John", "Yohane", ["jn", "yohanes"], 21),
    ("Acts", "Asomafoɔ Nnwuma", ["asomafo nnwuma", "asomafoo nnwuma", "acts of the apostles"], 28),
    ("Romans", "Romafoɔ", ["romafo", "rom", "romafoo"], 16),
    ("1 Corinthians", "1 Korintofoɔ", ["1 korintofo", "1 cor", "1 korintofoo"], 16),
    ("2 Corinthians", "2 Korintofoɔ", ["2 korintofo", "2 cor", "2 korintofoo"], 13),
    ("Galatians", "Galatifoɔ", ["galatifo", "gal", "galatifoo"], 6),
    ("Ephesians", "Efesofoɔ", ["efesofo", "eph", "efesofoo"], 6),
    ("Philippians", "Filipifoɔ", ["filipifo", "phil", "filipifoo"], 4),
    ("Colossians", "Kolosefoɔ", ["kolosefo", "col", "kolosefoo"], 4),
    ("1 Thessalonians", "1 Tesalonikafoɔ", ["1 tesalonikafo", "1 thess", "1 tesalonikafoo"], 5),
    ("2 Thessalonians", "2 Tesalonikafoɔ", ["2 tesalonikafo", "2 thess", "2 tesalonikafoo"], 3),
    ("1 Timothy", "1 Timoteo", ["1 tim"], 6),
    ("2 Timothy", "2 Timoteo", ["2 tim"], 4),
    ("Titus", "Tito", [], 3),
    ("Philemon", "Filemon", ["phlm"], 1),
    ("Hebrews", "Hebrifoɔ", ["hebrifo", "heb", "hebrifoo"], 13),
    ("James", "Yakobo", ["jas", "yakob"], 5),
    ("1 Peter", "1 Petro", ["1 pet"], 5),
    ("2 Peter", "2 Petro", ["2 pet"], 3),
    ("1 John", "1 Yohane", ["1 jn"], 5),
    ("2 John", "2 Yohane", ["2 jn"], 1),
    ("3 John", "3 Yohane", ["3 jn"], 1),
    ("Jude", "Yuda", [], 1),
    ("Revelation", "Adiyisɛm", ["adiyisem", "rev", "revelations", "nyikyerɛ", "nyikyere"], 22),
]

BOOKS = [
    {"en": en, "tw": tw, "aliases": aliases, "chapters": chapters}
    for en, tw, aliases, chapters in _RAW_BOOKS
]


def normalize(text: str) -> str:
    """Lowercase, map Akan vowels to Latin, strip accents/punctuation, collapse spaces."""
    t = text.lower()
    t = t.replace("ɛ", "e").replace("ɔ", "o").replace("ŋ", "ng")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-z0-9:\-\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Ordinal prefixes for numbered books ("1 Yohane", "first John", "Yohane a ɛdi kan")
_ORDINAL_WORDS = {
    "1": ["1", "i", "first", "1st", "deɛ ɛdi kan", "dee edi kan", "edi kan", "nea edi kan", "baako"],
    "2": ["2", "ii", "second", "2nd", "deɛ ɛtɔ so mmienu", "dee eto so mmienu", "eto so mmienu", "mmienu", "abien"],
    "3": ["3", "iii", "third", "3rd", "deɛ ɛtɔ so mmiɛnsa", "dee eto so mmiensa", "eto so mmiensa", "mmiensa", "abiesa"],
}

_EN_INDEX = {normalize(b["en"]): i for i, b in enumerate(BOOKS)}


def book_index(name: str) -> int | None:
    """Map a dataset/English book name to its canonical index."""
    return _EN_INDEX.get(normalize(name))


def _build_alias_table() -> list[tuple[str, int]]:
    table: dict[str, int] = {}
    for i, b in enumerate(BOOKS):
        names = {b["en"], b["tw"], *b["aliases"]}
        for n in list(names):
            nn = normalize(n)
            table[nn] = i
            m = re.match(r"^([123]) (.+)$", nn)
            if m:  # add spoken ordinal variants, before and after the base name
                num, base = m.groups()
                for ow in _ORDINAL_WORDS[num]:
                    table[f"{normalize(ow)} {base}"] = i
                    table[f"{base} {normalize(ow)}"] = i
    # Longest aliases first so "1 yohane" wins over "yohane", "nnwom mu dwom" over "dwom"
    return sorted(table.items(), key=lambda kv: -len(kv[0]))


ALIASES = _build_alias_table()


# ---------------------------------------------------------------------------
# Twi numbers  (spoken numbers ⇄ integers, range 1–999)
# ---------------------------------------------------------------------------
_UNITS = {
    1: ["baako", "biako", "baakoo", "koro"],
    2: ["mmienu", "abien", "mmien", "abienu", "mienu"],
    3: ["mmiensa", "abiesa", "mmiɛnsa", "miensa"],
    4: ["nnan", "anan", "nan"],
    5: ["nnum", "anum", "num"],
    6: ["nsia", "asia", "sia"],
    7: ["nson", "ason", "son"],
    8: ["nwotwe", "awotwe", "nwɔtwe", "wotwe"],
    9: ["nkron", "akron", "kron"],
}
_TENS = {
    10: ["du", "edu"],
    20: ["aduonu", "aduonum mmienu", "aduanu"],
    30: ["aduasa"],
    40: ["aduanan"],
    50: ["aduonum", "aduanum"],
    60: ["aduosia"],
    70: ["aduoson"],
    80: ["aduowotwe", "aduowɔtwe"],
    90: ["aduokron"],
}
_HUNDREDS = {100: ["oha", "ɔha"], 200: ["ahanu", "ahaanu"], 300: ["ahasa"]}
_TEENS = {11: ["dubaako", "dubiako"], 12: ["dumienu", "dummienu", "duabien"], 13: ["dumiensa", "duabiesa"],
          14: ["dunan", "duanan"], 15: ["dunum", "duanum"], 16: ["dunsia", "duasia"], 17: ["dunson", "duason"],
          18: ["dunwotwe", "duawotwe"], 19: ["dunkron", "duakron"]}

_WORD_VALUE: dict[str, int] = {}
for table in (_UNITS, _TENS, _HUNDREDS, _TEENS):
    for val, words in table.items():
        for w in words:
            if " " not in w:
                _WORD_VALUE[normalize(w)] = val

NUMBER_WORDS = set(_WORD_VALUE) | {"ne"}


def parse_twi_number(tokens: list[str]) -> tuple[int | None, int]:
    """
    Parse a Twi number from the start of a token list.
    Returns (value, tokens_consumed). Accepts digits too.
    e.g. ["aduonu", "mmiensa"] -> (23, 2);  ["oha", "ne", "aduonum"] -> (150, 3)
    """
    if not tokens:
        return None, 0
    if tokens[0].isdigit():
        return int(tokens[0]), 1
    total, used, last_kind = 0, 0, None
    for tok in tokens:
        if tok == "ne" and used and last_kind in ("hundred", "ten"):
            used += 1
            continue
        val = _WORD_VALUE.get(tok)
        if val is None:
            break
        kind = "hundred" if val >= 100 else "ten" if val >= 10 else "unit"
        if last_kind == "unit" or (kind == "hundred" and last_kind is not None):
            break
        total += val
        used += 1
        last_kind = kind
    if used and tokens[used - 1] == "ne":
        used -= 1
    return (total or None), used


def twi_number(n: int) -> str:
    """Speak an integer (1–999) in Asante Twi."""
    unit = {1: "baako", 2: "mmienu", 3: "mmiɛnsa", 4: "nnan", 5: "nnum", 6: "nsia", 7: "nson", 8: "nwɔtwe", 9: "nkron"}
    tens = {1: "du", 2: "aduonu", 3: "aduasa", 4: "aduanan", 5: "aduonum", 6: "aduosia", 7: "aduoson", 8: "aduowɔtwe", 9: "aduokron"}
    teen = {11: "dubaako", 12: "dumienu", 13: "dumiɛnsa", 14: "dunan", 15: "dunum", 16: "dunsia", 17: "dunson", 18: "dunwɔtwe", 19: "dunkron"}
    hundreds = {1: "ɔha", 2: "ahanu", 3: "ahasa", 4: "ahanan", 5: "ahanum", 6: "ahansia", 7: "ahanson", 8: "ahanwɔtwe", 9: "ahankron"}
    if n <= 0 or n > 999:
        return str(n)
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append(hundreds[h])
    if rest:
        if 11 <= rest <= 19:
            sub = teen[rest]
        else:
            t, u = divmod(rest, 10)
            sub = " ".join(p for p in [tens.get(t, ""), unit.get(u, "")] if p)
        parts.append(sub)
    return " ne ".join(parts)


def spoken_reference(book_idx: int, chapter: int, verse_start: int | None = None, verse_end: int | None = None) -> str:
    """e.g. 'Nnwom, ti aduonu mmiɛnsa, nkyekyɛm baako kɔsi nsia'."""
    name = BOOKS[book_idx]["tw"]
    m = re.match(r"^([123]) (.+)$", name)
    if m:
        ordinal = {"1": "a ɛdi kan", "2": "a ɛtɔ so mmienu", "3": "a ɛtɔ so mmiɛnsa"}[m.group(1)]
        name = f"{m.group(2)} {ordinal}"
    s = f"{name}, ti {twi_number(chapter)}"
    if verse_start:
        s += f", nkyekyɛm {twi_number(verse_start)}"
        if verse_end and verse_end != verse_start:
            s += f" kɔsi {twi_number(verse_end)}"
    return s
