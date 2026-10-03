# Local verification — 3 October 2026

The final substantive implementation was tested with CPython 3.11.15, Streamlit 1.65.0, MediaPipe 0.10.35 and OpenCV 4.14.0 in the isolated project virtual environment.

| Check | Observed result |
|---|---|
| `PARKINSENSE_RUN_MODEL_TESTS=1 .venv/bin/pytest -q --tb=short` | **339 passed**, 3 PostgreSQL-only race tests skipped; 121.33 seconds; final readiness suite includes the CLI/auth/version regressions. |
| `.venv/bin/ruff check .` | All checks passed |
| Python compileall | App/backend/ML/scripts compile successfully |
| `uv lock --check` | Lock matches project dependency metadata |
| Independent PostgreSQL backend/care suite | **40 passed** against an isolated temporary `parkinsense_test_*` database; three new care tables verified and test database removed |
| PostgreSQL security/backup checks | Isolated dedicated security suite and all 3 concurrency cases passed; new stale-login/recovery pair also passed after auth integration. Backup roundtrip preserved dates, nullable self-reports and Urdu text. Dedicated test databases removed. |
| Measurement validation | Synthetic known-error tests verify participant weighting, missing/rejected coverage, matched repeat grouping, split leakage, source file/hash requirements, withdrawal, method/version consistency and bounded private CLI output. No clinical dataset evaluated. |
| Private report integration | Actual UI button creates a private attachment grant; no native public Streamlit download node. Gateway tests cover actual HTTP GET/HEAD/ranges, expiry, revocation and no-store headers. |
| Patient usability | English/Urdu/Roman Urdu task/voice/ADL instructions and all 33 fault codes; mobile 390×844 browser check shows RTL instructions and no horizontal overflow. Physical-device capture was not tested. |
| Readiness browser | Isolated synthetic fixture showed empty validation evidence, 0 pilot observations and Unknown review savings. No real clinical or business outcome was entered. |
| Secure media HTTP health | Loopback gateway `http://127.0.0.1:8503/health` returned `ok` |
| Main Streamlit HTTP health | `http://127.0.0.1:8501/_stcore/health` returned `ok` |
| PostgreSQL container | Local `parkinsense_pk-db-1` healthy, loopback port 55432 |
| Browser sign-in and modular hub | Synthetic patient in a separate test database signed in and reached the hub |
| Focused live camera panel | Production movement page with isolated synthetic camera/XYZ fixtures: default focused lines/trails, latest 3D frame, tracking loss/return, viewpoints and actual Start/Finish fragment controls; user hardware camera was not accessed for this upgrade |
| Live tracking state and recording | Locked detached snapshots; 45-frame/3-second history; 0.35-second freshness on reads; camera gaps/hand switches clear trails; raw stored frames remain free of overlays; completed capped/interrupted clips stay reviewable |
| Persistent live 3D rendering | 20 live UI regressions, 24 focused geometry checks and a Node renderer lifecycle/queueing check; changing landmark messages retain host identity; vendor bundle stays outside frame payloads; latest-frame queueing, pointer pauses and unmount/late-render cleanup verified |
| Real landmark inference | Both official pose/hand bundles load and infer; blank/noise frames/videos produce no person and no accepted measurements |
| Source recording association | Regression tests verify reanalysis uses the selected file UUID; later uploads cannot replace the video's association with stored landmarks |
| Reports and review | Result changes reset review; saved summaries carry provenance and stale flags |
| Automatic patient reports | One current report per assessment; module/report writes are atomic; reanalysis, compatible references, human review/context and completion update report metadata; manual snapshots remain separate |
| Report authorization and database | 11 automatic-report tests plus 12 existing backend checks passed on independently created guarded PostgreSQL test databases; both databases removed safely |
| 3D module statistics | All movement/voice variants, NLP and ADL; unit grouping, real zero/negative values, finite/acceptance gates, recording gaps, compatible history, stable multiple-panel controls and native label padding |
| Fault and retry guidance | Canonical recording/processing faults, numbered English/Roman Urdu steps, private-error redaction, explicit self-report follow-up with negation checks |
| Analysis UI/report persistence | Automatic saved-report download survives a fresh session; rejected ADL attempts have numbered guidance and an unsaved report; rejected replacement retains earlier saved evidence and clears accepted preview; same-minute visit selection remains on its selected UUID after summary changes |
| Browser report download | Actual synthetic-account HTML download completed and the downloaded standalone document displayed correctly, including measurement units/references and questionnaire responses |
| Browser fault report | Actual rejected-attempt HTML download completed; unsaved-preview label, numbered lighting steps and absence of accepted measurement values verified |
| Genuine 3D geometry | World XYZ required; geometry invariant to image aspect/normalized depth; finite/visibility masks and tracking gaps preserved; fixed estimated-meter scale and at most 90 replay frames |
| Studio controls and export | Camera/model/speed/trail controls; incompatible baselines disabled; user-triggered self-contained HTML export with no CDN/private prose; changed results/options hide stale downloads |
| Human care workflow | Explicit self-report, unknown falls, dated upsert, patient-authored goals, clinician-authored follow-up; ownership, revoked assignments, consent and inactive actors covered |
| Browser 3D display | Isolated preview renders solid body and hand articulation; hand replay advanced from 0.0 to 2.2 seconds; trails, readable Play/Pause and visible field borders verified. Example geometry does not establish clinical accuracy. |
| Export | Tested Parquet round trip, UTC alignment, patient isolation, missing modalities and omission of raw prose/landmarks |
| Authentication/permissions | Patient-only registration, consent, password hashing, linked care teams, inactive accounts and admin restrictions tested |
| MCP | Typed facade tested; localhost HTTP rejects absent/wrong bearer tokens; caller identities/arbitrary file paths are excluded |

