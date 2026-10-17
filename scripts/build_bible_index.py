"""
Build the Asante Twi Bible knowledge base (`data/bible_tw.jsonl` & `data/jdapaah_asante_twi_bible.jsonl`).

Integrates:
1. `coqui-ai/open-bible-scripts/blob/main/split_verse_asante-twi.py` USFM (`\\c`, `\\v`)
   and timing-file verse-splitting pipeline (adapted to preserve Akan vowels `ɛ`, `ɔ`).
2. `davidguzmanr/open-bible-resources` ("Twi (Asante)") — the 30,565-verse Open.Bible
   Asante Twi dataset produced from the Open-Bible USFM splits.
3. `jdapaah/asante-twi-bible` on Hugging Face — Asante Twi *Nkwa Asɛm* passages with
   paired audio alignments.

Usage:
    python scripts/build_bible_index.py
"""
from __future__ import annotations

from collections import defaultdict
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.bible_books import BOOKS, book_index  # noqa: E402

DATASET = "datasets/davidguzmanr/open-bible-resources"
CONFIG_DIR = "Twi (Asante)"
COLUMNS = ["text", "testament", "book", "chapter", "verse"]
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_FILE = os.path.join(OUT_DIR, "bible_tw.jsonl")
JDAPAAH_FILE = os.path.join(OUT_DIR, "jdapaah_asante_twi_bible.jsonl")


# ---------------------------------------------------------------------------
# Adapted from coqui-ai/open-bible-scripts/blob/main/split_verse_asante-twi.py
# Preserves Akan characters (ɛ, ɔ, Ɛ, Ɔ) that the original ASCII regex stripped.
# ---------------------------------------------------------------------------
_AKAN_CLEAN_RE = re.compile(r"[^a-zA-Z0-9ɛɔƐƆ?'’‘´`,.;:!-]+")


def parse_usfm_book(path_to_book_sfm: str) -> dict[str, list[str]]:
    """
    Parse an Open.Bible USFM (.SFM) book file into {chapter_str: [verse_1, verse_2, ...]}.
    Adapted directly from `coqui-ai/open-bible-scripts/split_verse_asante-twi.py`
    with full Unicode support for Asante Twi (`ɛ`, `ɔ`).
    """
    dict_chap_verse: dict[str, list[str]] = defaultdict(list)
    current_chap = None
    current_verse = None

    with open(path_to_book_sfm, "r", encoding="utf-8") as f:
        for textline in f:
            current_txt = textline.split()
            if len(current_txt) == 0:
                continue
            if current_txt[0] == "\\c":
                current_chap = current_txt[1]
                current_verse = None
                continue

            if current_txt[0] == "\\v":
                current_verse = current_txt[1]
                raw = textline[len(current_txt[0] + current_txt[1]) + 2 :]
                content = _AKAN_CLEAN_RE.sub(" ", raw).strip()
                dict_chap_verse[current_chap].append(content)
            elif len(current_txt) == 1:
                continue
            elif current_chap and current_verse:
                raw = textline[len(current_txt[0]) + 2 :]
                content = _AKAN_CLEAN_RE.sub(" ", raw).strip()
                idx = int(current_verse) - 1
                if 0 <= idx < len(dict_chap_verse[current_chap]):
                    dict_chap_verse[current_chap][idx] += " " + content

    return dict_chap_verse


def parse_verse_timings(timing_file_path: str) -> dict[str, list[str]]:
    """
    Parse an Open.Bible Audacity/Sabda timing file into {Verse_001: [start, end]}.
    Adapted from `coqui-ai/open-bible-scripts/split_verse_asante-twi.py`.
    """
    dict_verse_time: dict[str, list[str]] = defaultdict(list)
    with open(timing_file_path, "r", encoding="utf-8") as f:
        for textline in f:
            verse_time = textline.split("\t")
            if len(verse_time) == 1 or len(verse_time[0].split()) == 1:
                continue
            parts = verse_time[0].split()
            if len(parts) < 2:
                continue
            verse, number = parts[0], parts[1]
            if verse != "Verse":
                continue
            t_val = verse_time[1].strip()
            dict_verse_time[f"{verse}_{number.zfill(3)}"].append(t_val)
            if int(number) - 1 > 0:
                dict_verse_time[f"{verse}_{str(int(number) - 1).zfill(3)}"].append(t_val)
    return dict_verse_time


def fetch_jdapaah_dataset() -> None:
    """Download `jdapaah/asante-twi-bible` (Nkwa Asɛm) from Hugging Face Datasets Server."""
    os.makedirs(OUT_DIR, exist_ok=True)
    url = (
        "https://datasets-server.huggingface.co/rows"
        "?dataset=jdapaah/asante-twi-bible&config=default&split=train&offset=0&length=100"
    )
    req = urllib.request.urlopen(url, timeout=30)
    payload = json.loads(req.read().decode("utf-8"))
    rows = [
        r["row"]["sentence"].strip()
        for r in payload.get("rows", [])
        if r.get("row", {}).get("sentence")
    ]
    with open(JDAPAAH_FILE, "w", encoding="utf-8") as f:
        for i, text in enumerate(rows, 1):
            f.write(
                json.dumps(
                    {
                        "book": "Romans",
                        "source": "jdapaah/asante-twi-bible (Nkwa Asɛm)",
                        "idx": i,
                        "text": text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"Wrote {len(rows)} passages from jdapaah/asante-twi-bible -> {JDAPAAH_FILE}")


def build_open_bible_index() -> None:
    """Download verse-split Open.Bible Asante Twi verses from Hugging Face."""
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    fs = HfFileSystem()
    files = sorted(fs.glob(f"{DATASET}/{CONFIG_DIR}/*.parquet"))
    if not files:
        sys.exit("No parquet files found — check dataset path / network.")
    print(f"Found {len(files)} parquet files")

    verses: dict[tuple, dict] = {}
    for i, path in enumerate(files, 1):
        t0 = time.time()
        with fs.open(path, "rb", block_size=2 * 1024 * 1024) as f:
            table = pq.ParquetFile(f).read(columns=COLUMNS)
        rows = table.to_pylist()
        for r in rows:
            bi = book_index(r["book"])
            if bi is None:
                continue
            ch, vs = int(r["chapter"]), int(r["verse"])
            text = " ".join((r["text"] or "").split())
            if not text:
                continue
            verses[(bi, ch, vs)] = {
                "book": BOOKS[bi]["en"],
                "chapter": ch,
                "verse": vs,
                "text": text,
            }
        print(f"[{i}/{len(files)}] {os.path.basename(path)}: {len(rows)} rows in {time.time() - t0:.1f}s")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as out:
        for key in sorted(verses):
            out.write(json.dumps(verses[key], ensure_ascii=False) + "\n")
    print(f"Wrote {len(verses)} verses -> {os.path.abspath(OUT_FILE)}")


def main():
    fetch_jdapaah_dataset()
    if not os.path.exists(OUT_FILE):
        build_open_bible_index()
    else:
        print(f"Open.Bible index already present at {OUT_FILE}")


if __name__ == "__main__":
    main()
