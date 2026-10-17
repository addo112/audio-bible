"""
Build the Asante Twi Bible knowledge base.

Source: Hugging Face dataset `davidguzmanr/open-bible-resources`, config "Twi (Asante)".
This is the verse-split Open.Bible Asante Twi Bible (Biblica, CC BY-SA 4.0) — the same
source that coqui-ai/open-bible-scripts (split_verse_asante-twi.py) processes.

Only the text columns are read (parquet column projection over HTTP range requests),
so the ~20 GB of audio in the dataset is never downloaded.

Output:  data/bible_tw.jsonl   (one verse per line, canonical book order)

Usage:
    python scripts/build_bible_index.py
"""
import json
import os
import sys
import time

import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.services.bible_books import BOOKS, book_index  # noqa: E402

DATASET = "datasets/davidguzmanr/open-bible-resources"
CONFIG_DIR = "Twi (Asante)"
COLUMNS = ["text", "testament", "book", "chapter", "verse"]
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_FILE = os.path.join(OUT_DIR, "bible_tw.jsonl")


def main():
    fs = HfFileSystem()
    files = sorted(fs.glob(f"{DATASET}/{CONFIG_DIR}/*.parquet"))
    if not files:
        sys.exit("No parquet files found — check dataset path / network.")
    print(f"Found {len(files)} parquet files")

    verses: dict[tuple, dict] = {}
    unknown_books: set[str] = set()
    for i, path in enumerate(files, 1):
        t0 = time.time()
        with fs.open(path, "rb", block_size=2 * 1024 * 1024) as f:
            table = pq.ParquetFile(f).read(columns=COLUMNS)
        rows = table.to_pylist()
        for r in rows:
            bi = book_index(r["book"])
            if bi is None:
                unknown_books.add(r["book"])
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

    if unknown_books:
        print("WARNING: unmapped book names:", sorted(unknown_books))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as out:
        for key in sorted(verses):
            out.write(json.dumps(verses[key], ensure_ascii=False) + "\n")

    books_present = {k[0] for k in verses}
    print(f"\nWrote {len(verses)} verses from {len(books_present)} books -> {os.path.abspath(OUT_FILE)}")
    missing = [BOOKS[b]["en"] for b in range(len(BOOKS)) if b not in books_present]
    if missing:
        print("Books with no verses:", missing)


if __name__ == "__main__":
    main()
