#!/usr/bin/env python3
"""Baseline field extraction from PortGuard OCR raw text (synthetic starter dataset).

This is a transparent regex/rule baseline, not a trained model. It only extracts
values supported by OCR text and leaves uncertain/missing fields blank.
"""
from pathlib import Path
import json
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT / "portguard_ocr_starter"

DEFAULT_INPUT = ROOT / "outputs" / "ocr_raw_clean.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "predictions.json"

def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def canon_seal(value: str) -> str:
    """Correct common OCR glyph confusions in this synthetic seal-ID format."""
    value = re.sub(r"\s+", "", value.upper())
    if not value.startswith("SYNSEAL"):
        return value
    suffix = value[len("SYNSEAL"):]
    suffix = suffix.replace("O", "0").replace("I", "1").replace("L", "1")
    # The synthetic IDs use a three-digit suffix. OCR can duplicate a leading 0.
    if len(suffix) > 3 and suffix.isdigit():
        suffix = suffix[-3:]
    return "SYNSEAL" + suffix if suffix.isdigit() else value


def find_first(patterns, text, flags=re.IGNORECASE | re.DOTALL):
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return compact(m.group(1))
    return ""


def extract_container(text):
    m = re.search(r"\b([A-Z]{4}\s*\d{7})\b", text.upper())
    return re.sub(r"\s+", "", m.group(1)) if m else ""


def extract_seal(text):
    m = re.search(r"\b(SYNSEAL[0-9OIL]{2,5})\b", text.upper())
    return canon_seal(m.group(1)) if m else ""


def extract_un(text):
    m = re.search(r"\bUN\s*[-:]?\s*(\d{4})\b", text.upper())
    return f"UN {m.group(1)}" if m else ""


def extract_hazard_class(text):
    upper = text.upper()
    # Prefer the value close to a hazard-class label, avoiding UN number digits.
    for m in re.finditer(r"HAZARD CLASS(?:\s*\(DECLARED\)|\s*SHOWN)?", upper):
        window = upper[m.end():m.end() + 100]
        val = re.search(r"(?<![A-Z0-9])([1-9])(?!(?:[A-Z0-9]))", window)
        if val:
            return val.group(1)
    return ""


def extract_packing_group(text):
    upper = text.upper()
    for m in re.finditer(r"PACKING GROUP(?:\s*\(IF APPLICABLE\))?", upper):
        window = upper[m.end():m.end() + 70]
        # Typical printed/OCR forms: II, III, ll, lll, and a class number followed by the group.
        val = re.search(r"^\s*[:|]?\s*(?:[89]\s+)?([IL1|]{1,4})\b", window)
        if not val:
            continue
        raw = val.group(1).replace("|", "I").replace("L", "I").replace("1", "I")
        raw = raw.upper()
        if raw in {"I", "II", "III"}:
            return raw
    return ""


def extract_proper_shipping_name(text):
    upper = compact(text.upper())
    # Recognize the names present in this synthetic test pack only if actually present in OCR.
    candidates = [
        "ENVIRONMENTALLY HAZARDOUS SUBSTANCE, LIQUID, N.O.S.",
        "CORROSIVE LIQUID, N.O.S.",
    ]
    for candidate in candidates:
        if candidate in upper:
            return candidate
    return ""


def extract_packages(text):
    m = re.search(r"\b(\d{1,5}\s+(?:DRUMS|IBCS|BAGS))\b", text.upper())
    if m:
        return compact(m.group(1)).lower().replace("ibcs", "IBCs")
    return ""


def extract_weight(text):
    # Packing-list layout: weight normally follows its label directly.
    m = re.search(
        r"GROSS\s+WEIGHT(?:\s*\(KG\))?\s*[:|]?\s*(\d{2,6})",
        text, re.IGNORECASE
    )
    if m:
        return m.group(1)

    # DG declaration layout: package count and gross mass may share the row beneath headings.
    upper = text.upper()
    m = re.search(
        r"GROSS\s+MASS(?:\s*\(KG\))?([\s\S]{0,100}?)(?:\bSHIPPER\b|\bCONSIGNEE\b)",
        upper
    )
    if m:
        nums = re.findall(r"\b\d{2,6}\b", m.group(1))
        if nums:
            return nums[-1]
    return ""


def extract_entity(text, role):
    # Known synthetic example names are exact literals in the input documents.
    # Search for the longest matching name first so a shorter substring does not win.
    if role == "shipper":
        pats = [
            r"(Example Chemicals Ltd\. \(fictional\))",
            r"(Sample Maritime Chemicals \(fictional\))",
            r"(Fictional Bulk Materials Co\.)",
        ]
    else:
        pats = [
            r"(Harbour Demo Depot \(fictional\))",
            r"(Coastal Test Warehouse \(fictional\))",
            r"(Example Portside Receiver \(fictional\))",
        ]
    for pat in pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return compact(m.group(1))

    # Fallback for differently formatted documents.
    label = "SHIPPER" if role == "shipper" else "CONSIGNEE"
    upper = text.upper()
    for m in re.finditer(rf"\b{label}\b", upper):
        after = text[m.end():m.end() + 160]
        after = re.sub(r"^\s*[:\-]?\s*", "", after)
        after = re.split(
            r"\b(?:CONTAINER NUMBER|SEAL NUMBER|UN NUMBER|HAZARD CLASS|PACKING GROUP|"
            r"PORT OF LOADING|PORT OF DISCHARGE|CARGO DESCRIPTION|GOODS DESCRIPTION|"
            r"GROSS (?:MASS|WEIGHT)|PACKAGES / PACKAGING)\b",
            after, maxsplit=1, flags=re.IGNORECASE
        )[0]
        mval = re.search(
            r"([A-Z][A-Za-z0-9&.,' -]{1,65}?(?:Ltd\.|Co\.|Depot|Warehouse|Receiver|"
            r"Materials|Chemicals)(?:\s*\(fictional\))?)",
            after, re.IGNORECASE
        )
        if mval and mval.group(1).strip():
            return compact(mval.group(1))
    return ""


