# Real recording validation

The new **Measurement validation** clinician page records exact native-unit measurements from saved, accepted recordings and compares them with independently obtained references. No real evaluation dataset has been supplied. Software tests and invented fixture recordings do not establish clinical accuracy.

The workflow follows the themes of representative participants and recording conditions, independent evaluation, fit-for-purpose references and predefined goals in [IMDRF GMLP, January 2025](https://www.imdrf.org/documents/good-machine-learning-practice-medical-device-development-guiding-principles). This is an implementation protocol, not IMDRF endorsement or certification.

## Before collecting evidence

1. A clinician and independent evaluator define the intended use, exact task, metric, extractor version and native unit. A landmark proxy cannot be compared with an unrelated clinical severity score. For a ratio, the reference must use the same anatomical normalization; for cycle counts, agree cycle rules and time window; for angles, agree joints, coordinate convention and an appropriate independent reference.
2. Prespecify MAE tolerance and independent participant sample size, justified for that intended use. Record recruitment, exclusions, aids/support, age/mobility coverage, sites and camera/lighting conditions. The app's planning defaults are not clinical thresholds.
   The in-app protocol picker uses an existing development visit to show exact implemented metric definitions. Keep that example and any participants whose results informed thresholds out of the prospective evaluation cohort; log them in the training/tuning manifest. The empty offline protocol can be completed before collecting any evaluation recordings.
3. Keep local training/tuning participants out of evaluation. If local supervised models are used, audit patient, site and acquisition overlap with their training roster. MediaPipe pretrained model provenance is separate and cannot be established by the local split check.
4. Obtain monitoring consent and separate optional validation consent. The clinician invites an assigned patient; the patient accepts in **Data & privacy**. Withdrawal is final for that study and removes its cases from subsequent evidence views. A new study is needed for new participation.
5. Have the reference evaluator measure without seeing the app result where possible. Record reference method and blinding honestly. Review the protocol and translations with a bilingual clinician before recruiting people.

## Collect actual recordings

Use a new visit per recording. Record across the planned camera families and lighting conditions, and include supported mobility aids. Preserve the task's ordinary safe assistance. For test-retest, agree a stable context and a short repeat window in advance; enter a matched repeat-group code only for those repeats. Use the same device, lighting and site within a matched group. Cross-device measurements are coverage comparisons rather than same-condition repeatability.

Save accepted measurements, then select the visit in the clinician validation page. The backend extracts the value from its saved module, checks its exact metric/unit/method, requires the linked source file, and snapshots file ID, SHA-256 and module revision. A reused clip hash or visit cannot become another independent recording. Enter references and metadata carefully: saved study cases are immutable, including reference entries; missing references remain unknown. To correct a study's reference data, retain its provenance and start a corrected study rather than quietly modifying prior evidence.

The in-app study dashboard includes **accepted saved measurements only**. It cannot estimate capture success because failed attempts do not become saved modules. Keep a manifest of **every** attempted recording, including quality failures, and evaluate that manifest offline. App study entries are prospectively tagged evaluation; the app has no training roster. Its dashboard is not an independence audit.

## Offline manifest and protocol

```sh
.venv/bin/python scripts/evaluate_recordings.py --template data/processed/validation/recordings.csv --protocol-template data/processed/validation/protocol.json
.venv/bin/python scripts/evaluate_recordings.py --manifest data/processed/validation/recordings.csv --protocol data/processed/validation/protocol.json --output data/processed/validation/evaluation.json --deidentified-consented
```

The first command creates empty templates only. Fill the protocol before collecting study data: timezone-qualified `prespecified_at`, reference procedure, exact `measurement` task/metric/unit/method, tolerance, participant target and sampling/confounder notes. The timestamp and consent/deidentification are operator attestations; the tool cannot retrospectively verify them. Output is exclusive-create at mode 600; templates/results are under an ignored private data path. Use pseudonymous participant/site codes; do not include names, contact details, video paths or free-text patient histories.

Each manifest row is an attempted recording/metric with split `training`, `tuning` or `evaluation` and status `accepted`, `rejected` or `unavailable`. Accepted rows require measured values; other statuses require an empty measured field. Reference absence is empty, never zero. Retain real zeros. `reference_blinded` is true/false/unknown. Empty camera, lighting, site or age fields become an explicit unknown group. A protocol evaluates one exact metric/unit/method. Do not apply one numerical tolerance to unrelated units.

Only evaluation rows enter reported performance. Participant overlap with training/tuning and duplicate recording/metric/method rows fail evaluation. The CLI does not process or upload media: obtain measured values from the existing local analyzer/saved results and independently record the references. It does not independently verify that different recording IDs contain different clips; maintain a recording hash inventory during dataset preparation.

## Interpret the evidence

- Accuracy reports paired recordings **and independent participants**, participant-balanced bias, MAE and RMSE. Each person's recordings receive equal weight within that person; people receive equal weight overall.
- MAE intervals use 2,000 deterministic participant bootstrap samples. Fewer than three paired participants show no interval. An interval with a small, unrepresentative sample is descriptive evidence, not a generalization guarantee.
- Rejected/unavailable attempts and accepted attempts without references remain visible in coverage denominators. Blinded, unblinded and unknown reference counts remain separate. Review heterogeneity in listed reference methods.
- Repeatability averages matched-group sample variances within each participant, then across participants. It reports within-participant SD and `1.96 × sqrt(2) × SD`; the latter assumes stable, approximately normal measurement error. True change in movement or inconsistent reference conditions can invalidate that interpretation.
- Camera, lighting, site and age strata retain native units and actual counts. Sparse or unknown strata require more evidence. The actual-data 3D comparison plots reference, measured value and error, all in the selected unit.

Review blinded reference quality, failure causes, subgroup coverage and prospective workflow outcomes before drawing a clinical conclusion. Meeting a descriptive point-estimate target does not certify a medical device. Track extractor/software changes and repeat the relevant evaluation after material changes.