One test warning remains: the installed Starlette SDK deprecates its httpx test-client integration. It did not fail the HTTP authorization test. CI configuration is supplied but has not run remotely because no Git remote or hosted workflow was configured.

Earlier navigation and contrast checks included 14 app/studio UI regressions and nine geometry/studio tests. They are included in the expanded full suite above. Browser screenshots include `artifacts/parkinsense-3d-upgrade.jpg`, `artifacts/parkinsense-care-upgrade.jpg`, `artifacts/parkinsense-statistics-upgrade.jpg` and `artifacts/parkinsense-patient-report.jpg`. The latter two use explicitly synthetic example data in an isolated QA database.

After the final report-freshness, saved/unsaved labelling and readable-unit adjustments, **61 targeted report/app/guidance integration/statistics/studio UI checks passed again**. Lint, compilation and lock verification also passed. Reports retain the selected visit when another summary changes and report reads flag stale references/language without regenerating content.

The live upgrade initially exposed an outdated snapshot fixture that supplied coordinates without camera receipt times. The fixture now represents an active camera; the freshness requirement remains enforced. The final full suite above passes. After the final late-render disposal guard, the Node lifecycle check passed again. A combined 36-check renderer/live UI/app/studio run also passed. Browser QA confirmed the same Plotly modebar instance across ongoing frame updates/viewpoint changes and exercised Start/Finish on real Streamlit fragments. The explicitly synthetic camera/3D preview is saved as `artifacts/parkinsense-live-tracking.jpg`. The local app was reloaded to use the final source, without changing its normal database records.

Tests use invented fixtures strictly for software mechanics, plus official models on non-person blank/noise input. Those fixtures do not establish Parkinson classification, clinical score performance, meaningful change, actual grasp contact, or detector reliability on patients. Real clinical training data/reference labels were not supplied.

No default account or fictitious assessment was seeded into the normal application database by the implementation. Browser test fixtures are isolated under ignored `artifacts`. Existing user-created records are preserved. The initial login preview is saved as `artifacts/parkinsense-preview.jpg`; the upgraded design and 3D preview screenshots are also kept under ignored `artifacts`.

The remaining clinical and deployment acceptance gates are itemized in `roadmap-analysis.md`.

## Recent visits loading fix

The observed browser error was a failed lazy import of `DataFrame.CFF5tBU0.js`. The main server returned this module and all 297 transitive JavaScript modules with correct MIME types and matching installed checksums; all 347 installed static files matched the package manifest. The browser tab was reloaded to clear the failed import. The read-only, five-row Home summary now uses escaped native HTML through the already loaded Markdown renderer, so it does not request the DataFrame grid. Other interactive grids retain their existing functionality.

The 8 focused summary tests and 28 existing app/usability tests passed. An isolated synthetic browser preview verified the native visits table, four summary fields, mobile cards at 390px without horizontal overflow, Urdu RTL labels and absence of the dynamic-import error. No normal patient data was written. Browser reload requires signing in again.
