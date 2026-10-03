# Clinic feasibility pilot

The clinician's **Clinic pilots** page makes a real pilot recordable. It does not create patients, recruit a clinic, run a study or establish clinical accuracy. No real pilot outcomes or payment evidence are prefilled. Real-world measurement validation is a separate workflow.

The page records the plan, participation decisions, observed task and recording counts, patient-reported usability, comparable review durations and reported payment intentions. A pilot belongs to its creating clinician. Patients acknowledge participation themselves in **My Care**, separately from monitoring consent. Administrators cannot open pilot evidence, observations or media.

## Before recruiting a clinic

1. Identify a clinician sponsor and a person authorized to discuss the clinic's purchasing decision. Recruitment and communications must be performed by the project team; this implementation does not contact anyone.
2. Write the task list, population, recording setup, languages, assistance allowed, review procedure and safety escalation in the protocol notes. Define what counts as a completed task before observing results. The ordinary clinical team continues to make clinical decisions.
3. Agree a start and end date, no more than 366 days apart. Agree minimum patient and observation coverage, target task completion, usable recordings, patient usability and review time savings before collecting outcomes. Default targets are editable planning examples: 10 participating patients, 10 comparable review pairs, 10 usability responses, 20% median review time saving, 85% completed/planned tasks, 85% usable/all recordings and median ease of use at least 4/5. These are not medical or statistically powered acceptance criteria. The study team must justify its own sample size and thresholds.
4. Explain what is recorded, who can access it, withdrawal, retention and the limits of an early feasibility pilot. Obtain the clinic's required ethics, governance and data handling arrangements for the intended study. The software's checkbox records an acknowledgement; it does not replace an approved participant information sheet or informed consent process where required.
5. Only invite patients assigned to the owning clinician, with active accounts and monitoring consent. Each patient independently chooses whether to acknowledge the optional pilot. The clinician cannot acknowledge on the patient's behalf.

Targets, dates and protocol notes remain editable before the first outcome or review timer. The first observation, payment intention or timer start freezes the plan. A subsequent protocol change requires a new pilot, rather than retroactively changing the target used to interpret outcomes.

## Record a visit without hiding unsuccessful attempts

1. Record the tasks agreed before the visit. A visit must contain at least one planned task. Each observation supports at most 100 planned tasks and 100 recording attempts.
2. Count attempted tasks even if the patient did not finish or the recording failed. **Completed** means the patient finished the agreed instructions. **Task completion = completed / planned**, so tasks never attempted remain in the denominator. The dashboard separately counts tasks not attempted and attempted but incomplete.
3. Count all recording attempts, including quality rejection, upload failure and camera failure. Count a recording as usable only when it passes the recording quality check defined in the protocol. **Usable recording fraction = usable / all attempts**. Passing a recording quality check does not establish clinical measurement accuracy.
4. Ask the patient how easy the task and recording workflow were to use: 1 very difficult, 2 difficult, 3 neutral, 4 easy, 5 very easy. Transcribe their own response; do not infer it from successful completion. If not asked, leave it unknown. Record whether help was needed as yes, no or unknown, and label the device mobile, desktop, other or unknown.
5. Link the authorized assessment being reviewed if collecting review durations. Baseline and app durations must concern this same assessment. Do not combine unrelated visits or patients into a pair. For valid comparisons, standardize the review task, reviewers, case complexity and information available; counterbalance review order and address learning/carry-over effects in the protocol.
6. Use **Start review timer** immediately before reviewing and **Stop review timer** immediately afterward. The elapsed server timer persists across browser reruns. It includes idle time and cannot verify clinician attention. Only one timer can run per pilot. Stopped timers are scoped to their patient, assessment and baseline/app mode and may be used once. A timer over four hours or affected by a backward server clock is unusable; it becomes missing, not an estimated duration. Finalizing a pilot discards unfinished timing intervals.
7. Alternatively enter an explicitly **manually reported** duration in seconds. The report retains this source separately from collected timer values. An unanswered duration remains unknown. A reported zero stays zero; a zero baseline cannot supply a percentage-saving denominator.
8. Save the observation. Observations are append-only; the software does not silently replace a failed visit with a later successful one. Maintain one record per real visit/session and document any repeat sessions. It remains the operator's responsibility to avoid duplicate records and verify transcribed counts.

The dashboard computes the median of paired differences in minutes and separately the median of paired percentage savings when the baseline is greater than zero. Negative savings remain negative. It shows total observations, distinct currently participating patients, paired review coverage, usability response coverage and recording denominators. Repeated visits from one patient cannot replace minimum distinct-patient coverage. Missing observations do not become zero or a successful target. A target stays **unknown** until the planned coverage relevant to that target is reached; **met** means that particular feasibility threshold was met in these collected records, not a validated product or business claim.

Both 3D charts use actual saved values. The task plot has planned, attempted and completed task counts as its three axes. The review plot has baseline minutes, app minutes and comparable-pair order; the order axis is an observation index, not a clinical measure. No chart is generated for missing review pairs.

## Payment discussions

Record the respondent's role (clinic owner, procurement, clinician or other), explicit yes/no/undecided intention, date and proposed payment period. An amount is optional and can accompany only an explicit yes. Supported currencies are PKR, USD, EUR and GBP; values of different currencies or periods are not combined. Keep respondent names and contact details out of notes. These records represent reported intentions, not paid invoices, contracts, collected revenue or confirmed market demand. Multiple responses are discussions, not necessarily different clinics or independent buyers.

## Privacy and exports

Every operation rechecks the authenticated, active owner. Patient observations also require the current clinician assignment, active patient account, monitoring consent and separately acknowledged pilot participation. Withdrawing participation, withdrawing monitoring consent, deactivating the patient or removing the clinician assignment immediately excludes that patient's observations and timers from dashboards and new exports. It prevents new observations. Previously recorded rows are retained under the clinic's data handling policy; withdrawal does not silently erase audit or study records, and a downloaded export cannot be remotely recalled.

**Download deidentified aggregate** includes only the frozen target plan, aggregated numeric coverage/outcomes, target checks and counts of reported payment discussions. It excludes pilot/patient/assessment identifiers, names, dates, private notes, media references, proposed amounts and respondent records. Small aggregates can still be sensitive; the receiving clinic controls appropriate sharing and any minimum-cell disclosure rules. The app does not export patient-level evidence from this page.

Close a pilot only after checking that available visits, failures and missing responses are recorded. Closure freezes new enrollment, observations and payment entries and leaves the original missing values unknown. A current authorized clinician can continue to read the finalized pilot.

## What remains external

- Actual participating clinic and patients, an approved/reviewed protocol appropriate to the setting, study staff and genuine observations.
- Independent clinical measurement validation and representative recordings across intended populations, camera setups and lighting.
- A justified sample size, analysis of confounding and uncertainty, and independent review of conclusions.
- Real purchasing discussions and, if appropriate, a separate commercial agreement and payment system.

The international [IMDRF good machine learning practice guidance (2025)](https://www.imdrf.org/documents/good-machine-learning-practice-medical-device-development-guiding-principles) addresses appropriate evaluation of medical AI. This feasibility workflow supports collecting operational evidence; it does not claim regulatory approval or compliance with every guiding principle.

Implementation: `backend/db/pilot_models.py`, `backend/services/pilot.py`, `app/components/clinic_pilot.py`. Verification uses isolated synthetic accounts and visit counts; it does not claim a real clinic pilot has occurred.
