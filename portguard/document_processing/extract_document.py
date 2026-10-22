#!/usr/bin/env python3
"""Portable PortGuard PDF text/OCR extractor adapted from the teammate prototype.

- Uses embedded PDF text when the page has a sufficiently useful text layer.
- Automatically OCRs scanned/sparse-text pages.
- Assesses image quality heuristically and preprocesses degraded pages.
- Extracts a conservative set of labeled fields; uncertain fields remain None.
- Can be imported by the PortGuard inspection runner or run from the CLI.

This is a development baseline, not a validated customs-document parser.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

from portguard.document_processing.field_aliases import FIELD_ALIASES


# Cross-platform Tesseract config. On macOS/Linux, PATH normally resolves it;
# on Windows, users may set TESSERACT_CMD to their installation path.
_env_tesseract = os.environ.get("TESSERACT_CMD", "").strip()
if _env_tesseract:
    pytesseract.pytesseract.tesseract_cmd = _env_tesseract


def _require_tesseract() -> None:
    cmd = str(pytesseract.pytesseract.tesseract_cmd)
    if cmd != "tesseract" and not Path(cmd).is_file():
        raise FileNotFoundError(
            f"Tesseract executable not found at {cmd!r}. Set TESSERACT_CMD to its path."
        )
    if cmd == "tesseract" and shutil.which("tesseract") is None:
        raise FileNotFoundError(
            "Tesseract is not on PATH. Install it and/or set the TESSERACT_CMD environment variable."
        )


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def clean_value(value: Any) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value)).strip().strip(" :\t|-")
    if not value:
        return None
    if re.match(r"^(not specified|not supplied|not provided|not available)\b", value, re.I):
        return None
    if value.lower() in {"unknown", "n/a", "na", "none", "null", "-", "—"}:
        return None
    return value


def get_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def assess_image_quality(image: Image.Image) -> dict[str, Any]:
    """A simple heuristic for display/preprocessing, not a trained classifier."""
    gray = ImageOps.grayscale(image)
    contrast_std = round(float(ImageStat.Stat(gray).stddev[0]), 2)
    edge_std = round(float(ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).stddev[0]), 2)
    # Calibrated as a demonstration heuristic against this starter pack. Real scans,
    # camera photos, resolution, and layouts can have very different metric ranges.
    quality = "degraded" if (contrast_std < 60.0 or edge_std < 29.1) else "clean"
    return {
        "quality_assessment": quality,
        "contrast_stddev": contrast_std,
        "edge_stddev": edge_std,
        "assessment_note": "Heuristic based on grayscale contrast and edge variation; not a validated quality classifier.",
    }


def preprocess_for_ocr(image: Image.Image, quality: str) -> tuple[Image.Image, str]:
    if quality != "degraded":
        return image.convert("RGB"), "original image"
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)
    gray = ImageEnhance.Sharpness(gray).enhance(1.5)
    if gray.width < 1800:
        scale = min(2.0, 1800 / max(gray.width, 1))
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)))
    return gray, "automatic grayscale/autocontrast/sharpen/upscale"


def _meaningful_text_score(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def ocr_image(image: Image.Image, lang: str = "eng") -> tuple[str, dict[str, Any]]:
    _require_tesseract()
    quality = assess_image_quality(image)
    processed, preprocessing = preprocess_for_ocr(image, quality["quality_assessment"])
    # PSM 6 is a reasonable default for printed forms; field-specific crops are
    # handled by the existing image pipeline for the synthetic starter templates.
    text = pytesseract.image_to_string(processed, lang=lang, config="--psm 6").strip()
    metadata = dict(quality)
    metadata["preprocessing"] = preprocessing
    metadata["ocr_method"] = "Tesseract OCR"
    metadata["recognized_alphanumeric_characters"] = _meaningful_text_score(text)
    return text, metadata


def _has_useful_embedded_text(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip()
    words = re.findall(r"\b[\w-]+\b", compact)
    chars = sum(ch.isalnum() for ch in compact)
    # Sparse hidden OCR/text layers are often incomplete for scanned PDFs;
    # render and OCR those pages instead. Thresholds are intentionally modest.
    return chars >= 60 and len(words) >= 8


def extract_pdf_text_detailed(pdf_path: str | Path) -> tuple[str, str, list[dict[str, Any]]]:
    """Extract each page from PDF text layer or OCR, automatically page by page."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    page_texts: list[str] = []
    page_details: list[dict[str, Any]] = []
    used_methods: set[str] = set()

    with pymupdf.open(pdf_path) as document:
        if len(document) == 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")
        for page_idx, page in enumerate(document, start=1):
            native_text = page.get_text("text").strip()
            if _has_useful_embedded_text(native_text):
                text = native_text
                method = "embedded PDF text"
                quality_meta = {"quality_assessment": "digital-text-layer", "assessment_note": "Used readable embedded PDF text; no OCR quality selection was needed."}
                preprocessing = "not needed"
            else:
                _require_tesseract()
                pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text, quality_meta = ocr_image(image)
                method = "OCR fallback (page had no/sparse embedded text)"
                preprocessing = quality_meta.get("preprocessing", "automatic")
                if native_text:
                    quality_meta["native_text_characters"] = _meaningful_text_score(native_text)
            page_texts.append(text)
            used_methods.add(method)
            page_details.append({
                "page_number": page_idx,
                "method": method,
                "preprocessing": preprocessing,
                **quality_meta,
                "recognized_alphanumeric_characters": _meaningful_text_score(text),
            })

    combined_text = "\n\n".join(page_texts).strip()
    if not combined_text:
        raise ValueError(f"No readable text was found in PDF: {pdf_path.name}")
    if len(used_methods) > 1:
        summary_method = "mixed embedded PDF text and OCR"
    else:
        summary_method = next(iter(used_methods))
    return combined_text, summary_method, page_details


