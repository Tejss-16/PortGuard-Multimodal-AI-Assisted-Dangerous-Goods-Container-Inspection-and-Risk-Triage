#!/usr/bin/env python3
"""PortGuard cross-document consistency checker v2.

Separates:
  * possible_ocr_error: a disagreement matches a known OCR-confusion pattern
    (currently packing-group Roman numerals, or identifier strings that become
    equal after conservative O/0 and I/1/L normalization);
  * value_disagreement: extracted values differ without a configured OCR-
    confusion pattern; this is NOT proof that the source documents conflict;
  * missing_value: at least one applicable document has no extracted value.

The script never auto-corrects a value and has no OCR confidence scores to rely on.
Its classifications are review hints, not safety decisions.

Usage from the project directory:
  python portguard_ocr_starter/scripts/check_document_consistency_v2.py \
      portguard_ocr_starter/outputs/predictions_scan_like.json

Optional second argument: report JSON path.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

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
    s = re.sub(r"\s+", " ", str(value).strip().upper())
    if field == "un_number":
        match = re.search(r"\bUN\s*[-:]?\s*(\d{4})\b", s)
        if match:
            return f"UN {match.group(1)}"
    if field in {"container_number", "seal_number"}:
        return re.sub(r"\s+", "", s)
    if field == "packing_group":
        return s.replace(" ", "")
    return s


def confusion_canonical(field: str, value: str) -> str:
    """Apply only conservative, common glyph-confusion mappings for triage."""
    s = normalize(field, value)
    if field == "packing_group":
        # OCR often confuses I, l, |, and 1. Do not collapse the number of marks:
        # I, II, and III must remain distinct.
        return re.sub(r"[L|1]", "I", s)
    if field == "container_number":
        # ISO-style IDs: in the final seven characters, O may be read as 0.
        if len(s) >= 7:
            prefix, suffix = s[:-7], s[-7:]
            return prefix + suffix.replace("O", "0")
    if field == "seal_number":
        # Apply only O/0 and I/1/L/1 equivalence. Other character changes remain.
        return s.replace("O", "0").replace("I", "1").replace("L", "1")
    return s


def classify_disagreement(field: str, observations: list[dict]) -> tuple[str, str]:
    vals = [o["normalized_value"] for o in observations]
    if field == "packing_group" and set(vals).issubset({"I", "II", "III", "1", "11", "111"}):
        return (
            "possible_ocr_error",
            "Packing-group values differ by Roman-numeral-like tokens. OCR confusion is possible, but a real source-document disagreement is also possible; inspect the original images.",
        )

    # If values differ literally but become identical under a conservative glyph
    # map, they may be OCR variants. Never replace the displayed values.
    canon = {confusion_canonical(field, o["value"]) for o in observations}
    if len(canon) == 1 and len(set(vals)) > 1:
        return (
            "possible_ocr_error",
            "Values differ only under a configured common OCR glyph-confusion check. Inspect the source image; no value has been corrected.",
        )

    return (
        "value_disagreement",
        "Extracted values disagree and do not match a configured OCR-confusion pattern. This is not proof of a source-document conflict; inspect the original documents and OCR output.",
    )


def load_predictions(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def document_type(document_id: str) -> str:
    return document_id.rsplit("-", 1)[-1].upper() if "-" in document_id else ""


def case_id(document_id: str) -> str:
    return document_id.split("-", 1)[0]


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print("Usage: python check_document_consistency_v2.py predictions.json [report.json]")
        raise SystemExit(2)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) == 3 else input_path.with_name(
        input_path.stem.replace("predictions", "consistency_report") + "_v2.json"
    )

    records = load_predictions(input_path)
    by_case: dict[str, dict[str, dict]] = defaultdict(dict)
    for record in records:
        doc_id = str(record.get("document_id", ""))
        if not doc_id:
            continue
        by_case[case_id(doc_id)][document_type(doc_id)] = {
            "document_id": doc_id,
            "fields": record.get("fields", {}) or {},
        }

    counts = {
        "match": 0,
        "possible_ocr_error": 0,
        "value_disagreement": 0,
        "missing_value": 0,
        "insufficient_sources": 0,
    }
    findings: list[dict] = []

    for case, docs in sorted(by_case.items()):
        for field, expected_types in FIELD_DOCUMENT_TYPES.items():
            applicable = [docs[t] for t in sorted(expected_types) if t in docs]
            if len(applicable) < 2:
                continue

            observations: list[dict] = []
            missing_docs: list[str] = []
            for doc in applicable:
                doc_id = doc["document_id"]
                doc_type = document_type(doc_id)
                raw = doc["fields"].get(field, "")
                norm = normalize(field, raw)
                if norm:
                    observations.append({
                        "document_id": doc_id,
                        "document_type": doc_type,
                        "value": str(raw),
                        "normalized_value": norm,
                    })
                else:
                    missing_docs.append(doc_id)

            distinct = {o["normalized_value"] for o in observations}
            has_disagreement = len(distinct) > 1
            has_missing = bool(missing_docs)

            if has_disagreement:
                classification, message = classify_disagreement(field, observations)
                counts[classification] += 1
                findings.append({
                    "case_id": case,
                    "field": field,
                    "classification": classification,
                    "observations": observations,
                    "missing_documents": missing_docs,
                    "reason": message,
                    "automatic_correction": False,
                })

            # Report missing data separately, even if a separate disagreement exists.
            if has_missing:
                counts["missing_value"] += 1
                findings.append({
                    "case_id": case,
                    "field": field,
                    "classification": "missing_value",
                    "observations": observations,
                    "missing_documents": missing_docs,
                    "reason": "At least one applicable document has no extracted value. This may reflect missing source information or OCR/field-extraction failure; check the original document.",
                    "automatic_correction": False,
                })

            if not has_disagreement and not has_missing and len(observations) >= 2:
                counts["match"] += 1
            elif not has_disagreement and not has_missing and len(observations) < 2:
                counts["insufficient_sources"] += 1
                findings.append({
                    "case_id": case,
                    "field": field,
                    "classification": "insufficient_sources",
                    "observations": observations,
                    "missing_documents": missing_docs,
                    "reason": "Not enough extracted values are available to compare this field.",
                    "automatic_correction": False,
                })

    report = {
        "input_file": str(input_path),
        "synthetic_dataset_note": "Field/document applicability is configured for PortGuard starter templates. Validate against approved real document layouts before use beyond research/testing.",
        "classification_note": "Possible OCR error is a rule-based review hint, not an OCR-confidence measurement. Value disagreement does not prove the source documents are wrong.",
        "automatic_correction": False,
        "summary": counts,
        "findings": findings,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Cases inspected: {len(by_case)}")
    print("Field comparison summary:")
    for key, value in counts.items():
        print(f"  {key.replace('_', ' ').title()}: {value}")
    print(f"Review findings: {len(findings)}")
    for item in findings:
        values = ", ".join(f"{o['document_type']}={o['value']!r}" for o in item["observations"]) or "no values extracted"
        missing = f"; missing in {', '.join(item['missing_documents'])}" if item["missing_documents"] else ""
        print(f"- Case {item['case_id']} | {item['field']} | {item['classification']} | {values}{missing}")
    print(f"Report saved to: {output_path}")
    print("Review the source documents. This script never decides which conflicting value is correct.")


if __name__ == "__main__":
    main()
