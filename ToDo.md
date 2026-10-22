Sem VII has two parts. Part A is a complete, consistent design for the whole project. Part B builds the first half, "evidence → checks": reading the photos and documents, then running the rules. I put the must-haves first, so if time runs short, cut from the bottom of Part B.

## Part A: Methodology, architecture, solution (whole project)

- [ ] **A1 Scope freeze.** Get your HOD's written OK on export, classes 8 and 9 (5.1 optional) and one desk.
- [ ] **A2 Title and objectives.** Final title with the repo name, a problem statement, 3–4 measurable objectives and an "out of scope" list.
- [ ] **A3 Literature review, 12–15 sources, mapped to modules.** Cover dangerous-goods misdeclaration, container damage detection, container-number OCR, document extraction, calibration, RAG citation checking and shadow-mode deployment. For each one, state the gap it leaves.
- [ ] **A4 Component contracts.** Write JSON schemas for the vision output, document output, rule outcome and tier, and add them to the repo. Done when the tests validate sample data against them.
- [ ] **A5 Architecture set.** Finalise the 3 diagrams you have, plus a deployment diagram and a sequence diagram.
- [ ] **A6 Methodology chapter.** For each component, give the method, why we chose it and what we rejected. Also cover RQ1–RQ4, the ablations, the splits and the metric definitions for all 10 HOD metrics.
- [ ] **A7 Data plan.** List datasets with licences, the synthetic generation plan, the partner request list (templates and redacted samples only) and a draft consent/NDA letter.
- [ ] **A8 Safety, governance and limits chapter.** Cover shadow mode, the unknown-is-not-pass logic, the IMDG licence and the claim limits.
- [ ] **A9 Traceability matrix.** Map each HOD requirement to a component, a metric, a test and the semester that delivers it.
- [ ] **A10 Sem VIII plan.** Milestones, risks and the frozen list below.
- [ ] **A11 Expert and partner.** Send the abstract and needs list, and track the letter and the partner CFS.
- [ ] **A12 Report and slides.** Assemble these last.

## Part B: Build the first half

- [ ] **B0 Repo.** Run `pytest`, fix failures, and add a CI workflow that runs the tests.
- [ ] **B1 Reference tables.** Add every UN number in classes 8 and 9 from the UN/ADR tables, with a source column. Add the placard specs, container type to max mass for 20GP, 40GP and 40HC (check these), and class to examination pathway.
- [ ] **B2 Rules engine v2.** Grow from 11 to about 25 rules in a YAML catalogue, each with an ID, severity and source. Each rule gets a passing and a failing test, plus a coverage report script.
- [ ] **B3 Synthetic DG documents.** Make declaration, safety data sheet, shipping bill extract and packing list in 6+ layouts, with OCR-style noise and faults tied to rule IDs, 1,000+ sets in all.
- [ ] **B4 Document extraction.** Deterministic parsers plus validators, storing the source span for every field. Report F1 on clean and noisy documents separately.
- [ ] **B5 Container-number reader.** Region detection and OCR, then our decoder. Report character error rate and exact match for raw, with the check digit, and with multi-view (this is RQ1).
- [ ] **B6 Placard detector baseline.** Train YOLO on the public hazmat sets, with placards composited onto container photos to narrow the domain gap. Report P/R/mAP and check a few real container photos.
- [ ] **B7 Damage detector.** Wrap the existing model so it outputs the evidence schema. Set a recall-first threshold and report the "hole" class miss rate honestly.
- [ ] **B8 Pipeline.** One function takes images plus documents and returns evidence, then rule outcomes, then a tier. Expose it through the CLI and API.
- [ ] **B9 Evaluation harness.** One script produces the Sem VII metrics, tagged as synthetic/public data (T0), plus per-stage latency.
- [ ] **B10 Thin demo page.** Streamlit with sample cases, labelled as a demo, not the officer console.

The metrics this semester are OCR accuracy, defect P/R/mAP, document F1, rule coverage and accuracy, and latency measured early. Triage PR-AUC, Brier, RAG citation correctness, override rate and real partner validation come in Sem VIII.

**Order:** A1 and A2 first. Then B0 → B1 → B2 → B3 → B4 in sequence. B5, B6 and B7 can run in parallel across teammates. B8 → B9 → B10 come after, and A3–A9 are written alongside. A12 goes last.

## Frozen for Sem VIII (not started)

- Triage model and calibration.
- RAG corpus and citation verifier.
- Officer console and audit log.
- Shadow replay.
- Seal detector and leakage class.
- Partner and expert-labelled validation.
- Final paper and viva.
