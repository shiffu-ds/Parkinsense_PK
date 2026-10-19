# Project audit - 18 October 2026

The final Python suite passed **461 tests, zero failures, zero skips**, with
`PARKINSENSE_RUN_MODEL_TESTS=1` and a disposable PostgreSQL 16 database for the
security integration cases. The real application database was not used for
test fixtures. One Starlette/httpx test-client deprecation warning remains.

The Android debug build and signature verification passed. Native unit tests
were explicitly rerun: **12 passed**. Fresh offline lint completed with **zero
errors and 23 warnings** (18 text/localisation, two synchronous preference
persistence, and one each for orientation, discouraged API and debug network
configuration). An older cached report contained 33 warnings, including
online dependency-update notices; the offline result does not establish that
dependencies are current. No physical-phone or emulator acceptance test was
performed. Repository Ruff and `git diff --check` passed.

## Fixes from this audit

- Report baseline selection and the web review now skip incompatible older
  results and continue looking for the first eligible matching method, task
  and language. Six regression cases cover those mismatches.
- Accepted movement/voice review now explicitly explains in English, Urdu and
  Roman Urdu that recording quality does not verify task completion. Public
  demonstrations display the same instruction.

## Real-media observations

Eleven real-video pipeline runs included four matched demonstration analyses,
six deliberate task-mismatch cases and one artificially darkened derivative.

- Published Parkinson's case: outdoor gait 49/60 usable sampled frames;
  indoor gait 60/60. These are two excerpts of the same person. Indoor arm
  swing remained unavailable because required optional arm tracking was poor.
- Published finger-tapping recording: left and right each 177/177 usable
  sampled frames, 21 cycles and approximately 1.79 Hz. Both analyses use the
  same recording; the participant's diagnosis is unspecified.
- MDVR-KCL PD-labelled reading: complete 157.56-second WAV and a fixed
  30-60-second excerpt both passed signal-quality checks. The excerpt had
  72.48% signal activity, six internal pauses and 120.30 Hz estimated median
  pitch. The PD label comes from the source dataset, not this application.
- Darkened gait was rejected, with zero usable landmarks. This was an
  artificial stress transformation, not another participant/camera trial.
- Five of six movement task-mismatch cases passed consistency checks;
  walking-as-reach was rejected for insufficient visibility. Ordinary
  narration also passed vowel/sentence/natural signal checks. **The current
  system does not verify task identity or completion.**

Local outputs include 11 generated video HTML reports and four matched world
XYZ replay HTML files. Historical browser report-download completion was not
verified and is not claimed here.

These observations are not clinical validation. Matched patient recordings
for dedicated turning, sit-to-stand, reach, grasp, object transfer,
hand-opening/closing and sustained vowel remain missing. Independent reference
measurements, representative participants, acquisition repeatability, device
coverage, clinic feasibility outcomes and production operational acceptance
remain outstanding. No clinical accuracy percentage is inferred from tracking
coverage or software test counts.

## Evidence and deliverable

- Detailed Roman Urdu PDF (updated 19 October): `output/pdf/ParkinSense-PK-Complete-Project-Audit-2026-10-19.pdf`.
- Local audit evidence: `artifacts/project-audit-2026-10-18/` (ignored), including
  final JUnit XML, logs, media analyses, source metadata/hashes and helpers.
- Updated component inventory: 90 first-party Python source files with AST definitions
  and SHA-256; the PDF also maps Java, JavaScript and runtime configuration.
- Rebuild source for the document: `tmp/pdfs/build_audit_report.py`.

Sources: [Schaeffer et al. 2016](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2016.00237/full),
[Kasemsap finger-tapping video](https://figshare.com/articles/dataset/Example_Video_Finger_tapping_for_bradykinesia_detection/28930706),
[MDVR-KCL](https://zenodo.org/records/2867216),
[librosa example recordings](https://librosa.org/doc/main/recordings.html).
All selected media are attributed under their CC BY 4.0 terms, with preparation
and limitations recorded. The PDF cites
[IMDRF GMLP guidance](https://www.imdrf.org/documents/good-machine-learning-practice-medical-device-development-guiding-principles)
for future evaluation planning, not as project certification.

## 19 October follow-up: report controls

The final updated full suite passed **463 tests, zero failures, zero skips**,
including real model-loading mode and isolated PostgreSQL security cases.
The earlier 461-case log/XML are preserved separately in the audit folder.

Report HTML now remains stable in browser-session state until its inputs,
actor, selected source or language change. Previously the generation timestamp
could change on unrelated reruns, changing the public download identity or
invalidating a prepared private attempt-report link. Advancing-clock regression
tests exercise both paths. Private exports still use the authorized gateway.

The public demo also offers **Open report here / Report yahin kholein**, which
renders the same attributed HTML used by the download control. The export is
HTML; browser Print can convert the downloaded document to PDF.

Direct browser verification was blocked by the browser URL/access policy on
19 October. No alternate browser or indirect page-fetch workaround was used.
Automated login/section tests and report payload/UI-state tests are distinct
from a successful browser download or inspection of every real-account visit.