def extract_pdf_text(pdf_path: str | Path) -> tuple[str, str]:
    text, method, _details = extract_pdf_text_detailed(pdf_path)
    return text, method


def _raw_remainder_after_normalized_prefix(line: str, normalized_prefix_len: int) -> str:
    consumed = 0
    idx = 0
    while idx < len(line) and consumed < normalized_prefix_len:
        if line[idx].isalnum():
            consumed += 1
        idx += 1
    return line[idx:].strip()


def find_label_value(text: str, field_name: str) -> str | None:
    aliases = FIELD_ALIASES.get(field_name, [])
    lines = get_lines(text)
    normalized_aliases = sorted(
        {(normalize_label(alias), alias) for alias in aliases if normalize_label(alias)},
        key=lambda item: len(item[0]), reverse=True,
    )
    all_normalized_labels = {
        normalize_label(alias) for values in FIELD_ALIASES.values() for alias in values
    }

    for i, line in enumerate(lines):
        # Common SDS labels are numbered (e.g. "14.3 Transport hazard class(es)").
        # Remove only a leading section-number token before comparing aliases.
        comparable_line = re.sub(r"^\s*\d+(?:\.\d+)?\s*", "", line)
        normalized_line = normalize_label(comparable_line)
        for norm_alias, _alias in normalized_aliases:
            if not normalized_line.startswith(norm_alias):
                continue
            remainder = _raw_remainder_after_normalized_prefix(comparable_line, len(norm_alias))
            remainder = re.sub(r"^[\s:;|=\-–—()]+", "", remainder).strip()
            # A remainder that is clearly another label is not this field's value.
            if remainder and normalize_label(remainder) not in all_normalized_labels:
                candidate = clean_value(remainder)
                if candidate:
                    return candidate
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_norm = normalize_label(next_line)
                is_next_label = any(
                    next_norm.startswith(alias)
                    for alias in all_normalized_labels
                    if len(alias) >= 4
                )
                if not is_next_label:
                    candidate = clean_value(next_line)
                    if candidate:
                        return candidate
    return None


def extract_un_number(text: str) -> str | None:
    value = find_label_value(text, "un_number")
    candidate = value or text
    m = re.search(r"\bUN\s*(?:Number|No\.?|#)?\s*[:#-]?\s*(\d{4})\b", candidate, re.I)
    if m:
        return f"UN {m.group(1)}"
    m = re.search(r"\bUN\s*(\d{4})\b", text, re.I)
    return f"UN {m.group(1)}" if m else None


