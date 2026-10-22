#!/usr/bin/env python3
"""Run Tesseract OCR on PortGuard's synthetic scan-like test images."""
from pathlib import Path
from PIL import Image
import pytesseract
import json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT / "portguard_ocr_starter"

IMAGE_DIR = ROOT / "images" / "scan_like"
OUTPUT_DIR = ROOT / "outputs"

results = []
for image_path in sorted(IMAGE_DIR.glob("*.png")):
    with Image.open(image_path) as image:
        text = pytesseract.image_to_string(image, lang="eng").strip()
    results.append({
        "document_id": image_path.stem,
        "image_path": str(image_path.relative_to(ROOT)),
        "ocr_text": text,
    })
    print(f"\n--- {image_path.name} ---")
    print(text[:400] if text else "No text detected")

output_file = OUTPUT_DIR / "ocr_raw_scan_like.json"
output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nProcessed {len(results)} scan-like images.")
print(f"Results saved to: {output_file}")
