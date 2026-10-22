from pathlib import Path
from PIL import Image
import pytesseract
import json

# Dataset directory
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT / "portguard_ocr_starter"

IMAGE_DIR = ROOT / "images" / "clean"
OUTPUT_DIR = ROOT / "outputs"

results = []

# Process every clean document image
for image_path in sorted(IMAGE_DIR.glob("*.png")):
    with Image.open(image_path) as image:
        text = pytesseract.image_to_string(
            image,
            lang="eng"
        ).strip()

    results.append({
        "document_id": image_path.stem,
        "image_path": str(image_path.relative_to(ROOT)),
        "ocr_text": text
    })

    print(f"\n--- {image_path.name} ---")
    print(text[:500] if text else "No text detected")

# Save the complete OCR output
output_file = OUTPUT_DIR / "ocr_raw_clean.json"
output_file.write_text(
    json.dumps(results, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print(f"\nProcessed {len(results)} images.")
print(f"Results saved to: {output_file}")