def extract_proper_shipping_name(text: str) -> str | None:
    """Extract PSN across wrapped lines without consuming the next field label."""
    aliases = sorted(
        {normalize_label(a) for a in FIELD_ALIASES.get("proper_shipping_name", []) if normalize_label(a)},
        key=len, reverse=True,
    )
    lines = get_lines(text)
    all_labels = {
        normalize_label(alias)
        for values in FIELD_ALIASES.values()
        for alias in values
        if len(normalize_label(alias)) >= 4
    }

    for idx, line in enumerate(lines):
        comparable = re.sub(r"^\s*\d+(?:\.\d+)?\s*", "", line)
        norm = normalize_label(comparable)
        match_alias = next((alias for alias in aliases if norm.startswith(alias)), None)
        if not match_alias:
            continue
        remainder = _raw_remainder_after_normalized_prefix(comparable, len(match_alias))
        remainder = re.sub(r"^[\s:;|=\-–—()]+", "", remainder).strip()
        candidates: list[str] = []
        if remainder and normalize_label(remainder) not in all_labels:
            candidates.append(remainder)
        else:
            for next_line in lines[idx + 1:]:
                next_comparable = re.sub(r"^\s*\d+(?:\.\d+)?\s*", "", next_line)
                next_norm = normalize_label(next_comparable)
                if any(next_norm.startswith(label) for label in all_labels):
                    break
                candidates.append(next_line)
                # PSNs are generally a single line or a wrap ending in a short continuation
                # like "N.O.S."; stop after two lines unless the first was clearly incomplete.
                joined_now = " ".join(candidates).strip()
                if len(candidates) >= 2 and not joined_now.rstrip().endswith((",", "/", "-")):
                    break
                if len(candidates) >= 3:
                    break
        value = re.sub(r"\s+", " ", " ".join(candidates)).strip(" :|-–—")
        if value:
            # If a label/value extractor captured a comma-ended first line, append a short
            # non-label continuation such as N.O.S. when present.
            if value.endswith(",") and idx + 1 < len(lines):
                continuation = lines[idx + 1]
                if normalize_label(continuation) not in all_labels:
                    value = f"{value} {continuation}"
            return clean_value(value)
    return find_label_value(text, "proper_shipping_name")


def extract_hazard_class(text: str) -> str | None:
    value = find_label_value(text, "imdg_class")
    if value:
        m = re.search(r"\b([1-9](?:\.\d)?)\b", value)
        if m:
            return m.group(1)
    return None


def extract_packing_group(text: str) -> str | None:
    value = find_label_value(text, "packing_group")
    if value:
        m = re.search(r"\b(I{1,3}|III|II|I)\b", value, re.I)
        if m:
            token = m.group(1).upper().replace("L", "I").replace("1", "I").replace("|", "I")
            if token in {"I", "II", "III"}:
                return token
    return None


def extract_container_number(text: str) -> str | None:
    # Common ISO-style OCR forms: ABCU1234567 or ABCU123456-7.
    m = re.search(r"\b([A-Z]{4}\s*\d{6,7}(?:\s*-\s*\d)?)\b", text, re.I)
    if not m:
        return find_label_value(text, "container_number")
    return re.sub(r"\s+", "", m.group(1)).upper().replace("-", "")


def extract_weight(text: str, field_name: str) -> float | None:
    """Extract cargo gross/net weight, avoiding unlabeled guesses and container tare."""
    lines = get_lines(text)
    start = 0
    end = len(lines)

    # On dangerous-goods declarations, prefer the dangerous-goods item section.
    for index, line in enumerate(lines):
        if "dangerousgoodsdescription" in normalize_label(line):
            start = index
            break
    for index in range(start + 1, len(lines)):
        if normalize_label(lines[index]) in {"declarations", "shipperdeclaration", "declaration"}:
            end = index
            break
    section_text = "\n".join(lines[start:end])

    aliases = FIELD_ALIASES.get(field_name, [])
    if field_name == "gross_weight_kg":
        aliases = [a for a in aliases if normalize_label(a) not in {"totalgrossmass", "totalgrossweight"}]
    normalized_aliases = sorted({normalize_label(a) for a in aliases if normalize_label(a)}, key=len, reverse=True)
    section_lines = get_lines(section_text)

    for index, line in enumerate(section_lines):
        comparable = re.sub(r"^\s*\d+(?:\.\d+)?\s*", "", line)
        normalized_line = normalize_label(comparable)
        for alias in normalized_aliases:
            if not alias or not normalized_line.startswith(alias):
                continue
            remainder = _raw_remainder_after_normalized_prefix(comparable, len(alias))
            remainder = re.sub(r"^\s*(?:\([^)]*\))?\s*[:=\-–—]?\s*", "", remainder)
            if remainder:
                # Do not take the first random number unless the label/value relation is local.
                match = re.search(r"\d+(?:[.,]\d+)?", remainder)
                if match:
                    return float(match.group(0).replace(",", "."))
            if index + 1 < len(section_lines):
                next_line = section_lines[index + 1]
                match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kgs)?\s*", next_line, re.I)
                if match:
                    return float(match.group(1).replace(",", "."))

    value = find_label_value(section_text, field_name)
    if value:
        match = re.search(r"\d+(?:[.,]\d+)?", value)
        if match:
            return float(match.group(0).replace(",", "."))
    return None


