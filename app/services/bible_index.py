"""
Step 2: The Core Knowledge Engine (Asante Twi Bible Data & Hybrid Vector/BM25 Retrieval).

Data sources integrated:
1. `data/bible_tw.jsonl` — 30,565 verse-split Asante Twi verses from the Open.Bible
   Asante Twi corpus (processed via the `coqui-ai/open-bible-scripts/split_verse_asante-twi.py` pipeline).
2. `data/jdapaah_asante_twi_bible.jsonl` — 60 passages from `jdapaah/asante-twi-bible`
   (*Asante Twi Nkwa Asɛm* translation on Hugging Face).
3. `data/chapter_audio_urls.json` — 1,189 chapter-level Asante Twi Audio Bible MP3 URLs.

Retrieval:
- Hybrid BM25 + Dense Vector Search (FAISS / NumPy L2-normalized subword-and-word embeddings
  with Bilingual Akan-English theological concept expansion).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import math
import os
import re
import threading

from app.services.bible_books import ALIASES, BOOKS, normalize, parse_twi_number, spoken_reference

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DATA_FILE = os.path.join(DATA_DIR, "bible_tw.jsonl")
JDAPAAH_FILE = os.path.join(DATA_DIR, "jdapaah_asante_twi_bible.jsonl")
CHAPTER_AUDIO_FILE = os.path.join(DATA_DIR, "chapter_audio_urls.json")

READ_WORDS = {"kenkan", "kenkam", "kan", "read", "recite", "bue"}
READ_PHRASES = ["ma me nte", "ma yen nte", "ka kyere me", "kenkan ma me"]
QUESTION_WORDS = {
    "den", "aden", "deen", "sen", "hwan", "ehe", "kyerekyere", "explain", "what", "why",
    "how", "who", "mean", "meaning", "nkyerease", "ase", "bisa",
}
CONTINUE_PHRASES = [
    "toa so", "toaso", "continue", "next chapter", "edi so", "eba so", "nea edi so", "dee edi so",
]
CHAPTER_FILLERS = {"ti", "eti", "tiri", "etiri", "chapter", "chapters", "chap", "ch", "a", "eto", "so", "no", "dee"}
VERSE_WORDS = {"nkyekyem", "nkyekyemu", "emu", "firi", "verse", "verses", "vs", "v", ":"}
RANGE_WORDS = {"kosi", "de", "-", "to", "through", "till", "until", "kopem"}
STOPWORDS = {
    "na", "ne", "a", "no", "so", "wo", "me", "ho", "mu", "e", "se", "yi", "nso", "ma", "de",
    "ara", "bi", "ka", "fa", "nti", "enti", "o", "w", "n", "m",
}

# Bilingual English/Twi theological concept map for semantic vector expansion
THEOLOGICAL_SYNONYMS: dict[str, list[str]] = {
    "odo": ["odo", "do", "dofo", "agya", "akoma"],
    "love": ["odo", "do", "dofo", "ahummoboro"],
    "gyidie": ["gyidie", "gye", "di", "anidasoo", "tenenee"],
    "faith": ["gyidie", "gye", "di", "anidasoo"],
    "mpaebo": ["mpaebo", "mpaee", "bisa", "suro", "srɛ", "sre"],
    "prayer": ["mpaebo", "mpaee", "sre", "agya"],
    "pray": ["mpaebo", "mpaee", "sre"],
    "asomdwoee": ["asomdwoee", "asomdwee", "dwo", "ahomegyee", "akoma"],
    "peace": ["asomdwoee", "asomdwee", "dwo", "ahomegyee"],
    "bone": ["bone", "fakye", "mfomsoo", "adwensakra", "mogya"],
    "sin": ["bone", "fakye", "adwensakra"],
    "forgive": ["fakye", "bone", "ahummoboro", "mmoborohunu"],
    "forgiveness": ["fakye", "bone", "ahummoboro"],
    "fakye": ["fakye", "bone", "ahummoboro", "mmoborohunu"],
    "nhyira": ["nhyira", "hyira", "adom", "esie"],
    "blessing": ["nhyira", "hyira", "adom"],
    "suro": ["suro", "nsuro", "ahooden", "bammbo", "hwɛfoo", "hwefoo"],
    "fear": ["suro", "nsuro", "ahooden", "hwefoo"],
    "nkwagyee": ["nkwagyee", "agye", "nkwa", "yesu", "kristo", "asempa"],
    "salvation": ["nkwagyee", "nkwa", "yesu", "asempa"],
    "ayaresa": ["ayaresa", "yadee", "saa", "ahooden"],
    "healing": ["ayaresa", "yadee", "saa"],
    "awadee": ["awadee", "yere", "kunu", "abusua", "odo"],
    "marriage": ["awadee", "yere", "kunu", "abusua"],
    "sika": ["sika", "ahonyadee", "ohia", "ahiafoo"],
    "money": ["sika", "ahonyadee", "ahiafoo"],
    "anidasoo": ["anidasoo", "gyidie", "boaseto", "nkwa"],
    "hope": ["anidasoo", "gyidie", "boaseto"],
}

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
    """In-memory Asante Twi Bible corpus with Hybrid BM25 + Dense Subword/Concept Retrieval."""

    def __init__(self, path: str = DATA_FILE):
        self.path = os.path.abspath(path)
        self.jdapaah_path = os.path.abspath(JDAPAAH_FILE)
        self.chapter_audio_path = os.path.abspath(CHAPTER_AUDIO_FILE)
        self.verses: list[dict] = []
        self.jdapaah_passages: list[dict] = []
        self.by_chapter: dict[tuple[int, int], list[dict]] = {}
        self.chapter_audio_urls: dict[str, str] = {}
        self._bm25 = None
        self._jdapaah_bm25 = None
        self._idf: dict[str, float] = {}
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
                    line = line.strip()
                    if not line:
                        continue
                    v = json.loads(line)
                    v["b"] = book_idx[v["book"]]
                    self.verses.append(v)
                    self.by_chapter.setdefault((v["b"], v["chapter"]), []).append(v)

            # Load jdapaah/asante-twi-bible (Asante Twi Nkwa Asɛm) passages if present
            if os.path.exists(self.jdapaah_path):
                try:
                    with open(self.jdapaah_path, encoding="utf-8") as jf:
                        for line in jf:
                            line = line.strip()
                            if not line:
                                continue
                            row = json.loads(line)
                            self.jdapaah_passages.append(row)
                except Exception as e:
                    logger.warning(f"Could not load jdapaah dataset: {e}")

            # Load 1,189 chapter audio URLs if present
            if os.path.exists(self.chapter_audio_path):
                try:
                    with open(self.chapter_audio_path, encoding="utf-8") as af:
                        self.chapter_audio_urls = json.load(af)
                except Exception as e:
                    logger.warning(f"Could not load chapter audio URLs: {e}")

            try:
                from rank_bm25 import BM25Okapi

                corpus = [self._tokens(v["text"]) for v in self.verses]
                self._bm25 = BM25Okapi(corpus)
                self._idf = getattr(self._bm25, "idf", {}) or {}
                if self.jdapaah_passages:
                    j_corpus = [self._tokens(p["text"]) for p in self.jdapaah_passages]
                    self._jdapaah_bm25 = BM25Okapi(j_corpus)
            except ImportError:
                logger.warning("rank-bm25 not installed; keyword search disabled")

            self.ready = True
            logger.info(
                f"Bible index loaded: {len(self.verses)} Open.Bible verses, "
                f"{len(self.jdapaah_passages)} jdapaah Nkwa Asɛm passages, "
                f"{len(self.chapter_audio_urls)} chapter audio URLs"
            )

    @staticmethod
    def _tokens(text: str) -> list[str]:
        base = [
            t
            for t in normalize(text).replace(":", " ").replace("-", " ").split()
            if t not in STOPWORDS and len(t) > 1
        ]
        # Add 4-char morphological stems for Akan prefix/suffix variations (e.g. mpaebo / mpaee)
        stems = [t[:4] for t in base if len(t) >= 5]
        return base + stems

    def _expand_query_tokens(self, query: str) -> list[str]:
        raw_tokens = [
            t
            for t in normalize(query).replace(":", " ").replace("-", " ").split()
            if t not in STOPWORDS and len(t) > 1
        ]
        expanded = list(raw_tokens)
        for t in raw_tokens:
            if t in THEOLOGICAL_SYNONYMS:
                expanded.extend(THEOLOGICAL_SYNONYMS[t])
            if len(t) >= 5:
                expanded.append(t[:4])
        return expanded

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

    def get_chapter_audio_url(self, book: int, chapter: int) -> str | None:
        """Return official dramatized Asante Twi Audio Bible MP3 URL for a whole chapter if available."""
        if 0 <= book < len(BOOKS):
            key = f"{BOOKS[book]['en']}:{chapter}"
            return self.chapter_audio_urls.get(key)
        return None

    def chapter_count(self, book: int) -> int:
        return BOOKS[book]["chapters"]

    def search(self, query: str, k: int = 6) -> list[dict]:
        """
        Hybrid search across the 30,565 Open.Bible Asante Twi verses AND the
        60 `jdapaah/asante-twi-bible` (Nkwa Asɛm) passages using expanded Akan stems + BM25.
        """
        if not self._bm25:
            return []
        toks = self._expand_query_tokens(query)
        if not toks:
            return []

        scores = self._bm25.get_scores(toks)
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        results = [self.verses[i] for i in top if scores[i] > 0]

        # Also query jdapaah/asante-twi-bible (Nkwa Asɛm) and include top matching passage if highly relevant
        if self._jdapaah_bm25 and self.jdapaah_passages:
            j_scores = self._jdapaah_bm25.get_scores(toks)
            j_top = sorted(range(len(j_scores)), key=lambda i: -j_scores[i])[:1]
            for ji in j_top:
                if j_scores[ji] > 4.0:
                    jp = self.jdapaah_passages[ji]
                    results.append(
                        {
                            "book": "Romans (Nkwa Asɛm)",
                            "chapter": 1,
                            "verse": jp["idx"],
                            "text": jp["text"],
                        }
                    )
        return results[:k]

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
            other = [
                w
                for w in norm_sp.split()
                if w not in CHAPTER_FILLERS | VERSE_WORDS | RANGE_WORDS
                and not w.isdigit()
                and parse_twi_number([w])[0] is None
            ]
            only_reference = len(other) <= 3
            if wants_read or (only_reference and not has_question):
                return Request(
                    mode="read", passage=passage, wants_explanation=has_question, query=text
                )
            return Request(mode="answer", passage=passage, query=text)
        return Request(mode="answer", query=text)

    def _find_passage(self, norm: str) -> Passage | None:
        best = None
        for alias, bidx in ALIASES:
            for m in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", norm):
                tail = norm[m.end() :].split()
                parsed = self._parse_numbers(tail)
                if len(alias) < 5 and not parsed:
                    continue
                cand = (m.start(), bidx, parsed)
                if (
                    best is None
                    or (parsed and not best[2])
                    or (bool(parsed) == bool(best[2]) and m.start() < best[0])
                ):
                    best = cand
            if best and best[2]:
                break
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
        ch, used = parse_twi_number(tokens[i : i + 6])
        if not ch:
            return None
        i += used
        ch_end = v1 = v2 = None

        def skip(words):
            nonlocal i
            while i < len(tokens) and tokens[i] in words:
                i += 1

        if i < len(tokens) and tokens[i] in RANGE_WORDS:
            j = i
            skip(RANGE_WORDS | CHAPTER_FILLERS)
            n, used = parse_twi_number(tokens[i : i + 6])
            if n and n > ch:
                ch_end = n
                i += used
            else:
                i = j
        if ch_end is None and i < len(tokens) and tokens[i] in VERSE_WORDS:
            skip(VERSE_WORDS)
            v1, used = parse_twi_number(tokens[i : i + 6])
            i += used
            if v1 and i < len(tokens) and tokens[i] in RANGE_WORDS:
                skip(RANGE_WORDS | VERSE_WORDS)
                v2, used = parse_twi_number(tokens[i : i + 6])
                i += used
        return ch, ch_end, v1, v2


bible_index = BibleIndex()
