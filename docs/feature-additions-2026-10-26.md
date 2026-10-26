# Competitor-inspired additions - 26 October 2026

These features close gaps named in
[the competitor analysis](competitor-gap-analysis-2026-10-25.md). All are
monitoring or practice aids: none diagnoses, scores severity or gives treatment
advice, and all patient-facing text is in English, Urdu and Roman Urdu.

## What was added

| Feature | Where | Data |
|---|---|---|
| **Spiral drawing and two-circle tapping** on the phone screen, left or right hand | Movement → Spiral & tapping; a seventh task group on Start Assessment | Saved as modules `spiral_*` and `touch_tap_*` with the raw trace or taps |
| **Same-setup check**: names differences in distance, position, camera side and phone orientation (or screen size and finger/stylus for touch tests) against the comparison recording; shows how the person was framed last time before recording | Movement and touch result pages; before recording | Computed from stored landmarks; nothing new stored |
| **Medicine ON/OFF diary** with one-tap buttons, earlier-time entry, a 7-day chart and usual medicine times; Home asks for an entry after a usual time | Check-in & goals → Medicine diary; Home; clinician follow-up; caseload column | `medication_diary_entries`, `medicine_times` (times only, never names or doses) |
| **Weekly task plan** set by a linked clinician; Home shows today's planned tasks and task cards say "Planned for today" | Patient follow-up → Weekly task plan; Home; Start Assessment | `task_plans` (newest is current) |
| **Walking beat** (metronome, starting from the last measured cadence) and **louder-voice practice** with a live meter | Voice and daily life → Practice | None: runs in the browser only |
| **Listen** buttons that read task instructions and voice prompts aloud; Urdu and Roman Urdu readers hear the Urdu-script text | Movement, touch and voice pages | None |
| **Help and walking aid** per visit, and "did someone help fill this in?" per check-in | Start Assessment; check-in form; Progress table; clinician overview | `visit_assistance`, `checkin_assistance` |

## How touch tests are scored

The canvas sends normalized coordinates and times only; `ml/touch` does all
scoring so one rule set applies everywhere. Distances use the drawing width as
the unit.

* **Spiral** (Archimedean guide, three turns): drawing time, mean distance from
  the guide, share of the guide traced, mean speed and its variability, finger
  lifts, and the share of 1–15 Hz oscillation power in the 4–7 Hz band. That
  last measure is omitted when touches arrive at fewer than 30 per second.
  A drawing is rejected when it is too short, covers under 60% of the guide,
  strays more than 6% of the width on average, or does not move steadily
  along the guide.
* **Tapping** (two circles, 20 seconds from the first tap): count, rate,
  share inside a circle, correct alternation, mean interval and its
  variability, rate change from the first to the last third, and distance
  from the circle centre. Fewer than 8 taps, stopping early, or under half
  the taps inside a circle means a repeat.

## Data and privacy

* All new tables are additive, so `init_db()` creates them on an existing
  database without a migration. Existing tables were not changed, and the
  encrypted backup tool picks the new tables up automatically.
* Writes need current monitoring consent, and every read and write goes
  through the existing patient and visit access checks.
* Plan notes are shown as plain text, and diary notes appear escaped in the
  chart's hover label.
* The practice tools never record. Read-aloud uses the browser's own voices;
  some desktop browsers use online voices, so only the app's fixed
  instructions are ever spoken, never patient data.
* The microphone and camera need HTTPS when the app is reached from another
  device (no change from before).

## Verification

* Full suite with real model tests: **533 passed, 3 skipped** (the three need
  PostgreSQL; they passed there on 25 Oct). `ruff check .` is clean.
* On a disposable PostgreSQL 16 container, each on a fresh database: diary
  (13), task plan (8), assistance (3), care (28) and backend (14) passed.
* Browser checks on an isolated scratch database:
  * A spiral drawn on the canvas was accepted, measured and saved, and its
    figure was drawn; two consecutive attempts both updated the canvas status.
  * A 20-second tapping run counted down, submitted by itself and was accepted.
  * The diary one-tap entry worked from Home.
  * The walking beat started, changed tempo and stopped.
  * The Listen button rendered.
* Not checked: louder-voice practice with a real microphone, and speech output
  on a phone with an Urdu voice. Both need a person and a device.

## Not done, and why

* **Android app**: the native app was not changed. The new web pages work in
  a phone browser; native reminders and touch tests need Java work and a
  device test.
* **SMS or WhatsApp reminders** need a messaging provider account and the
  patient's consent to message them. Reminders are on-screen only.
* **Wearable import** (Health Connect) is still for later.
* **Separate caregiver logins** would change the users table's role
  constraint, which needs a reviewed migration. Help is recorded on visits and
  check-ins instead.
* **Validation**: every touch, framing and practice measure is unvalidated. A
  clinic study is the next step before anyone relies on them.
