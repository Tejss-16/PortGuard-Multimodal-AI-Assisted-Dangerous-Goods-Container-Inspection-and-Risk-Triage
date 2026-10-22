#!/usr/bin/env python3
"""Improved OCR fallback for the PortGuard synthetic starter documents.

Keeps the baseline field extractor, retries only missing critical fields with
alternate Tesseract segmentation and label-guided crops, and leaves unresolved
values blank. Crop rules are tailored to this starter dataset's templates and
must be generalized before use on real-world forms.
"""
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps
from pytesseract import Output
import pytesseract
import json
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from portguard.document_processing.extract_fields_from_ocr import extract_document

ROOT = PROJECT_ROOT / "portguard_ocr_starter"
DEFAULT_INPUT = ROOT / "outputs" / "ocr_raw_clean.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "predictions_v2.json"

def compact(text):
    return re.sub(r"\s+", " ", text or "").strip()


def find_label_box(image, phrase):
    """Return bounding box around adjacent label words detected by Tesseract."""
    data = pytesseract.image_to_data(
        image, config="--psm 11", output_type=Output.DICT
    )
    wanted = phrase.upper().split()
    words = [str(x).strip().upper().strip(":|.,()") for x in data["text"]]
    for i in range(len(words) - len(wanted) + 1):
        if words[i:i + len(wanted)] != wanted:
            continue
        # Require label words to be on the same OCR line.
        line_keys = {
            (data["page_num"][j], data["block_num"][j], data["par_num"][j], data["line_num"][j])
            for j in range(i, i + len(wanted))
        }
        if len(line_keys) != 1:
            continue
        left = min(data["left"][j] for j in range(i, i + len(wanted)))
        top = min(data["top"][j] for j in range(i, i + len(wanted)))
        right = max(data["left"][j] + data["width"][j] for j in range(i, i + len(wanted)))
        bottom = max(data["top"][j] + data["height"][j] for j in range(i, i + len(wanted)))
        return left, top, right, bottom
    return None


def crop_ocr(image, box, whitelist, psm=7):
    """Upscale and OCR a small region with a field-appropriate character set."""
    x1, y1, x2, y2 = box
    x1 = max(0, min(image.width - 1, int(x1)))
    x2 = max(x1 + 1, min(image.width, int(x2)))
    y1 = max(0, min(image.height - 1, int(y1)))
    y2 = max(y1 + 1, min(image.height, int(y2)))
    crop = image.crop((x1, y1, x2, y2))
    crop = crop.resize((crop.width * 2, crop.height * 2))
    crop = ImageEnhance.Contrast(ImageOps.grayscale(crop)).enhance(2.0)
    config = f"--psm {psm} -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(crop, config=config).strip()


def normalize_packing_group(raw):
    token = re.sub(r"\s+", "", (raw or "").upper())
    token = token.replace("|", "I").replace("L", "I").replace("1", "I")
    return token if token in {"I", "II", "III"} else ""


def retry_missing_fields(record, original_prediction):
    fields = dict(original_prediction["fields"])
    missing_critical = [k for k in ("hazard_class", "packing_group") if not fields.get(k)]
    if not missing_critical:
        return {"document_id": record.get("document_id", ""), "fields": fields}

    image_path = ROOT / record.get("image_path", "")
    if not image_path.is_file():
        return {"document_id": record.get("document_id", ""), "fields": fields}

    with Image.open(image_path) as opened:
        image = opened.convert("RGB")

        # Secondary full-page pass. PSM 6 can recover values in table-style layouts.
        alt_text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
        alt_record = dict(record)
        alt_record["ocr_text"] = alt_text
        alt_fields = extract_document(alt_record)["fields"]
        for key in missing_critical:
            if not fields.get(key) and alt_fields.get(key):
                fields[key] = alt_fields[key]

        suffix = record.get("document_id", "").rsplit("-", 1)[-1]

        # SDS: packing-group value is in the same row, to the right of its label.
        # Only attempt this when the full-page passes did not find a value.
        if suffix == "SDS" and not fields.get("packing_group"):
            box = find_label_box(image, "PACKING GROUP")
            if box:
                left, top, right, bottom = box
                roi = (right + 45, top - 20, right + 330, top + 50)
                raw = crop_ocr(image, roi, "IL1|", psm=7)
                val = normalize_packing_group(raw)
                if val:
                    fields["packing_group"] = val

        # Dangerous-goods declaration: critical values sit below their labels.
        # The crop uses the detected label position rather than fixed page coordinates.
        if suffix == "DG" and not fields.get("hazard_class"):
            box = find_label_box(image, "HAZARD CLASS")
            if box:
                left, top, right, bottom = box
                roi = (left - 15, top + 15, right + 45, top + 80)
                raw = crop_ocr(image, roi, "0123456789", psm=10)
                match = re.search(r"(?<!\d)([1-9])(?!\d)", raw)
                if match:
                    fields["hazard_class"] = match.group(1)

        if suffix == "DG" and not fields.get("packing_group"):
            box = find_label_box(image, "PACKING GROUP")
            if box:
                left, top, right, bottom = box
                roi = (left - 15, top + 15, right + 25, top + 80)
                raw = crop_ocr(image, roi, "IL1|", psm=10)
                val = normalize_packing_group(raw)
                if val:
                    fields["packing_group"] = val

    return {"document_id": record.get("document_id", ""), "fields": fields}


def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    records = json.loads(input_path.read_text(encoding="utf-8"))
    predictions = []
    for record in records:
        base = extract_document(record)
        predictions.append(retry_missing_fields(record, base))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Processed {len(predictions)} OCR records with missing-field fallbacks.")
    print(f"Structured predictions saved to: {output_path}")
    print("Note: crop fallback is tailored to the synthetic starter templates; validate and generalize before real use.")


if __name__ == "__main__":
    main()
