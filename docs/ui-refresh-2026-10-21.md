# UI refresh and care-context additions (21 Oct 2026)

## Visual system

The interface now reads as a calm clinic chart rather than a dark dashboard.

| Token | Light | Dark | Used for |
|---|---|---|---|
| Paper | `#F6F7F5` | `#111A1C` | Page background |
| Ink | `#16262A` | `#E7EDEA` | Text, metric rules |
| Indus green | `#1D6B52` | `#6FC3A2` | Primary actions, saved/accepted state |
| Ochre | `#8F5410` | `#E0B270` | Waiting, in progress, OFF medicine |
| Brick | `#A3392F` | `#EE9A8F` | Repeat / error |

* **Typeface:** Atkinson Hyperlegible Next, designed by the Braille Institute for
  low-vision readers, with Noto Naskh Arabic for Urdu. Both are self-hosted in
  `app/static/fonts` (SIL OFL licences included), so no font request leaves the
  clinic network.
* **Mark:** an Archimedean spiral — the bedside spiral-drawing test — with a
  slight tremor in its outer turn. It is drawn once on the welcome page and
  respects `prefers-reduced-motion`. SVGs live in `app/static/brand`.
* **Colour carries state only.** Task cards, the next-step panel and visit rows
  show saved / waiting state on their leading edge (right edge in Urdu).
* **Both themes** are defined in `.streamlit/config.toml`; Streamlit follows the
  device setting and Settings can switch it. The 3D movement viewers keep a dark
  "instrument" ground in both themes. All colours come from
  `app/components/palette.py`.
* The Streamlit "Deploy" toolbar is hidden (`client.toolbarMode = "minimal"`).

## New features

* **Medicine timing per visit** (`backend/db/context_models.py`,
  `backend/services/visit_context.py`). The patient records whether their
  Parkinson's medicine is ON, wearing off or OFF, roughly when the last dose was
  taken, and any extra involuntary movement. It is context for comparing like
  with like, not a measurement and not advice. Movement and voice pages remind
  the patient if it is missing. The new `visit_contexts` table is additive:
  `init_db()` creates it on an existing database without a migration.
* **Progress trend chart.** A plain 2D line of one measure across accepted
  visits, with readable measure names, the first visit as a dotted reference,
  "change since first" figures and markers showing medicine timing (filled = ON,
  open = wearing off / OFF). The 3D statistical review is still one click away.
* **Clinician caseload** (`backend/services/caseload.py`). Linked patients with
  visits awaiting review, open visits, last check-in, falls reported in the last
  14 days, medicine timing at the last visit and the next planned review. It
  reads counts and dates only — no measurements, notes or media.
* **Patient home "next step".** One stated action chosen from the patient's own
  records (continue an open visit → today's check-in → read a completed review →
  start a visit), plus last check-in and the next planned review date.
* **Visit progress** on Start Assessment: "2 of 6 task groups saved" with a
  segmented bar; resume / new visit side by side.
* **Urdu and Roman Urdu** for the whole Check-in & goals page (previously
  English only), and directional isolation so dates read correctly in Urdu.
* Friendlier labels: "Daily activities" instead of "ADL Questionnaire",
  "Check-in & goals" instead of a second "My Care", readable visit status and
  review status, an admin user table without raw IDs.

## Fixes

* **Clinician Trends page crashed** with `StreamlitDuplicateElementKey
  ('care_patient')` once a patient had data, because the page asked for the
  patient selector twice. Fixed and covered by a test.
* The home page ended with a "A note from your day" heading that had nothing
  under it; it is replaced by the next-step panel.
* Movement page title now sits above its task selector.
* Charts on light pages no longer inherit dark-only colours; the 3D replay is
  rendered with `theme=None` so its labels stay legible.

## Tests

`tests/test_visit_context_and_caseload.py` adds 10 tests (access control,
validation, closed visits, caseload privacy, hub save, home next step, clinician
dashboard + trends). Full suite: 469 passed, 4 skipped; `ruff check .` clean.

## 25 Oct follow-up

Fixes from the review of this refresh, plus hardening found along the way.

* **Theme switches.** Changing the device or Settings theme with a page open
  left custom colours stale until the next click, which hid the login labels.
  A tiny watcher (`app/components/theme_sync.py`) compares the theme on screen
  with the one the page was drawn for and asks for one rerun; it never loops.
* **Home next step.** A finished review is pointed out for 14 days
  (`REVIEW_NOTICE_DAYS`) and names the visit date; after that Home goes back to
  "Start a visit". "Next planned review" (Home and caseload) now comes from the
  newest follow-up note that sets a date, not the earliest date in any note.
* **Lighter pages.** Visit lists no longer load per-frame landmarks (about 98%
  of a movement result). The database drops them (`jsonb -` on PostgreSQL,
  `json_remove` on SQLite) and marks the result `landmark_frames_omitted`;
  `get_assessment()` and the replay baseline still load them in full.
* **Sign-in pause.** Five wrong passwords for one email within 15 minutes pause
  sign-in for that email (web and mobile alike). Only a hash of the typed email
  is stored, unknown emails get the same answer, and a verified recovery code
  lifts the pause.
* **Patient words shown as typed.** Check-in notes, goals, follow-up notes and
  the medicine note are escaped before Markdown rendering: no remote images,
  formatting or disguised links.
* **Camera clips.** Abandoned `data/private/capture/tmp*.avi` clips older than
  12 hours are removed at start-up and when a new clip starts. The first start
  after this change deletes the leftover clips already in that folder.
* **Visits.** With a visit open, Start Assessment can switch to another open
  visit or start a new one. Urdu and Roman Urdu now say "جانچ شروع کریں" /
  "Jaiza shuru karein" everywhere, matching the menu.
* **Housekeeping.** Unused copy keys and the unused inline wordmark were
  removed, as were four unused imports in `output/linkedin-demo` scripts that
  had been failing CI since 19 Oct (ruff runs before the tests there).

Verification: full suite **480 passed, 3 skipped** with real model tests on
(the three skips need PostgreSQL). On a disposable PostgreSQL 16 container,
`test_backend.py` (14), `test_care.py` (28), `test_auto_reports.py` (11) and
`test_production_security.py` (41, including the three race tests) passed, each
on a fresh database. `ruff check .` is clean. A browser check on an isolated
scratch database confirmed the theme switch in both directions, the sign-in
pause message, and verbatim rendering of a Markdown-laden note.
