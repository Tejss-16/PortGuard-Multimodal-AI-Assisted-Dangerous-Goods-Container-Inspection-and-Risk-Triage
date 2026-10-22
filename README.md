# PortGuard

PortGuard is a BE major-project prototype that combines container damage detection, shipping-document OCR, field extraction, and cross-document consistency checks for human review.

## Current features

- Detects the damage classes supported by the trained model (for example, holes and rust).
- Reads PDFs: uses embedded text when usable and OCR for scanned or sparse-text pages.
- Reads document images with Tesseract OCR and extracts fields such as container number, seal number, UN number, hazard class, and packing group when found.
- Compares relevant fields across documents in the same case and flags matches, possible OCR errors, disagreements, and missing values.
- Provides a local Streamlit dashboard for running a case and recording a reviewer decision.
- Includes synthetic test cases and clean/scan-like document images for development tests.

## Run locally (macOS)

Install Python 3.10 or newer and Tesseract OCR. If Tesseract is not installed:

```bash
brew install tesseract
```

Create and activate a virtual environment, then install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the dashboard from the repository root:

```bash
streamlit run portguard/dashboard/portguard_case_dashboard_v2.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Main folders

- `data/` — sample container images and sample shipping documents.
- `models/container_damage_detector/weights/best.pt` — trained damage-detection weights used by the prototype.
- `portguard/` — application modules: damage detection, document processing, consistency checking, workflow, dashboard, and RAG-related scripts.
- `portguard_ocr_starter/` — synthetic documents/images, ground-truth labels, and OCR testing scripts.
- `runs/` — training and prediction outputs retained for project review.

## Important limitations

The synthetic documents are fictional. The container photograph is associated with uploaded documents by the operator; the prototype does not independently verify that they belong to the same shipment. OCR and field extraction may be wrong, and flagged values require human review. The prototype does not decide cargo contents or make automatic release/hold decisions. It has not been validated for operational use.
