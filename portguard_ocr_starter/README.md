# PortGuard OCR + Document Extraction Starter Dataset

**Purpose:** starter material for building and testing OCR and field extraction in the PortGuard academic prototype.

## Important data notice
- Every record and document in this package is synthetic and labelled **SYNTHETIC - TEST ONLY**.
- These are mock data sheets inspired by common document categories, not copies of official customs, carrier, dangerous-goods or SDS forms.
- They are not evidence of regulatory compliance and must not be used for real shipping, customs, safety or operational decisions.
- Synthetic examples are useful for pipeline development and software tests; they do not prove performance on real port documents.

## Contents
- `documents/`: 12 one-page mock PDFs: 3 linked test cases x 4 document types.
- `images/clean/`: clean page renders of each PDF (use as OCR inputs).
- `images/scan_like/`: mildly degraded grayscale versions to test OCR robustness. These are generated degradations, not real scanner captures.
- `ground_truth/labels.json`: complete labels with expected fields for each document.
- `ground_truth/labels.jsonl`: one JSON object per line, useful for streaming pipelines.
- `ground_truth/field_ground_truth.csv`: flat field-level labels for viewing/annotation.
- `ground_truth/document_manifest.csv`: path and document-type index.
- `ground_truth/case_level_test_notes.json`: notes on intentional cross-document mismatches for later consistency-check testing.
- `scripts/evaluate_field_extraction.py`: exact-match field evaluation helper.

## Document types and fields
1. `dangerous_goods_declaration`: container number, seal number, UN number, proper shipping name, hazard class, packing group, packages, gross weight, shipper and consignee.
2. `shipping_details_summary`: shipping reference, container and seal numbers, shipper, consignee, ports, cargo description, UN number and hazard class.
3. `packing_list`: reference, container and seal numbers, goods description, packages, gross weight, UN number, hazard class and consignee.
4. `sds_section_14`: UN number, proper shipping name, transport hazard class, packing group, environmental-hazard note and product identifier.

Field values are document-specific: labels reflect what actually appears on that synthetic document, including any intentional mismatch. Do not substitute case-master values for per-document ground truth.

## Suggested first experiment
1. Run your OCR engine against every image under `images/clean/`.
2. Store OCR text per `document_id`.
3. Add document-type-specific extraction that emits JSON using the field names in `ground_truth/labels.json`.
4. Save model outputs in a JSON file/JSONL as records like:

```json
{"document_id": "001-DG", "fields": {"container_number": "DEMU1234560", "un_number": "UN 1760"}}
```

5. Evaluate using:

```bash
python scripts/evaluate_field_extraction.py predictions.json
```

6. Repeat with `images/scan_like/` and compare performance. Treat the 12 documents as a small smoke-test set, not a statistically sufficient benchmark.

## Notes for interpretation
- Exact-match field accuracy is a simple starter metric. It does not replace character error rate (CER), word error rate (WER), per-field precision/recall/F1, or manual review of safety-critical fields.
- Missing, unreadable or uncertain values should be returned as null/unknown by the application rather than invented.
- A real-world evaluation needs authorised, appropriately redacted samples and independently checked labels from a domain expert.
