#!/usr/bin/env python3
"""Run a first local PortGuard integration demo.

This script connects:
  1. Existing Ultralytics YOLO container-damage model
  2. Tesseract OCR over a folder of document-page images
  3. Existing PortGuard document field extractor v2
  4. Existing cross-document consistency checker v2

The supplied starter-document images are synthetic. This is a research/demo
workflow only; it does not make or authorize operational safety decisions.

Run from the project root, for example:
  python run_portguard_inspection.py
  python run_portguard_inspection.py --container-image test_images/imagesnew.jpeg
  python run_portguard_inspection.py --document-dir portguard_ocr_starter/images/clean
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image
import pytesseract
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = PROJECT_ROOT / "runs/detect/container_damage_detector/weights/best.pt"
DEFAULT_CONTAINER_IMAGE = PROJECT_ROOT / "test_images/imagesnew.jpeg"
DEFAULT_DOCUMENT_DIR = PROJECT_ROOT / "portguard_ocr_starter/images/scan_like"
OCR_ROOT = PROJECT_ROOT / "portguard_ocr_starter"
SCRIPTS_DIR = OCR_ROOT / "scripts"
OUTPUT_DIR = OCR_ROOT / "outputs"
EXTRACTOR_V2 = SCRIPTS_DIR / "extract_fields_from_ocr_v2.py"
CONSISTENCY_V2 = SCRIPTS_DIR / "check_document_consistency_v2.py"


def relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def run_damage_detection(model_path: Path, image_path: Path, conf: float, output_dir: Path) -> dict:
    if not model_path.is_file():
        raise FileNotFoundError(f"YOLO model weights not found: {model_path}")
    if not image_path.is_file():
        raise FileNotFoundError(f"Container image not found: {image_path}")

    model = YOLO(str(model_path))
    results = model.predict(
        source=str(image_path),
        conf=conf,
        save=True,
        project=str(output_dir),
        name="damage_visualized",
        exist_ok=True,
        verbose=False,
    )

    all_detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        xyxy_list = boxes.xyxy.cpu().tolist() if boxes.xyxy is not None else []
        confidences = boxes.conf.cpu().tolist() if boxes.conf is not None else []
        classes = boxes.cls.cpu().tolist() if boxes.cls is not None else []

        for idx, (class_id, confidence) in enumerate(zip(classes, confidences)):
            class_id = int(class_id)
            name_map = model.names
            class_name = name_map.get(class_id, str(class_id)) if isinstance(name_map, dict) else name_map[class_id]
            bbox = xyxy_list[idx] if idx < len(xyxy_list) else None
            all_detections.append({
                "class_id": class_id,
                "class_name": str(class_name),
                "confidence": round(float(confidence), 6),
                "bbox_xyxy_pixels": [round(float(v), 2) for v in bbox] if bbox else None,
            })

    return {
        "model_weights": relative_to_project(model_path),
        "image": relative_to_project(image_path),
        "confidence_threshold": conf,
        "detections_count": len(all_detections),
        "detections": all_detections,
        "visualization_dir": relative_to_project(output_dir / "damage_visualized"),
    }


def run_document_ocr(document_dir: Path) -> list[dict]:
    if not document_dir.is_dir():
        raise NotADirectoryError(f"Document image directory not found: {document_dir}")

    supported_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    image_paths = sorted(p for p in document_dir.iterdir() if p.is_file() and p.suffix.lower() in supported_exts)
    if not image_paths:
        raise FileNotFoundError(f"No document images found in: {document_dir}")

    records = []
    for image_path in image_paths:
        with Image.open(image_path) as image:
            ocr_text = pytesseract.image_to_string(image.convert("RGB"), lang="eng").strip()
        try:
            relative_image = image_path.resolve().relative_to(OCR_ROOT.resolve()).as_posix()
        except ValueError:
            # The v2 crop fallback expects dataset paths relative to portguard_ocr_starter.
            # When input images are outside that root, keep an absolute path in the record;
            # those images can still be OCRed, but crop-based fallback won't find them.
            relative_image = str(image_path.resolve())
        records.append({
            "document_id": image_path.stem,
            "image_path": relative_image,
            "ocr_text": ocr_text,
        })
        print(f"OCR: {image_path.name} ({len(ocr_text)} characters)")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PortGuard damage + OCR + consistency demo.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path to trained YOLO .pt weights")
    parser.add_argument("--container-image", type=Path, default=DEFAULT_CONTAINER_IMAGE, help="Container photograph for damage detection")
    parser.add_argument("--document-dir", type=Path, default=DEFAULT_DOCUMENT_DIR, help="Folder of document page images for OCR")
    parser.add_argument("--confidence", type=float, default=0.25, help="YOLO detection confidence threshold")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "integrated_inspection_report.json", help="Final combined report path")
    args = parser.parse_args()

    # Resolve relative paths against the project root, independent of launch cwd.
    model_path = args.model if args.model.is_absolute() else (PROJECT_ROOT / args.model).resolve()
    container_image = args.container_image if args.container_image.is_absolute() else (PROJECT_ROOT / args.container_image).resolve()
    document_dir = args.document_dir if args.document_dir.is_absolute() else (PROJECT_ROOT / args.document_dir).resolve()
    final_output = args.output if args.output.is_absolute() else (PROJECT_ROOT / args.output).resolve()

    required_files = [EXTRACTOR_V2, CONSISTENCY_V2]
    missing = [p for p in required_files if not p.is_file()]
    if missing:
        missing_list = "\n".join(f"  - {relative_to_project(p)}" for p in missing)
        raise FileNotFoundError(
            "Required PortGuard script(s) not found. Keep the existing OCR extractor and checker in the scripts folder:\n"
            + missing_list
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    damage_output_dir = PROJECT_ROOT / "runs/detect/portguard_integrated"

    print("\n[1/4] Running container damage detection...")
    damage_results = run_damage_detection(model_path, container_image, args.confidence, damage_output_dir)
    print(f"Damage detections: {damage_results['detections_count']}")

    print("\n[2/4] Running OCR on document images...")
    ocr_records = run_document_ocr(document_dir)
    raw_ocr_path = OUTPUT_DIR / "ocr_raw_integrated.json"
    raw_ocr_path.write_text(json.dumps(ocr_records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Raw OCR saved: {relative_to_project(raw_ocr_path)}")

    print("\n[3/4] Extracting structured document fields...")
    prediction_path = OUTPUT_DIR / "predictions_integrated.json"
    extractor_cmd = [sys.executable, str(EXTRACTOR_V2), str(raw_ocr_path), str(prediction_path)]
    subprocess.run(extractor_cmd, cwd=PROJECT_ROOT, check=True)

    print("\n[4/4] Checking consistency across documents...")
    consistency_path = OUTPUT_DIR / "consistency_report_integrated.json"
    checker_cmd = [sys.executable, str(CONSISTENCY_V2), str(prediction_path), str(consistency_path)]
    subprocess.run(checker_cmd, cwd=PROJECT_ROOT, check=True)
    consistency = json.loads(consistency_path.read_text(encoding="utf-8"))
    predictions = json.loads(prediction_path.read_text(encoding="utf-8"))

    combined_report = {
        "project": "PortGuard",
        "purpose": "Prototype integration test only",
        "integration_note": (
            "The container photograph and the 12 synthetic document pages are separate demo inputs. "
            "They are processed in one run for integration testing, but are NOT asserted to belong to the same real inspection case. "
            "Case-level document comparisons apply only within the synthetic document IDs."
        ),
        "safety_notice": (
            "Synthetic starter documents and computer-vision outputs are for academic testing only. "
            "The report does not determine cargo contents or make an operational safety decision. "
            "A qualified human reviewer must inspect source material and resolve any findings."
        ),
        "container_damage_detection": damage_results,
        "document_processing": {
            "document_image_directory": relative_to_project(document_dir),
            "documents_processed": len(predictions),
            "raw_ocr_output": relative_to_project(raw_ocr_path),
            "structured_predictions_output": relative_to_project(prediction_path),
            "predictions": predictions,
        },
        "consistency_check": {
            "report_path": relative_to_project(consistency_path),
            "summary": consistency.get("summary", {}),
            "findings": consistency.get("findings", []),
            "automatic_correction": False,
        },
    }
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_text(json.dumps(combined_report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== PortGuard integrated run complete ===")
    print(f"Damage detections: {damage_results['detections_count']}")
    print(f"Documents processed: {len(predictions)}")
    for key, value in consistency.get("summary", {}).items():
        print(f"Consistency {key.replace('_', ' ')}: {value}")
    print(f"Combined report: {relative_to_project(final_output)}")
    print(f"Damage visualizations: {relative_to_project(damage_output_dir / 'damage_visualized')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, NotADirectoryError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
