"""
Run this ON YOUR OWN MACHINE, not in Claude — it processes local PDF files
that were never uploaded to this chat.

What it does:
  1. Reads every PDF in a folder (e.g. the 20 GISIS investigation reports
     you downloaded, typically named like C1000917-MHL-R01.pdf)
  2. Extracts the text of each report
  3. Splits long reports into ~500-word chunks (full investigation reports
     run several pages — one chunk per doc would be too coarse for retrieval)
  4. Writes everything to investigation_reports_corpus.jsonl in the SAME
     schema as rag_corpus.jsonl, so it can be merged directly

Setup (run once):
    pip install pypdf

Usage:
    python3 extract_investigation_reports.py /path/to/your/pdf/folder

Output:
    investigation_reports_corpus.jsonl  (in the same folder you run this from)

After running, either:
  (a) merge locally:  cat rag_corpus.jsonl investigation_reports_corpus.jsonl > full_rag_corpus.jsonl
  (b) or just upload the resulting investigation_reports_corpus.jsonl file
      back to this chat — it'll be a few hundred KB at most, not 20 PDFs —
      and I'll merge it with the existing corpus for you.
"""

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

CHUNK_WORDS = 500
CHUNK_OVERLAP_WORDS = 50


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    return text


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_words=CHUNK_WORDS, overlap=CHUNK_OVERLAP_WORDS):
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_words
        chunks.append(" ".join(words[start:end]))
        start = end - overlap
        if start >= len(words):
            break
    return chunks


def parse_reference_from_filename(filename: str) -> str:
    # expects a pattern like C1000917-MHL-R01.pdf -> reference C1000917
    match = re.match(r"([A-Z]\d+)", filename)
    return match.group(1) if match else filename


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 extract_investigation_reports.py /path/to/pdf/folder")
        sys.exit(1)

    folder = Path(sys.argv[1])
    pdf_files = sorted(folder.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files in {folder}")

    docs = []
    for pdf_path in pdf_files:
        try:
            raw_text = extract_text(pdf_path)
        except Exception as e:
            print(f"  FAILED to extract {pdf_path.name}: {e}")
            continue

        text = clean_text(raw_text)
        if not text:
            print(f"  WARNING: {pdf_path.name} produced no extractable text "
                  f"(likely a scanned/image-only PDF — would need OCR, skipped)")
            continue

        reference = parse_reference_from_filename(pdf_path.stem)
        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            docs.append({
                "id": f"{reference}_report_chunk{i}",
                "text": chunk,
                "metadata": {
                    "reference": reference,
                    "source_file": pdf_path.name,
                    "doc_type": "full_investigation_report",
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            })
        print(f"  {pdf_path.name}: {len(chunks)} chunk(s), {len(text.split())} words")

    out_path = Path("investigation_reports_corpus.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(docs)} chunks from {len(pdf_files)} PDFs -> {out_path}")
    print("This file is small (text only) — safe to upload back to the chat if you want it merged there.")


if __name__ == "__main__":
    main()
