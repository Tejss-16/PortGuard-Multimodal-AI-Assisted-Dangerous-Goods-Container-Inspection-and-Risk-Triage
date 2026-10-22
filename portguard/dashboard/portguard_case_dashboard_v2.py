#!/usr/bin/env python3
"""PortGuard inspection-case dashboard (local academic prototype).

Place in the project root alongside run_portguard_inspection.py. Run:
    streamlit run portguard_case_dashboard.py

A case groups a selected container photo, document images, pipeline report, and
human-review record. The association is supplied by the operator; it is not
independently verified. Synthetic starter documents are clearly identified.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]

RUNNER = (
    ROOT / "portguard" / "inspection_workflow"
    / "run_portguard_inspection_v2.py"
)

OCR_ROOT = ROOT / "portguard_ocr_starter"
OUTPUT_ROOT = OCR_ROOT / "outputs"
CASE_ROOT = OUTPUT_ROOT / "inspection_cases"
REGISTRY_PATH = CASE_ROOT / "registry.json"

MODEL_PATH = (
    ROOT / "models" / "container_damage_detector"
    / "weights" / "best.pt"
)

TEST_IMAGE_ROOT = ROOT / "data" / "test_images"
STARTER_IMAGE_ROOT = OCR_ROOT / "images"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
DOC_EXTS = IMAGE_EXTS | {".pdf"}
DOC_TYPES = [
    ("DG", "Dangerous-goods declaration"),
    ("PACK", "Packing list"),
    ("SDS", "SDS Section 14"),
    ("SHIP", "Shipping details summary"),
]


def relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_registry() -> list[dict[str, Any]]:
    data = read_json(REGISTRY_PATH, [])
    return data if isinstance(data, list) else []


def images_under(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def find_visualization(report: dict[str, Any]) -> Path | None:
    damage = report.get("container_damage_detection", {}) or {}
    directory_value = damage.get("visualization_dir", "")
    if not directory_value:
        return None
    directory = Path(directory_value)
    if not directory.is_absolute():
        directory = ROOT / directory
    if not directory.is_dir():
        return None
    image_value = damage.get("image", "")
    stem = Path(image_value).stem if image_value else ""
    if stem:
        for p in directory.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.stem == stem:
                return p
    candidates = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    return candidates[0] if len(candidates) == 1 else None


def get_case_by_id(case_id: str) -> dict[str, Any] | None:
    folder = CASE_ROOT / case_id
    record_path = folder / "case_record.json"
    record = read_json(record_path, None)
    return record if isinstance(record, dict) else None


def save_case_registry(record: dict[str, Any]) -> None:
    registry = get_registry()
    registry = [x for x in registry if x.get("case_id") != record.get("case_id")]
    registry.insert(0, {
        "case_id": record["case_id"],
        "created_at": record["created_at"],
        "review_decision": (record.get("review") or {}).get("decision", "Pending"),
        "case_record_path": relpath(CASE_ROOT / record["case_id"] / "case_record.json"),
        "report_path": relpath(CASE_ROOT / record["case_id"] / "integrated_inspection_report.json"),
    })
    write_json(REGISTRY_PATH, registry)


def copy_or_save_photo(case_dir: Path, selected_image: str, uploaded_image) -> Path:
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    if uploaded_image is not None:
        suffix = Path(uploaded_image.name).suffix.lower() or ".jpg"
        if suffix not in IMAGE_EXTS:
            raise ValueError("Unsupported photo format. Upload PNG, JPG, JPEG, WEBP, BMP, TIF or TIFF.")
        target = input_dir / f"container_photo{suffix}"
        target.write_bytes(uploaded_image.getbuffer())
        return target
    if not selected_image:
        raise ValueError("Choose or upload a container photograph.")
    src = Path(selected_image)
    if not src.is_absolute():
        src = ROOT / src
    if not src.is_file():
        raise FileNotFoundError(f"Selected container image not found: {src}")
    target = input_dir / f"container_photo{src.suffix.lower()}"
    shutil.copy2(src, target)
    return target


def prepare_documents(
    case_id: str,
    case_dir: Path,
    source_mode: str,
    source_case: str,
    quality: str,
    uploads: dict[str, Any],
) -> tuple[Path, list[str], str]:
    doc_dir = case_dir / "documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    document_ids: list[str] = []

    if source_mode == "Use synthetic starter case":
        source_dir = STARTER_IMAGE_ROOT / quality
        copied = 0
        for code, _label in DOC_TYPES:
            candidates = [
                source_dir / f"{source_case}-{code}.png",
                source_dir / f"{source_case}-{code}.jpg",
                source_dir / f"{source_case}-{code}.jpeg",
            ]
            source = next((p for p in candidates if p.is_file()), None)
            if source is None:
                raise FileNotFoundError(
                    f"Could not find {source_case}-{code} in {relpath(source_dir)}. "
                    "Check that the starter dataset is extracted."
                )
            target = doc_dir / f"{case_id}-{code}{source.suffix.lower()}"
            shutil.copy2(source, target)
            document_ids.append(target.stem)
            copied += 1
        source_note = (
            f"Synthetic starter test case {source_case}, {quality} image set. "
            "The selected container photograph was manually associated for demo purposes; "
            "the dataset does not establish that they belong to the same physical shipment."
        )
        return doc_dir, document_ids, source_note

    uploaded_count = 0
    for code, _label in DOC_TYPES:
        upload = uploads.get(code)
        if upload is None:
            continue
        suffix = Path(upload.name).suffix.lower() or ".png"
        if suffix not in DOC_EXTS:
            raise ValueError(f"{code}: supported document types are PDF, PNG, JPG/JPEG, TIF/TIFF, BMP, or WEBP.")
        target = doc_dir / f"{case_id}-{code}{suffix}"
        target.write_bytes(upload.getbuffer())
        document_ids.append(target.stem)
        uploaded_count += 1
    if uploaded_count < 2:
        raise ValueError("Upload at least two document files so the consistency checker has fields to compare.")
    source_note = (
        "Operator-uploaded document images. Document types were assigned by the operator. "
        "Verify extracted values against the original pages; current crop fallbacks were developed on synthetic templates."
    )
    return doc_dir, document_ids, source_note


def run_pipeline_for_case(case_id: str, case_dir: Path, photo_path: Path, doc_dir: Path, confidence: float, source_note: str, reuse_damage_report: Path | None = None) -> dict[str, Any]:
    if not RUNNER.is_file():
        raise FileNotFoundError("run_portguard_inspection_v2.py is missing from the project root.")
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(f"Damage model not found: {relpath(MODEL_PATH)}")

    report_path = case_dir / "integrated_inspection_report.json"
    cmd = [
        sys.executable, str(RUNNER),
        "--model", str(MODEL_PATH),
        "--container-image", str(photo_path),
        "--document-dir", str(doc_dir),
        "--confidence", str(confidence),
        "--output", str(report_path),
    ]
    if reuse_damage_report is not None:
        cmd.extend(["--reuse-damage-result", str(reuse_damage_report)])
    completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False, timeout=900)
    (case_dir / "run_stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (case_dir / "run_stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "No output captured.")[-6000:]
        raise RuntimeError(f"Pipeline exited with code {completed.returncode}.\n{details}")

    # Preserve the global runner artifacts under this case to keep previous runs reproducible.
    artifact_map = {
        OUTPUT_ROOT / "ocr_raw_integrated.json": case_dir / "ocr_raw.json",
        OUTPUT_ROOT / "predictions_integrated.json": case_dir / "predictions.json",
        OUTPUT_ROOT / "consistency_report_integrated.json": case_dir / "consistency_report.json",
        OUTPUT_ROOT / "pdf_extraction_details.json": case_dir / "pdf_extraction_details.json",
    }
    for source, target in artifact_map.items():
        if source.is_file():
            shutil.copy2(source, target)

    shared_vis = ROOT / "runs" / "detect" / "portguard_integrated_v2" / "damage_visualized"
    case_vis = case_dir / "damage_visualized"
    if shared_vis.is_dir():
        if case_vis.exists():
            shutil.rmtree(case_vis)
        shutil.copytree(shared_vis, case_vis)

    report = read_json(report_path, None)
    if not isinstance(report, dict):
        raise RuntimeError("Runner completed but integrated_inspection_report.json could not be parsed.")
    report["purpose"] = "PortGuard inspection-case prototype test"
    report["integration_note"] = (
        f"Inspection case {case_id}. {source_note} The case grouping is supplied by the operator and has not "
        "been independently verified. This prototype does not establish cargo contents or make operational decisions."
    )
    report["case_metadata"] = {
        "case_id": case_id,
        "case_folder": relpath(case_dir),
        "container_photo": relpath(photo_path),
        "document_directory": relpath(doc_dir),
        "document_ids": sorted([p.stem for p in doc_dir.iterdir() if p.is_file() and p.suffix.lower() in DOC_EXTS]),
        "association_method": "operator-selected/manual; not independently verified",
    }
    if "document_processing" in report:
        report["document_processing"]["document_image_directory"] = relpath(doc_dir)
        report["document_processing"]["raw_ocr_output"] = relpath(case_dir / "ocr_raw.json")
        report["document_processing"]["structured_predictions_output"] = relpath(case_dir / "predictions.json")
        if (case_dir / "pdf_extraction_details.json").is_file():
            report["document_processing"]["pdf_extraction_details"] = relpath(case_dir / "pdf_extraction_details.json")
    if "consistency_check" in report:
        report["consistency_check"]["report_path"] = relpath(case_dir / "consistency_report.json")
    if "container_damage_detection" in report and case_vis.is_dir():
        report["container_damage_detection"]["visualization_dir"] = relpath(case_vis)
    write_json(report_path, report)
    return report



def run_all_synthetic_batches(
    case_id: str,
    case_dir: Path,
    photo_path: Path,
    confidence: float,
) -> tuple[dict[str, Any], Path, list[str], str]:
    """Run all three synthetic cases for both image variants; never asks the user to pick a case/quality."""
    quality_runs: dict[str, dict[str, Any]] = {}
    all_ids: list[str] = []
    photo_damage: dict[str, Any] | None = None

    for variant in ("clean", "scan_like"):
        source_dir = STARTER_IMAGE_ROOT / variant
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Synthetic image set not found: {relpath(source_dir)}")
        source_images = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
        if not source_images:
            raise FileNotFoundError(f"No synthetic images were found in {relpath(source_dir)}")
        variant_dir = case_dir / "document_quality_runs" / variant
        doc_dir = variant_dir / "documents"
        doc_dir.mkdir(parents=True, exist_ok=True)
        for image in source_images:
            shutil.copy2(image, doc_dir / image.name)
        ids = [p.stem for p in source_images]
        all_ids = sorted(set(all_ids) | set(ids))
        variant_note = (
            f"Synthetic benchmark quality variant '{variant}'. All three document test cases (001, 002, 003) are included. "
            "The container photo is processed as a separate visual-model input and is not claimed to belong to these synthetic shipments."
        )
        previous_report_path = case_dir / "document_quality_runs" / "clean" / "integrated_inspection_report.json" if variant == "scan_like" else None
        report = run_pipeline_for_case(
            case_id, variant_dir, photo_path, doc_dir, confidence, variant_note,
            reuse_damage_report=previous_report_path,
        )
        if photo_damage is None:
            photo_damage = report.get("container_damage_detection", {})
        quality_runs[variant] = {
            "variant": variant,
            "documents_processed": (report.get("document_processing", {}) or {}).get("documents_processed", len(ids)),
            "document_processing": report.get("document_processing", {}) or {},
            "consistency_check": report.get("consistency_check", {}) or {},
            "integrated_report_path": relpath(variant_dir / "integrated_inspection_report.json"),
            "quality_assessments": (report.get("document_processing", {}) or {}).get("quality_assessments", []),
        }

    source_note = (
        "All three synthetic document cases (001–003) were processed in one batch. Both clean and scan-like image variants "
        "are run automatically as separate comparison conditions; no image-quality selector is required. The container photo "
        "is a separate model demonstration input and has not been verified as belonging to any synthetic document case."
    )
    # Keep a primary document/consistency view for compatibility with saved-case rendering;
    # the Quality comparison tab exposes the second condition as well.
    primary = quality_runs["scan_like"]
    master = {
        "project": "PortGuard",
        "purpose": "Synthetic batch integration and OCR robustness comparison",
        "integration_note": source_note,
        "safety_notice": "Synthetic cases are for academic testing only. No cargo contents or operational safety decision are inferred.",
        "container_damage_detection": photo_damage or {},
        "document_processing": primary["document_processing"],
        "consistency_check": primary["consistency_check"],
        "document_quality_runs": quality_runs,
        "synthetic_test_cases": ["001", "002", "003"],
        "automatic_quality_handling": "Both pre-made image variants are processed without a manual selector. For uploaded images/PDFs, image quality and text-layer/OCR method are assessed automatically.",
    }
    write_json(case_dir / "integrated_inspection_report.json", master)
    return master, case_dir / "document_quality_runs" / "scan_like" / "documents", all_ids, source_note


def render_report(report: dict[str, Any], key_prefix: str = "view") -> None:
    damage = report.get("container_damage_detection", {}) or {}
    documents = report.get("document_processing", {}) or {}
    consistency = report.get("consistency_check", {}) or {}
    summary = consistency.get("summary", {}) or {}
    detections = damage.get("detections", []) or []
    predictions = documents.get("predictions", []) or []
    findings = consistency.get("findings", []) or []
    quality_runs = report.get("document_quality_runs", {}) or {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Damage detections", int(damage.get("detections_count", len(detections)) or 0))
    c2.metric("Documents in primary view", int(documents.get("documents_processed", len(predictions)) or 0))
    c3.metric("Value disagreements", int(summary.get("value_disagreement", 0) or 0))
    c4.metric("Fields needing review", sum(int(summary.get(k, 0) or 0) for k in ("possible_ocr_error", "value_disagreement", "missing_value")))

    tab_names = ["Damage", "Document fields", "Consistency"]
    if quality_runs:
        tab_names.append("Quality comparison")
    tab_names.append("Full report")
    tabs = st.tabs(tab_names)
    tab_index = {name: tab for name, tab in zip(tab_names, tabs)}

    with tab_index["Damage"]:
        st.write(f"**Container photo:** `{damage.get('image', 'not recorded')}`")
        st.write(f"**Detection confidence threshold:** {damage.get('confidence_threshold', '—')}")
        visual = find_visualization(report)
        if visual and visual.is_file():
            st.image(str(visual), caption="Detected regions from the current damage model", use_container_width=True)
        else:
            st.info("No annotated image found for this report. Inspect the damage_visualized folder in this case directory.")
        if detections:
            st.dataframe([
                {"Class": x.get("class_name", "unknown"), "Confidence": f"{float(x.get('confidence', 0)):.1%}", "Box (pixels)": x.get("bbox_xyxy_pixels", [])}
                for x in detections
            ], use_container_width=True, hide_index=True)
        else:
            st.info("No detections above the selected threshold.")

    with tab_index["Document fields"]:
        if predictions:
            doc_ids = [x.get("document_id", f"document-{i+1}") for i, x in enumerate(predictions)]
            selected = st.selectbox("Document", doc_ids, key=f"{key_prefix}_doc_select")
            row = next((x for x in predictions if x.get("document_id") == selected), predictions[0])
            st.caption(f"Source: {row.get('source_file', row.get('source_format', 'document'))} · Format: {row.get('source_format', 'image')}")
            if row.get("quality_assessment"):
                qa = row["quality_assessment"]
                st.caption(f"Automatically assessed image quality: {qa.get('quality_assessment', 'not available')} · {qa.get('preprocessing', 'preprocessing not recorded')}")
            if row.get("page_details"):
                st.dataframe(row["page_details"], use_container_width=True, hide_index=True)
            st.dataframe([
                {"Field": k.replace("_", " ").title(), "Extracted value": v if v not in (None, "") else "—"}
                for k, v in (row.get("fields", {}) or {}).items()
            ], use_container_width=True, hide_index=True)
            if row.get("review_required"):
                st.warning("This document has missing/unreadable fields: " + "; ".join(row.get("review_issues", [])))
            st.download_button(
                "Download selected fields (JSON)", data=json.dumps(row, indent=2, ensure_ascii=False),
                file_name=f"{selected}_fields.json", mime="application/json", key=f"{key_prefix}_download_doc",
            )
        else:
            st.info("No document predictions stored.")
        qa_rows = documents.get("quality_assessments", []) or []
        if qa_rows:
            with st.expander("Automatic image/PDF page quality assessments", expanded=False):
                st.dataframe(qa_rows, use_container_width=True, hide_index=True)

    with tab_index["Consistency"]:
        cols = st.columns(5)
        for col, label, key in zip(cols,
            ["Matches", "Possible OCR errors", "Value disagreements", "Missing values", "Insufficient sources"],
            ["match", "possible_ocr_error", "value_disagreement", "missing_value", "insufficient_sources"]):
            col.metric(label, int(summary.get(key, 0) or 0))
        if findings:
            rows = []
            for item in findings:
                obs = item.get("observations", []) or []
                values = "; ".join(f"{o.get('document_id', '?')}: {o.get('value', '—')}" for o in obs)
                missing = ", ".join(item.get("missing_documents", []) or [])
                rows.append({
                    "Case": item.get("case_id", "—"),
                    "Field": str(item.get("field", "—")).replace("_", " ").title(),
                    "Classification": str(item.get("classification", item.get("status", "unknown"))).replace("_", " ").title(),
                    "Observed values": values, "Missing in": missing or "—",
                    "Reason": item.get("reason", item.get("message", "Review source pages.")),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("No consistency findings recorded.")
        st.warning("These are review hints. The checker does not automatically correct values or establish which source is correct.")

    if quality_runs:
        with tab_index["Quality comparison"]:
            st.info("All three synthetic document cases (001–003) ran automatically in both variants. This is a comparison of image-quality conditions, not a setting you need to choose.")
            comparison_rows = []
            for variant in ("clean", "scan_like"):
                qrun = quality_runs.get(variant, {}) or {}
                qsummary = ((qrun.get("consistency_check") or {}).get("summary") or {})
                comparison_rows.append({
                    "Variant": "Clean images" if variant == "clean" else "Scan-like images (degraded)",
                    "Documents": qrun.get("documents_processed", 0),
                    "Matches": qsummary.get("match", 0),
                    "Possible OCR errors": qsummary.get("possible_ocr_error", 0),
                    "Value disagreements": qsummary.get("value_disagreement", 0),
                    "Missing values": qsummary.get("missing_value", 0),
                })
            st.dataframe(comparison_rows, use_container_width=True, hide_index=True)
            for variant, label in [("clean", "Clean images"), ("scan_like", "Scan-like images (degraded)")]:
                qrun = quality_runs.get(variant, {}) or {}
                with st.expander(label, expanded=(variant == "scan_like")):
                    qdocs = (qrun.get("document_processing") or {}).get("predictions", []) or []
                    qfindings = (qrun.get("consistency_check") or {}).get("findings", []) or []
                    if qdocs:
                        st.caption(f"{len(qdocs)} document files processed across cases 001, 002 and 003.")
                        st.dataframe([
                            {"Document": r.get("document_id"), **{k.replace("_", " ").title(): (v if v not in (None, "") else "—") for k, v in (r.get("fields", {}) or {}).items()}}
                            for r in qdocs
                        ], use_container_width=True, hide_index=True)
                    if qfindings:
                        st.write("Consistency findings")
                        st.dataframe([
                            {"Case": f.get("case_id"), "Field": f.get("field"), "Classification": f.get("classification"), "Reason": f.get("reason")}
                            for f in qfindings
                        ], use_container_width=True, hide_index=True)
                    qa = qrun.get("quality_assessments", []) or []
                    if qa:
                        st.write("Automatically assessed image quality")
                        st.dataframe(qa, use_container_width=True, hide_index=True)

    with tab_index["Full report"]:
        st.json(report)
        st.download_button(
            "Download integrated report", data=json.dumps(report, indent=2, ensure_ascii=False),
            file_name=f"{report.get('case_metadata', {}).get('case_id', 'inspection')}_report.json",
            mime="application/json", key=f"{key_prefix}_download_report",
        )


st.set_page_config(page_title="PortGuard | Inspection Cases", page_icon="📦", layout="wide")
st.title("PortGuard — Inspection Case Workflow")
st.caption("Container damage detection · Document OCR · Consistency review · Human review record")
st.warning(
    "Academic prototype only. A photo and documents become one case because the operator groups them together; "
    "the software does not independently verify that they belong to the same shipment. Synthetic documents are test-only. "
    "No automated release/hold or safety decision is made."
)

if "case_id_seed" not in st.session_state:
    st.session_state["case_id_seed"] = "PG" + datetime.now().strftime("%Y%m%d%H%M%S")

new_tab, saved_tab, how_tab = st.tabs(["Create / run a case", "Saved cases & officer review", "Demo checklist"])

with new_tab:
    st.subheader("Create an inspection case or synthetic test batch")
    left, right = st.columns(2)
    with left:
        case_id = st.text_input("Case ID (letters, numbers, underscore; no hyphens)", value=st.session_state["case_id_seed"], key="new_case_id")
        st.caption("Example: PGDEMO001. A no-hyphen ID keeps the current document case grouping logic consistent.")
        image_source = st.radio("Container photograph source", ["Choose existing test image", "Upload a container photograph"], key="image_source")
        available_images = images_under(TEST_IMAGE_ROOT)
        selected_image = ""
        uploaded_photo = None
        if image_source == "Choose existing test image":
            if available_images:
                defaults = [p for p in available_images if p.name == "imagesnew.jpeg"]
                chosen = st.selectbox("Container image", [relpath(p) for p in available_images], index=([relpath(p) for p in available_images].index(relpath(defaults[0])) if defaults else 0), key="existing_image")
                selected_image = chosen
            else:
                st.error("No images found under test_images/. Upload a photo or add one there.")
        else:
            uploaded_photo = st.file_uploader("Upload container photograph", type=["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"], key="uploaded_photo")
    with right:
        source_mode = st.radio(
            "Document source",
            ["Run all synthetic cases (001–003)", "Upload documents (PDF or images)"],
            key="doc_source_mode",
        )
        uploaded_docs: dict[str, Any] = {}
        synthetic_case = "ALL_001_003" if source_mode.startswith("Run all synthetic") else ""
        quality_label = "automatic"
        if source_mode.startswith("Run all synthetic"):
            st.caption(
                "One click processes all 12 document pages across cases 001, 002 and 003. "
                "Clean and scan-like versions are run separately and compared automatically; there is no quality selector."
            )
        else:
            st.caption(
                "Upload up to one PDF or image per document type. PDF pages with readable embedded text use that text; "
                "scanned/sparse-text pages use OCR automatically. Image quality is assessed automatically."
            )
            for code, label in DOC_TYPES:
                uploaded_docs[code] = st.file_uploader(
                    f"{label} (PDF or image; optional)",
                    type=["pdf", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
                    key=f"upload_{code}",
                )
        confidence = st.slider("Damage detection confidence threshold", 0.05, 0.90, 0.25, 0.05, key="new_case_confidence")

    st.info("The case ID links the selected photo and document pages in this prototype. It is an operator-provided association, not an identity match produced by AI.")
    run_button = st.button("Create case and run inspection", type="primary", use_container_width=True)
    if run_button:
        clean_case_id = case_id.strip()
        if not clean_case_id or not re.fullmatch(r"[A-Za-z0-9_]+", clean_case_id):
            st.error("Use a case ID containing only letters, numbers and underscores; do not include hyphens.")
        elif (CASE_ROOT / clean_case_id / "case_record.json").is_file():
            st.error("That case ID already exists. Choose a new ID to avoid overwriting a previous case.")
        elif image_source == "Choose existing test image" and not selected_image:
            st.error("Select an existing container image or upload one.")
        elif image_source == "Upload a container photograph" and uploaded_photo is None:
            st.error("Upload the container photograph first.")
        else:
            case_dir = CASE_ROOT / clean_case_id
            # A failed earlier run may leave a partial folder without a case record.
            # Clear that partial folder before retrying the same unused case ID.
            if case_dir.exists():
                shutil.rmtree(case_dir)
            case_dir.mkdir(parents=True, exist_ok=True)
            try:
                photo_path = copy_or_save_photo(case_dir, selected_image, uploaded_photo)
                if source_mode.startswith("Run all synthetic"):
                    with st.spinner("Running all three synthetic document cases against clean and scan-like images automatically..."):
                        report, doc_dir, document_ids, source_note = run_all_synthetic_batches(
                            clean_case_id, case_dir, photo_path, confidence
                        )
                    primary_artifact_dir = case_dir / "document_quality_runs" / "scan_like"
                else:
                    doc_dir, document_ids, source_note = prepare_documents(
                        clean_case_id, case_dir, source_mode, synthetic_case, quality_label, uploaded_docs
                    )
                    if not document_ids:
                        raise ValueError("No document files were selected or uploaded.")
                    with st.spinner("Running damage detection, automatic PDF/image extraction and consistency checks..."):
                        report = run_pipeline_for_case(clean_case_id, case_dir, photo_path, doc_dir, confidence, source_note)
                    primary_artifact_dir = case_dir
                review = {
                    "decision": "Pending",
                    "reviewer": "",
                    "notes": "",
                    "history": [],
                }
                record = {
                    "case_id": clean_case_id,
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "status": "Awaiting officer review",
                    "container_photo": relpath(photo_path),
                    "document_directory": relpath(doc_dir),
                    "document_ids": document_ids,
                    "document_source_note": source_note,
                    "synthetic_reference_case": synthetic_case or None,
                    "document_quality_variants": ["clean", "scan_like"] if source_mode.startswith("Run all synthetic") else ["automatically assessed"],
                    "review": review,
                    "artifacts": {
                        "report": relpath(case_dir / "integrated_inspection_report.json"),
                        "ocr_raw": relpath(primary_artifact_dir / "ocr_raw.json"),
                        "predictions": relpath(primary_artifact_dir / "predictions.json"),
                        "consistency_report": relpath(primary_artifact_dir / "consistency_report.json"),
                        "damage_visualization_dir": relpath(primary_artifact_dir / "damage_visualized"),
                    },
                }
                write_json(case_dir / "case_record.json", record)
                save_case_registry(record)
                st.success(f"Case {clean_case_id} was created and processed. It is now awaiting officer review.")
                st.session_state["newest_case_id"] = clean_case_id
                st.rerun()
            except (ValueError, FileNotFoundError, NotADirectoryError, RuntimeError, subprocess.TimeoutExpired) as exc:
                st.error(str(exc))
                st.caption(f"If a case folder was created, inspect its run_stdout.log / run_stderr.log for details: `{relpath(case_dir)}`")
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")
                st.caption("Check that run_portguard_inspection_v2.py, the model weights, PDF extractor, field aliases, and OCR scripts are present in the expected project folders.")

with saved_tab:
    st.subheader("Saved inspection cases")
    registry = get_registry()
    if not registry:
        st.info("No saved cases yet. Create and run a case in the first tab.")
    else:
        ids = [str(item.get("case_id", "")) for item in registry if item.get("case_id")]
        default_id = st.session_state.get("newest_case_id")
        index = ids.index(default_id) if default_id in ids else 0
        selected_case_id = st.selectbox("Choose a saved case", ids, index=index, key="saved_case_selector")
        record = get_case_by_id(selected_case_id)
        report_file = CASE_ROOT / selected_case_id / "integrated_inspection_report.json"
        report = read_json(report_file, None)
        if not record:
            st.error("The case registry entry exists, but case_record.json is missing or invalid.")
        elif not isinstance(report, dict):
            st.error("The integrated report is missing or invalid for this case.")
        else:
            meta1, meta2, meta3 = st.columns(3)
            meta1.metric("Case ID", record.get("case_id", "—"))
            meta2.metric("Review decision", (record.get("review") or {}).get("decision", "Pending"))
            meta3.metric("Documents", len(record.get("document_ids", [])))
            st.caption(f"Created: {record.get('created_at', 'unknown')} · {record.get('document_source_note', '')}")
            render_report(report, key_prefix=f"saved_{selected_case_id}")
            st.divider()
            st.subheader("Officer review record")
            st.caption("This is a local academic review record, not an authenticated or tamper-proof operational log.")
            current_review = record.get("review", {}) or {}
            with st.form(f"review_form_{selected_case_id}"):
                reviewer = st.text_input("Reviewer / guide (optional)", value=current_review.get("reviewer", ""))
                decision = st.selectbox("Review decision", ["Pending", "Accept", "Override", "Reject"], index=["Pending", "Accept", "Override", "Reject"].index(current_review.get("decision", "Pending")) if current_review.get("decision", "Pending") in ["Pending", "Accept", "Override", "Reject"] else 0)
                notes = st.text_area("Review notes", value=current_review.get("notes", ""), height=100, placeholder="e.g. inspect original document for the UN-number conflict; verify the damage detection manually.")
                save_review = st.form_submit_button("Save review decision", type="primary")
            if save_review:
                previous = dict(current_review)
                history = list(previous.get("history", []))
                history.append({
                    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "reviewer": reviewer.strip(),
                    "decision": decision,
                    "notes": notes.strip(),
                })
                record["review"] = {
                    "decision": decision,
                    "reviewer": reviewer.strip(),
                    "notes": notes.strip(),
                    "history": history,
                }
                record["status"] = {
                    "Pending": "Awaiting officer review",
                    "Accept": "Accepted by reviewer",
                    "Override": "Overridden by reviewer",
                    "Reject": "Rejected / needs further inspection",
                }[decision]
                write_json(CASE_ROOT / selected_case_id / "case_record.json", record)
                save_case_registry(record)
                st.success("Review decision saved to this local case record.")
                st.rerun()
            history = (record.get("review") or {}).get("history", []) or []
            if history:
                with st.expander("Review history", expanded=False):
                    st.dataframe(list(reversed(history)), use_container_width=True, hide_index=True)
            st.download_button(
                "Download case record (JSON)",
                data=json.dumps(record, indent=2, ensure_ascii=False),
                file_name=f"{selected_case_id}_case_record.json",
                mime="application/json",
                key=f"download_case_{selected_case_id}",
            )

with how_tab:
    st.subheader("Recommended guide demonstration")
    st.markdown(
        "1. Create batch/case `PGDEMO001` (case IDs must not contain hyphens).\n"
        "2. Select a container photo from `test_images/` or upload one.\n"
        "3. Choose **Run all synthetic cases (001–003)**. The app runs all cases with both clean and scan-like variants automatically.\n"
        "4. Show damage detections, extracted document fields, discrepancies, and the clean-vs-scan-like comparison.\n"
        "5. Open **Saved cases & officer review**, add a review note, and save an Accept/Override/Reject decision.\n"
        "6. Explain that the damage photo remains a separate demo input; it is not verified as belonging to any synthetic shipment."
    )
    st.markdown("### What this prototype currently does not do")
    st.markdown(
        "- It does not identify text or placards on container photos; the existing model detects its trained damage classes only.\n"
        "- It does not verify that a photograph and document set describe the same real shipment.\n"
        "- Uploaded documents must currently be images. PDF page rendering is not implemented.\n"
        "- The synthetic image crop fallbacks were developed on starter layouts; the teammate PDF parser is a label/regex baseline and needs validation on diverse real layouts.\n"
        "- Officer review decisions are local demo records only; no external customs, port or safety system is contacted."
    )

st.divider()
st.caption("PortGuard academic prototype · Missing/uncertain values require review · No autonomous operational decisions")