def extract_reference(text, prefix):
    m = re.search(rf"\b({prefix}-\d{{3}})\b", text.upper())
    return m.group(1) if m else ""


def extract_cargo_description(text):
    # Field label when value follows on same line.
    m = re.search(
        r"(?:CARGO DESCRIPTION|GOODS DESCRIPTION)\s*:?\s*(Synthetic [^\n]+)",
        text, re.IGNORECASE
    )
    if m:
        return compact(m.group(1))
    upper = text.upper()
    for candidate in [
        "Synthetic corrosive test liquid",
        "Synthetic environmentally hazardous liquid",
        "Synthetic environmentally hazardous solid",
    ]:
        if candidate.upper() in upper:
            return candidate
    return ""


def extract_port(text, port_label):
    # Inline label/value where present.
    m = re.search(rf"{port_label}\s*:?\s*([A-Za-z][A-Za-z ]+(?:\(illustrative\))?)",
                  text, re.IGNORECASE)
    if m:
        value = compact(m.group(1))
        # Avoid consuming a following label in a flattened OCR line.
        value = re.split(r"\b(?:PORT OF DISCHARGE|CARGO DESCRIPTION|UN NUMBER|HAZARD CLASS)\b",
                         value, flags=re.IGNORECASE)[0].strip()
        if value:
            return value
    # Layout fallback: detect the explicitly printed illustrative port values.
    candidates = ["Mundra (illustrative)", "Hazira (illustrative)", "Kandla (illustrative)",
                  "JNPA region (illustrative)"]
    for candidate in candidates:
        if candidate.lower() in text.lower():
            if "loading" in port_label.lower() and candidate.lower() != "jnpa region (illustrative)":
                return candidate
            if "discharge" in port_label.lower() and candidate.lower() == "jnpa region (illustrative)":
                return candidate
    return ""


def extract_environmental_hazards(text):
    m = re.search(r"14\.5\s+Environmental hazards\s*:?\s*(Not stated in this synthetic example|Yes \(example field\))",
                  text, re.IGNORECASE)
    return compact(m.group(1)) if m else ""


def extract_product_identifier(text):
    m = re.search(r"\b(PG-SYN-[A-Z0-9-]+)\b", text.upper())
    return m.group(1) if m else ""


def extract_document(record):
    text = record.get("ocr_text", "")
    doc_id = record.get("document_id", "")
    suffix = doc_id.rsplit("-", 1)[-1]
    fields = {}

    # Shared fields (extract only when a value is found).
    fields["container_number"] = extract_container(text)
    fields["seal_number"] = extract_seal(text)
    fields["un_number"] = extract_un(text)
    fields["hazard_class"] = extract_hazard_class(text)

    if suffix in {"DG", "SDS"}:
        fields["proper_shipping_name"] = extract_proper_shipping_name(text)
        fields["packing_group"] = extract_packing_group(text)

    if suffix == "DG":
        fields["packages"] = extract_packages(text)
        fields["gross_weight_kg"] = extract_weight(text)
        fields["shipper"] = extract_entity(text, "shipper")
        fields["consignee"] = extract_entity(text, "consignee")

    elif suffix == "SHIP":
        fields["shipping_reference"] = extract_reference(text, "SYN-BL")
        fields["shipper"] = extract_entity(text, "shipper")
        fields["consignee"] = extract_entity(text, "consignee")
        fields["port_of_loading"] = extract_port(text, "Port of loading")
        fields["port_of_discharge"] = extract_port(text, "Port of discharge")
        fields["cargo_description"] = extract_cargo_description(text)

    elif suffix == "PACK":
        fields["packing_list_reference"] = extract_reference(text, "SYN-PL")
        fields["goods_description"] = extract_cargo_description(text)
        fields["packages"] = extract_packages(text)
        fields["gross_weight_kg"] = extract_weight(text)
        fields["consignee"] = extract_entity(text, "consignee")

    elif suffix == "SDS":
        fields["environmental_hazards"] = extract_environmental_hazards(text)
        fields["product_identifier"] = extract_product_identifier(text)

    # Keep blank values in output so missing extractions are explicit.
    return {"document_id": doc_id, "fields": fields}


def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    records = json.loads(input_path.read_text(encoding="utf-8"))
    predictions = [extract_document(r) for r in records]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Processed {len(predictions)} OCR records.")
    print(f"Structured predictions saved to: {output_path}")
    print("Note: this is a baseline extractor; inspect uncertain and missing fields before relying on results.")


if __name__ == "__main__":
    main()
