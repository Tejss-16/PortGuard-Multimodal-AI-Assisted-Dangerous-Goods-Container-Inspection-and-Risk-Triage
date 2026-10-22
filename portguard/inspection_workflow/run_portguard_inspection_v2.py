#!/usr/bin/env python3
"""PortGuard integration runner v2: damage detection + image/PDF extraction + consistency.

Usage from project root:
  python run_portguard_inspection_v2.py
  python run_portguard_inspection_v2.py --container-image test_images/imagesnew.jpeg --document-dir <folder>

PDFs use the teammate's PDF text-layer/OCR-fallback extractor. Raster document images
use the existing image OCR + template fallback field extractor. Image quality is
assessed automatically; there is no manual clean/scan-like selection.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image
import pytesseract

PROJECT_ROOT = Path(__file__).resolve().parents[2]

OCR_ROOT = PROJECT_ROOT / "portguard_ocr_starter"

SCRIPTS_DIR = (
    PROJECT_ROOT / "portguard" / "document_processing"
)

OUTPUT_DIR = OCR_ROOT / "outputs"

DEFAULT_MODEL = (
    PROJECT_ROOT / "models" / "container_damage_detector"
    / "weights" / "best.pt"
)

DEFAULT_CONTAINER_IMAGE = (
    PROJECT_ROOT / "data" / "test_images" / "imagesnew.jpeg"
)

DEFAULT_DOCUMENT_DIR = OCR_ROOT / "images" / "scan_like"

EXTRACTOR_V2 = SCRIPTS_DIR / "extract_fields_from_ocr_v2.py"

CONSISTENCY_V2 = (
    PROJECT_ROOT / "portguard" / "consistency_checker"
    / "check_document_consistency_v2.py"
)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}
SUPPORTED_DOC_EXTS = IMAGE_EXTS | PDF_EXTS

# Import the teammate's portable PDF extraction functions from the scripts folder.
# Make both the project package and document-processing module importable.
sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from portguard.document_processing.extract_document import (
        assess_image_quality,
        extract_document as extract_pdf_document,
        ocr_image,
    )
except Exception as exc:
    raise RuntimeError(
        f"Failed to import PDF/OCR helpers: {exc}"
    ) from exc
else:
    _PDF_IMPORT_ERROR = None


def relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def run_damage_detection(model_path: Path, image_path: Path, conf: float, output_dir: Path) -> dict[str, Any]:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Ultralytics is required for container damage detection. Install it with: python -m pip install ultralytics") from exc
    if not model_path.is_file():
        raise FileNotFoundError(f"YOLO model weights not found: {model_path}")
    if not image_path.is_file():
        raise FileNotFoundError(f"Container image not found: {image_path}")
    model = YOLO(str(model_path))
    results = model.predict(
        source=str(image_path), conf=conf, save=True,
        project=str(output_dir), name="damage_visualized", exist_ok=True, verbose=False,
    )
    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        coords = boxes.xyxy.cpu().tolist() if boxes.xyxy is not None else []
        confs = boxes.conf.cpu().tolist() if boxes.conf is not None else []
        classes = boxes.cls.cpu().tolist() if boxes.cls is not None else []
        for i, (class_id, score) in enumerate(zip(classes, confs)):
            cid = int(class_id)
            names = model.names
            label = names.get(cid, str(cid)) if isinstance(names, dict) else names[cid]
            detections.append({
                "class_id": cid,
                "class_name": str(label),
                "confidence": round(float(score), 6),
                "bbox_xyxy_pixels": [round(float(v), 2) for v in coords[i]] if i < len(coords) else None,
            })
    return {
        "model_weights": relative_to_project(model_path),
        "image": relative_to_project(image_path),
        "confidence_threshold": conf,
        "detections_count": len(detections),
        "detections": detections,
        "visualization_dir": relative_to_project(output_dir / "damage_visualized"),
    }


def run_document_processing(document_dir: Path) -> dict[str, Any]:
    if not document_dir.is_dir():
        raise NotADirectoryError(f"Document input directory not found: {document_dir}")
    inputs = sorted(p for p in document_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_DOC_EXTS)
    if not inputs:
        raise FileNotFoundError(f"No supported PDF or raster document files found in: {document_dir}")

    if any(p.suffix.lower() == ".pdf" for p in inputs) and extract_pdf_document is None:
        raise RuntimeError(
            "Could not load the PDF extractor. Copy extract_document.py and field_aliases.py into "
            f"{relative_to_project(SCRIPTS_DIR)}. Import error: {_PDF_IMPORT_ERROR}"
        )

    image_records: list[dict[str, Any]] = []
    pdf_predictions: list[dict[str, Any]] = []
    quality_assessments: list[dict[str, Any]] = []
    pdf_details: list[dict[str, Any]] = []

    for source in inputs:
        doc_id = source.stem
        suffix_type = doc_id.rsplit("-", 1)[-1].upper()
        if source.suffix.lower() == ".pdf":
            extracted = extract_pdf_document(source)
            fields = dict(extracted.get("fields", {}) or {})
            # Normalise teammate parser output to the keys used by image extraction/checking.
            if "imdg_class" in fields and not fields.get("hazard_class"):
                fields["hazard_class"] = fields.pop("imdg_class")
            pdf_predictions.append({
                "document_id": doc_id,
                "document_type": suffix_type,
                "source_file": source.name,
                "source_format": "PDF",
                "extraction_method": extracted.get("extraction_method"),
                "page_details": extracted.get("page_details", []),
                "review_required": extracted.get("review_required", True),
                "review_issues": extracted.get("review_issues", []),
                "fields": fields,
            })
            pdf_details.append({
                "document_id": doc_id,
                "source_file": source.name,
                "extraction_method": extracted.get("extraction_method"),
                "page_details": extracted.get("page_details", []),
                "extracted_text": extracted.get("extracted_text", ""),
            })
            for page in extracted.get("page_details", []):
                quality_assessments.append({
                    "source_file": source.name,
                    "page_number": page.get("page_number"),
                    "quality_assessment": page.get("quality_assessment", "digital-text-layer"),
                    "processing_method": page.get("method"),
                    "preprocessing": page.get("preprocessing", "not needed"),
                    "metrics_note": page.get("assessment_note", ""),
                })
            print(f"PDF: {source.name} ({extracted.get('extraction_method')})")
            continue

        with Image.open(source) as opened:
            image = opened.convert("RGB")
            text, metadata = ocr_image(image)
            metadata["source_file"] = source.name
            quality_assessments.append({
                "source_file": source.name,
                "quality_assessment": metadata.get("quality_assessment", "unknown"),
                "contrast_stddev": metadata.get("contrast_stddev"),
                "edge_stddev": metadata.get("edge_stddev"),
                "preprocessing": metadata.get("preprocessing", "not recorded"),
                "assessment_note": metadata.get("assessment_note", ""),
            })
        # Absolute path allows the existing synthetic-template crop fallback to open the source image.
        image_records.append({
            "document_id": doc_id,
            "image_path": str(source.resolve()),
            "ocr_text": text,
            "quality_assessment": metadata,
        })
        print(f"Image: {source.name} ({metadata.get('quality_assessment')}; {len(text)} characters)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_ocr_path = OUTPUT_DIR / "ocr_raw_integrated.json"
    raw_ocr_path.write_text(json.dumps(image_records, indent=2, ensure_ascii=False), encoding="utf-8")
    pdf_details_path = OUTPUT_DIR / "pdf_extraction_details.json"
    pdf_details_path.write_text(json.dumps(pdf_details, indent=2, ensure_ascii=False), encoding="utf-8")

    image_predictions: list[dict[str, Any]] = []
    if image_records:
        if not EXTRACTOR_V2.is_file():
            raise FileNotFoundError(f"Image field extractor not found: {EXTRACTOR_V2}")
        image_prediction_path = OUTPUT_DIR / "predictions_image_integrated.json"
        subprocess.run(
            [sys.executable, str(EXTRACTOR_V2), str(raw_ocr_path), str(image_prediction_path)],
            cwd=PROJECT_ROOT, check=True,
        )
        loaded = json.loads(image_prediction_path.read_text(encoding="utf-8"))
        metadata_by_id = {r["document_id"]: r.get("quality_assessment", {}) for r in image_records}
        for row in loaded:
            row["source_format"] = "image"
            row["source_file"] = Path(next((r["image_path"] for r in image_records if r["document_id"] == row.get("document_id")), "unknown")).name
            row["quality_assessment"] = metadata_by_id.get(row.get("document_id"), {})
            image_predictions.append(row)

    predictions = sorted(image_predictions + pdf_predictions, key=lambda row: row.get("document_id", ""))
    prediction_path = OUTPUT_DIR / "predictions_integrated.json"
    prediction_path.write_text(json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8")

    if not predictions:
        raise ValueError("No fields were extracted from the supplied documents.")

    consistency_path = OUTPUT_DIR / "consistency_report_integrated.json"
    if not CONSISTENCY_V2.is_file():
        raise FileNotFoundError(f"Consistency checker not found: {CONSISTENCY_V2}")
    subprocess.run(
        [sys.executable, str(CONSISTENCY_V2), str(prediction_path), str(consistency_path)],
        cwd=PROJECT_ROOT, check=True,
    )
    consistency = json.loads(consistency_path.read_text(encoding="utf-8"))

    return {
        "document_image_directory": relative_to_project(document_dir),
        "documents_processed": len(predictions),
        "raw_ocr_output": relative_to_project(raw_ocr_path),
        "pdf_extraction_details": relative_to_project(pdf_details_path),
        "structured_predictions_output": relative_to_project(prediction_path),
        "predictions": predictions,
        "quality_assessments": quality_assessments,
        "consistency_report_path": relative_to_project(consistency_path),
        "consistency_summary": consistency.get("summary", {}),
        "consistency_findings": consistency.get("findings", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PortGuard damage detection with PDF/image OCR and consistency checks.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--container-image", type=Path, default=DEFAULT_CONTAINER_IMAGE)
    parser.add_argument("--document-dir", type=Path, default=DEFAULT_DOCUMENT_DIR)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--reuse-damage-result", type=Path, default=None, help="Reuse container_damage_detection from an earlier report, instead of rerunning the vision model")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "integrated_inspection_report.json")
    args = parser.parse_args()

    model_path = args.model if args.model.is_absolute() else (PROJECT_ROOT / args.model).resolve()
    container_image = args.container_image if args.container_image.is_absolute() else (PROJECT_ROOT / args.container_image).resolve()
    document_dir = args.document_dir if args.document_dir.is_absolute() else (PROJECT_ROOT / args.document_dir).resolve()
    final_output = args.output if args.output.is_absolute() else (PROJECT_ROOT / args.output).resolve()

    for needed in [EXTRACTOR_V2, CONSISTENCY_V2]:
        if not needed.is_file():
            raise FileNotFoundError(f"Required pipeline script is missing: {relative_to_project(needed)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    damage_output_dir = PROJECT_ROOT / "runs" / "detect" / "portguard_integrated_v2"
    if args.reuse_damage_result is not None:
        reuse_path = args.reuse_damage_result if args.reuse_damage_result.is_absolute() else (PROJECT_ROOT / args.reuse_damage_result).resolve()
        if not reuse_path.is_file():
            raise FileNotFoundError(f"Reuse-damage report not found: {reuse_path}")
        reused_report = json.loads(reuse_path.read_text(encoding="utf-8"))
        damage = reused_report.get("container_damage_detection")
        if not isinstance(damage, dict):
            raise ValueError(f"No container_damage_detection section in reuse report: {reuse_path}")
        print("\n[1/3] Reusing previously computed container damage detections...")
    else:
        print("\n[1/3] Running container damage detection...")
        damage = run_damage_detection(model_path, container_image, args.confidence, damage_output_dir)
        print(f"Damage detections: {damage['detections_count']}")

    print("\n[2/3] Processing document PDFs/images (quality/method selected automatically)...")
    documents = run_document_processing(document_dir)

    print("\n[3/3] Building combined report...")
    report = {
        "project": "PortGuard",
        "purpose": "Academic prototype integration test",
        "integration_note": (
            "Container photo and documents are grouped by the operator for this prototype; the system does not independently "
            "verify that they belong to the same shipment. Synthetic starter documents are for testing only."
        ),
        "safety_notice": "This report is not a cargo-content determination or an operational safety/release decision. Review original documents and images.",
        "container_damage_detection": damage,
        "document_processing": documents,
        "consistency_check": {
            "report_path": documents["consistency_report_path"],
            "summary": documents["consistency_summary"],
            "findings": documents["consistency_findings"],
            "automatic_correction": False,
        },
        "pdf_extractor_integration": {
            "module": relative_to_project(SCRIPTS_DIR / "extract_document.py"),
            "method": "embedded PDF text where useful; otherwise OCR fallback per page",
            "field_aliases": relative_to_project(SCRIPTS_DIR / "field_aliases.py"),
        },
    }
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== PortGuard integrated run complete ===")
    print(f"Damage detections: {damage['detections_count']}")
    print(f"Documents processed: {documents['documents_processed']}")
    for k, v in documents["consistency_summary"].items():
        print(f"Consistency {k.replace('_', ' ')}: {v}")
    print(f"Combined report: {relative_to_project(final_output)}")
    print(f"Damage visualizations: {relative_to_project(damage_output_dir / 'damage_visualized')}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, NotADirectoryError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
