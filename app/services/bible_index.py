"""
Asante Twi Bible knowledge base — exact passage lookup, spoken-reference parsing, and search.

Data: data/bible_tw.jsonl (built by scripts/build_bible_index.py from the Open.Bible
Asante Twi Bible, CC BY-SA 4.0).

Understands requests such as:
    "Kenkan Dwom ti aduonu mmiɛnsa"          -> read Psalm 23 (whole chapter)
    "Kenkan Genesis ti 1 kɔsi 3"             -> read Genesis 1–3 (several chapters)
    "Yohane 3:16"                            -> John 3:16
    "Mateo ti 5 nkyekyɛm 3 kɔsi 12"          -> Matthew 5:3–12
    "Toa so" / "continue"                    -> next chapter after the last one read
    "Dɛn na Bible ka fa ɔdɔ ho?"             -> question -> search for relevant verses
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field

from app.services.bible_books import ALIASES, BOOKS, normalize, parse_twi_number, spoken_reference

logger = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "bible_tw.jsonl")

READ_WORDS = {"kenkan", "kenkam", "kan", "read", "recite", "bue"}
READ_PHRASES = ["ma me nte", "ma yen nte", "ka kyere me", "kenkan ma me"]
QUESTION_WORDS = {"den", "aden", "deen", "sen", "hwan", "ehe", "kyerekyere", "explain", "what", "why",
                  "how", "who", "mean", "meaning", "nkyerease", "ase", "bisa"}
CONTINUE_PHRASES = ["toa so", "toaso", "continue", "next chapter", "edi so", "eba so", "nea edi so", "dee edi so"]
CHAPTER_FILLERS = {"ti", "tiri", "chapter", "chapters", "chap", "ch", "a", "eto", "so", "no", "dee"}
VERSE_WORDS = {"nkyekyem", "nkyekyemu", "verse", "verses", "vs", "v", ":"}
RANGE_WORDS = {"kosi", "-", "to", "through", "till", "until", "kopem"}
STOPWORDS = {"na", "ne", "a", "no", "so", "wo", "me", "ho", "mu", "e", "se", "yi", "nso", "ma", "de",
             "ara", "bi", "ka", "fa", "nti", "enti", "o", "w", "n", "m"}

MAX_READ_CHAPTERS = int(os.environ.get("MAX_READ_CHAPTERS", "10"))


@dataclass
class Passage:
    book: int
    chapter_start: int
    chapter_end: int
    verse_start: int | None = None
    verse_end: int | None = None

    @property
    def spoken_title(self) -> str:
        if self.chapter_end != self.chapter_start:
            return f"{spoken_reference(self.book, self.chapter_start)} kɔsi ti {_tw(self.chapter_end)}"
        return spoken_reference(self.book, self.chapter_start, self.verse_start, self.verse_end)

    @property
    def label(self) -> str:
        name = BOOKS[self.book]["tw"]
        s = f"{name} {self.chapter_start}"
        if self.chapter_end != self.chapter_start:
            s += f"–{self.chapter_end}"
        elif self.verse_start:
            s += f":{self.verse_start}"
            if self.verse_end and self.verse_end != self.verse_start:
                s += f"–{self.verse_end}"
        return s


def _tw(n: int) -> str:
    from app.services.bible_books import twi_number
    return twi_number(n)


@dataclass
class Request:
    """What the listener wants."""
    mode: str                      # "read" | "answer" | "continue"
    passage: Passage | None = None
    wants_explanation: bool = False
    query: str = ""
    notes: list[str] = field(default_factory=list)


class BibleIndex:
    def __init__(self, path: str = DATA_FILE):
        self.path = os.path.abspath(path)
        self.verses: list[dict] = []
        self.by_chapter: dict[tuple[int, int], list[dict]] = {}
        self._bm25 = None
        self._lock = threading.Lock()
        self.ready = False

    # ------------------------------------------------------------------ loading
    def load(self) -> None:
        with self._lock:
            if self.ready:
                return
            if not os.path.exists(self.path):
                logger.warning(f"Bible data not found at {self.path}. Run scripts/build_bible_index.py")
                return
            book_idx = {b["en"]: i for i, b in enumerate(BOOKS)}
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    v = json.loads(line)
                    v["b"] = book_idx[v["book"]]
                    self.verses.append(v)
                    self.by_chapter.setdefault((v["b"], v["chapter"]), []).append(v)
            try:
                from rank_bm25 import BM25Okapi
                corpus = [self._tokens(v["text"]) for v in self.verses]
                self._bm25 = BM25Okapi(corpus)
            except ImportError:
                logger.warning("rank-bm25 not installed; keyword search disabled")
            self.ready = True
            logger.info(f"Bible index loaded: {len(self.verses)} verses, {len(self.by_chapter)} chapters")

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [t for t in normalize(text).replace(":", " ").replace("-", " ").split() if t not in STOPWORDS]

    # ------------------------------------------------------------------ lookup
    def get_passage(self, p: Passage) -> list[dict]:
        out: list[dict] = []
        for ch in range(p.chapter_start, p.chapter_end + 1):
            verses = self.by_chapter.get((p.book, ch), [])
            if p.verse_start and p.chapter_start == p.chapter_end:
                end = p.verse_end or p.verse_start
                verses = [v for v in verses if p.verse_start <= v["verse"] <= end]
            out.extend(verses)
        return out

    def chapter_count(self, book: int) -> int:
        return BOOKS[book]["chapters"]

    def search(self, query: str, k: int = 6) -> list[dict]:
        if not self._bm25:
            return []
        toks = self._tokens(query)
        if not toks:
            return []
        scores = self._bm25.get_scores(toks)
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [self.verses[i] for i in top if scores[i] > 0]

    # ------------------------------------------------------------------ parsing
    def parse_request(self, text: str) -> Request:
        norm = normalize(text)
        norm_sp = re.sub(r"(\d+)\s*:\s*(\d+)", r"\1 : \2", norm)
        norm_sp = re.sub(r"(\d)\s*-\s*(\d)", r"\1 - \2", norm_sp)
        words = set(norm_sp.split())

        if any(p in norm_sp for p in CONTINUE_PHRASES) and len(words) <= 6:
            return Request(mode="continue", query=text)

        wants_read = bool(words & READ_WORDS) or any(p in norm_sp for p in READ_PHRASES)
        has_question = bool(words & QUESTION_WORDS)
        passage = self._find_passage(norm_sp)

        if passage:
            other = [w for w in norm_sp.split() if w not in CHAPTER_FILLERS | VERSE_WORDS | RANGE_WORDS
                     and not w.isdigit() and parse_twi_number([w])[0] is None]
            only_reference = len(other) <= 3
            if wants_read or (only_reference and not has_question):
                return Request(mode="read", passage=passage, wants_explanation=has_question, query=text)
            return Request(mode="answer", passage=passage, query=text)
        return Request(mode="answer", query=text)

    def _find_passage(self, norm: str) -> Passage | None:
        best = None
        for alias, bidx in ALIASES:
            for m in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm):
                tail = norm[m.end():].split()
                parsed = self._parse_numbers(tail)
                # Short aliases/abbreviations (e.g. "ps", "rom") only count when followed by a chapter number
                if len(alias) < 5 and not parsed:
                    continue
                cand = (m.start(), bidx, parsed)
                if best is None or (parsed and not best[2]) or (bool(parsed) == bool(best[2]) and m.start() < best[0]):
                    best = cand
            if best and best[2]:
                break  # longest alias with numbers found
        if not best:
            return None
        _, bidx, parsed = best
        max_ch = self.chapter_count(bidx)
        if not parsed:
            return Passage(bidx, 1, 1)
        c1, c2, v1, v2 = parsed
        c1 = max(1, min(c1, max_ch))
        c2 = max(c1, min(c2 or c1, max_ch))
        if c2 - c1 + 1 > MAX_READ_CHAPTERS:
            c2 = c1 + MAX_READ_CHAPTERS - 1
        return Passage(bidx, c1, c2, v1, v2)

    @staticmethod
    def _parse_numbers(tokens: list[str]) -> tuple[int, int | None, int | None, int | None] | None:
        """Parse 'ti 3 kɔsi 5' / '3 : 16 - 18' / 'ti aduonu mmiensa nkyekyem 1 kosi 6'."""
        i = 0
        while i < len(tokens) and tokens[i] in CHAPTER_FILLERS:
            i += 1
        ch, used = parse_twi_number(tokens[i:i + 6])
        if not ch:
            return None
        i += used
        ch_end = v1 = v2 = None

        def skip(words):
            nonlocal i
            while i < len(tokens) and tokens[i] in words:
                i += 1

        if i < len(tokens) and tokens[i] in RANGE_WORDS:  # chapter range: "ti 1 kɔsi 3"
            j = i
            i += 1
            skip(CHAPTER_FILLERS)
            n, used = parse_twi_number(tokens[i:i + 6])
            if n and n > ch:
                ch_end = n
                i += used
            else:
                i = j
        if ch_end is None and i < len(tokens) and tokens[i] in VERSE_WORDS:
            skip(VERSE_WORDS)
            v1, used = parse_twi_number(tokens[i:i + 6])
            i += used
            if v1 and i < len(tokens) and tokens[i] in RANGE_WORDS:
                i += 1
                skip(VERSE_WORDS)
                v2, used = parse_twi_number(tokens[i:i + 6])
                i += used
        return ch, ch_end, v1, v2


bible_index = BibleIndex()