def extract_marine_pollutant(text: str) -> bool | None:
    value = find_label_value(text, "marine_pollutant")
    if value is None:
        return None
    value_lower = value.lower().strip()
    if value_lower in {"yes", "true", "y"}:
        return True
    if value_lower in {"no", "false", "n"}:
        return False
    return None


def extract_ems(text: str) -> str | None:
    fire = find_label_value(text, "ems_fire")
    spillage = find_label_value(text, "ems_spillage")
    if fire and spillage:
        return f"{fire} / {spillage}"
    if fire:
        return fire
    if spillage:
        return spillage
    return find_label_value(text, "ems_code")


def extract_fields_from_text(text: str) -> dict[str, Any]:
    """Shared parser used by PDF-native text, PDF OCR, and uploaded images."""
    fields: dict[str, Any] = {
        "un_number": extract_un_number(text),
        "proper_shipping_name": extract_proper_shipping_name(text),
        "hazard_class": extract_hazard_class(text),
        "subsidiary_hazard": find_label_value(text, "subsidiary_hazard"),
        "packing_group": extract_packing_group(text),
        "container_number": extract_container_number(text),
        "seal_number": find_label_value(text, "seal_number"),
        "gross_weight_kg": extract_weight(text, "gross_weight_kg"),
        "net_weight_kg": extract_weight(text, "net_weight_kg"),
        "marine_pollutant": extract_marine_pollutant(text),
        "ems_code": extract_ems(text),
        "port_of_loading": find_label_value(text, "port_of_loading"),
        "port_of_discharge": find_label_value(text, "port_of_discharge"),
    }
    return {key: clean_value(value) if isinstance(value, str) else value for key, value in fields.items()}


def applicable_fields(document_type: str) -> list[str]:
    document_type = document_type.upper()
    map_fields = {
        "DG": ["un_number", "proper_shipping_name", "hazard_class", "packing_group", "container_number", "seal_number"],
        "PACK": ["container_number", "seal_number", "gross_weight_kg"],
        "SDS": ["un_number", "proper_shipping_name", "hazard_class"],
        "SHIP": ["container_number", "seal_number", "un_number", "hazard_class"],
    }
    return map_fields.get(document_type, ["un_number", "proper_shipping_name", "hazard_class"])


def extract_document(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    text, extraction_method, page_details = extract_pdf_text_detailed(pdf_path)
    fields = extract_fields_from_text(text)
    doc_type = pdf_path.stem.rsplit("-", 1)[-1].upper()
    missing_fields = [field for field in applicable_fields(doc_type) if not fields.get(field)]
    return {
        "document_id": pdf_path.stem,
        "source_file": pdf_path.name,
        "extraction_method": extraction_method,
        "page_details": page_details,
        "fields": fields,
        "review_required": bool(missing_fields),
        "review_issues": [f"Missing or unreadable field: {field}" for field in missing_fields],
        "extracted_text": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract PortGuard fields from a PDF using embedded text with automatic OCR fallback.")
    parser.add_argument("pdf", type=Path, help="Input PDF file")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON file (default: alongside input PDF)")
    args = parser.parse_args()
    result = extract_document(args.pdf)
    output_path = args.output or args.pdf.with_name(f"{args.pdf.stem}_extracted.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "extracted_text"}, indent=2, ensure_ascii=False))
    print(f"Saved extraction output to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
