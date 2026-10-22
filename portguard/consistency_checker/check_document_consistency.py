#!/usr/bin/env python3
"""Cross-document consistency checks for PortGuard structured predictions.

Reads the predictions JSON created by the OCR field-extraction scripts and compares
fields that should normally agree across document types within the same synthetic
inspection case. It does NOT use ground-truth labels and does NOT correct values.
It only reports matches, discrepancies, and missing values for review.

Usage from the project directory:
  python portguard_ocr_starter/scripts/check_document_consistency.py \
    portguard_ocr_starter/outputs/predictions_scan_like.json

Optional second argument: output report path.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

# Which document types should normally contain the same field for this project’s
# synthetic starter templates. Expand this list only when new templates/real forms
# are reviewed with a domain expert.
FIELD_DOCUMENT_TYPES = {
    "container_number": {"DG", "PACK", "SHIP"},
    "seal_number": {"DG", "PACK", "SHIP"},
    "un_number": {"DG", "PACK", "SDS", "SHIP"},
    "hazard_class": {"DG", "PACK", "SDS", "SHIP"},
    "packing_group": {"DG", "SDS"},
}


def normalize(field: str, value) -> str:
    if value is None:
        return ""
    s = str(value).strip().upper()
    s = re.sub(r"\s+", " ", s)
    if field == "un_number":
        m = re.search(r"\bUN\s*[-:]?\s*(\d{4})\b", s)
        if m:
            return f"UN {m.group(1)}"
    if field == "packing_group":
        # Only normalise spaces/case. Do not map I, II and III into each other.
        return s.replace(" ", "")
    if field == "container_number":
        return re.sub(r"\s+", "", s)
    if field == "seal_number":
        return re.sub(r"\s+", "", s)
    return s


def load_predictions(path: Path):
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def document_type(document_id: str) -> str:
    # Starter IDs look like 001-DG, 001-SDS, 001-PACK, and 001-SHIP.
    return document_id.rsplit("-", 1)[-1].upper() if "-" in document_id else ""


def case_id(document_id: str) -> str:
    return document_id.split("-", 1)[0]


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python check_document_consistency.py predictions.json [report.json]")
        raise SystemExit(2)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) == 3 else input_path.with_name(
        input_path.stem.replace("predictions", "consistency_report") + ".json"
    )

    records = load_predictions(input_path)
    by_case = defaultdict(dict)
    for record in records:
        doc_id = str(record.get("document_id", ""))
        if not doc_id:
            continue
        by_case[case_id(doc_id)][document_type(doc_id)] = {
            "document_id": doc_id,
            "fields": record.get("fields", {}) or {},
        }

    findings = []
    counts = {"match": 0, "mismatch": 0, "missing": 0, "insufficient_sources": 0}

    for case, docs in sorted(by_case.items()):
        for field, expected_types in FIELD_DOCUMENT_TYPES.items():
            applicable = [docs[t] for t in sorted(expected_types) if t in docs]
            if len(applicable) < 2:
                continue

            observations = []
            missing_docs = []
            for doc in applicable:
                raw = doc["fields"].get(field, "")
                norm = normalize(field, raw)
                if norm:
                    observations.append({
                        "document_id": doc["document_id"],
                        "document_type": document_type(doc["document_id"]),
                        "value": str(raw),
                        "normalized_value": norm,
                    })
                else:
                    missing_docs.append(doc["document_id"])

            distinct = sorted({o["normalized_value"] for o in observations})
            if len(distinct) > 1:
                status = "mismatch"
                message = "Values disagree across documents; do not auto-correct. Review source documents."
            elif missing_docs and observations:
                status = "missing"
                message = "At least one applicable document has no extracted value; verify the original document."
            elif len(observations) >= 2:
                status = "match"
                message = "Extracted values agree across the available documents."
            else:
                status = "insufficient_sources"
                message = "Not enough extracted values to compare this field."

            counts[status] += 1
            if status != "match":
                findings.append({
                    "case_id": case,
                    "field": field,
                    "status": status,
                    "observations": observations,
                    "missing_documents": missing_docs,
                    "message": message,
                })

    report = {
        "input_file": str(input_path),
        "synthetic_dataset_note": "Field/document applicability is configured for the PortGuard starter templates; validate against approved real document layouts before operational use.",
        "automatic_correction": False,
        "summary": counts,
        "findings": findings,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Cases inspected: {len(by_case)}")
    print(f"Consistency issues requiring review: {len(findings)}")
    for item in findings:
        values = ", ".join(
            f"{o['document_type']}={o['value']!r}" for o in item["observations"]
        ) or "no values extracted"
        missing = f"; missing in {', '.join(item['missing_documents'])}" if item["missing_documents"] else ""
        print(f"- Case {item['case_id']} | {item['field']} | {item['status']} | {values}{missing}")
    print(f"Report saved to: {output_path}")
    print("This report flags issues only; it never decides which conflicting value is correct.")


if __name__ == "__main__":
    main()
