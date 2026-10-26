# Competitor and gap analysis - 25 October 2026

Desk research on products that monitor Parkinson's at home, what they leave
out, and what ParkinSense-PK can add. Sources are listed at the end. Product
claims come from company material or news coverage unless a study is cited;
none of this is independent product testing.

## Where ParkinSense-PK sits

A phone or laptop camera and microphone, no wearable. Patient, clinician and
administrator roles; Urdu, Roman Urdu and English; private local storage;
quality checks before anything is saved; 3D movement replay; medicine timing
per visit; clinician caseload and follow-up. It makes no diagnosis or treatment
claim, and it is not a cleared medical device.

## The field

| Product | What it does | What it needs | Gap ParkinSense can use |
|---|---|---|---|
| StrivePD (Rune Labs) | Passive tremor and dyskinesia from Apple Watch (Movement Disorder API), medication logging and reminders, sharing with clinicians. FDA 510(k), 2022. | iPhone plus Apple Watch | Apple-only hardware; English-first, US care model |
| NeuroRPM | Bradykinesia, tremor and dyskinesia from Apple Watch. FDA 510(k), 2023; prescription only. | Apple Watch, prescription | Same hardware barrier; "neurologist-level" accuracy is a company claim |
| PKG (Global Kinetics) | Clinic-prescribed wrist logger producing movement reports for the neurologist. | Dedicated device through a clinic | NICE estimated £57,877-£67,856 per QALY; evidence "limited and often low quality" |
| Kinesia 360 / KinesiaU, PDMonitor, STAT-ON | Dedicated sensor systems. | Purchased wearables | 2024 NIHR assessment: evidence too thin for meta-analysis |
| KELVIN (Machine Medicine) | Clinician-run video assessment with pose estimation down to the fingertips. | Phone or tablet, clinic workflow | A 2024 paper says camera-angle bias is not yet addressed |
| VisionMD (University of Florida, 2025) | Open-source, local video analysis of finger tapping and other tasks for clinicians. | Desktop tool, recorded video | No patient-facing longitudinal workflow, care team or language support |
| mPower (Sage Bionetworks) | Smartphone tapping, voice and walking tasks for research. | Smartphone | Retention: under 10% gave data on 5+ days; median 15 days for people with PD |
| CUE1 (Charco Neurotech) | Wearable vibrotactile cueing with an app for reminders and symptom tracking. | Purchased wearable | Benefit evidence is a single company pilot; users report mixed results |
| Parkinson's ON, My CareCycle, ParkCare | Medication scheduling and reminders; ON/OFF and caregiver logging in some. | Phone (several iPhone-only) | No movement measurement; reviewers found "limited insights" |
| Loud and Clear and similar | Real-time loudness feedback for voice practice. | Phone or tablet | Practice only; nothing reaches a care team |

## Gaps across the market

1. **Language and literacy.** No Parkinson's app in Urdu turned up. In one
   review, 30% of people with PD had low health literacy and 21% rated their
   technology skills as absent or poor.
2. **Hardware cost.** The cleared remote-monitoring apps need an Apple Watch
   and iPhone; the others need a dedicated wearable bought through a clinic.
3. **People stop using them.** mPower's numbers show most participants drop
   out within weeks.
4. **Recordings are not comparable.** Camera angle and setup change between
   recordings, and video tools have not solved that yet.
5. **Thin evidence everywhere.** A 2025 systematic review kept 13 of 1,027
   studies of commercial phone and wrist devices.
6. **Pakistan's care gap.** Older counts put neurologists at roughly one per
   1-2 million people, concentrated in a few cities; Balochistan had nine for
   about 13 million people (2017). Telemedicine is described as scarce.
7. **Medicine timing.** Paper ON/OFF diaries suffer from recall bias and poor
   compliance, yet ON/OFF state changes what a movement recording means.

## What ParkinSense-PK already does differently

- Urdu, Roman Urdu and English throughout, with right-to-left layout.
- Any phone camera or an uploaded clip, plus an Android app. No wearable.
- A quality check before anything is saved; no diagnosis claims.
- Medicine timing recorded with each visit (21 Oct).
- Runs on a clinic's own machine; recordings stay private.
- 3D replay, clinician caseload and written follow-up.

## What to add next

Ordered by value for this audience against effort in the current code.

> **26 Oct update:** items 1–8 are built in the web app, with three differences: reminders are
> on-screen only (no SMS, WhatsApp or Android notifications); read-aloud uses the browser's own
> voices instead of pre-recorded audio, and check-in voice notes are not built; caregiver help is
> recorded per visit and check-in rather than as separate logins. The Android app is unchanged. See
> [feature additions](feature-additions-2026-10-26.md). Items 9–12 remain open.

### Fits the current architecture

1. **Same-setup check for repeat recordings.** Store simple framing measures
   from the landmarks (body size in frame, position, side or front view) with
   each accepted recording. Warn when a repeat is set up differently from the
   patient's first one, and show a faint outline of the earlier framing on
   the live camera. This answers the camera-angle gap directly.
2. **Daily medicine reminders and an ON/OFF diary.** Extend per-visit timing
   to a daily log with reminders on the Android app. Optionally add SMS or
   WhatsApp reminders, which suit Pakistan. Timing and context only; never
   dosing advice.
3. **Caregiver accounts.** A family member, linked with the patient's
   consent, could enter check-ins and help with recordings. Tremor, low
   literacy and older age make this common in practice. The role and
   permission model already exist to build on.
4. **Voice-first Urdu.** Short pre-recorded Urdu audio for each instruction
   and voice notes for check-ins. Nothing goes to an outside speech service.
5. **Touchscreen tests in the Android app.** Spiral drawing (already the
   brand mark) and alternating-finger tapping, as in mPower. Phone-screen
   versions have only small pilot evidence, so label them unvalidated.
6. **Keeping people engaged.** A clinician-set weekly plan ("walk on Monday,
   voice on Thursday"), one small task per day, and gentle reminders.

### Next

7. **Voice loudness practice.** A practice mode with live loudness feedback,
   built on the existing audio pipeline and kept separate from measurements.
8. **Walking cue for freezing.** An adjustable metronome, optionally started
   from the patient's own measured cadence. Of the cue types, auditory cues
   have the most consistent support in small studies.
9. **Offline capture.** Record on the phone without a connection and upload
   later, plus a one-page PDF summary for clinic visits.
10. **Wearable import.** Steps and sleep from Android Health Connect, only
    after the basics above are in place.

### Needs clinical partners

11. **A local validation study.** Compare app measurements with clinician
    ratings across Pakistani clinics and phones, reported the way the 2023
    npj study reported intraclass correlation (ICC 0.74) for video
    bradykinesia. Every product here is short of evidence, so local data
    would be the strongest differentiator.
12. **Clinic pilots at scale.** The pilot module already tracks feasibility
    and patients' willingness to pay; run it with partner neurologists before
    any paid offering.

Check medical-device rules before making any measurement or monitoring claim.
Competitors with US clearance went through a 510(k) review.

## Sources

- [Use of smartphones and wrist-worn devices for motor symptoms in PD: systematic review (2025)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12196963/)
- [NIHR Health Technology Assessment of PD wearables (2024)](https://doaj.org/article/622770438be64f26883bc4f10dab7464)
- [NICE DG51 diagnostics assessment report (PKG)](https://www.nice.org.uk/guidance/dg51/documents/diagnostics-assessment-report)
- [PKG availability and cost claims, Parkinson's Resource Organization](https://www.parkinsonsresource.org/news/articles/pkg-watch-helps-in-managing-parkinsons-symptoms-and-lowering-patient-costs-global-kinetics-reports/)
- [StrivePD on the App Store](https://apps.apple.com/us/app/strivepd-parkinsons-assistant/id1275051699)
- [Apple Watch app cleared for Parkinson's monitoring (MDDI)](https://www.mddionline.com/digital-health/apple-watch-app-cleared-for-parkinson-s-monitoring)
- [StrivePD tracking, Davis Phinney Foundation](https://davisphinneyfoundation.org/blog/strivepd-tracking-parkinsons/)
- [NeuroRPM FDA clearance (Business Wire)](https://www.businesswire.com/news/home/20230323005557/en/NeuroRPM-Inc.-Announces-FDA-Clearance-for-NeuroRPM-the-AI-Powered-Remote-Monitoring-App-for-Parkinsons-Disease-on-Apple-Watch)
- [Apple Movement Disorder API (MobiHealthNews)](https://www.mobihealthnews.com/news/apple-adds-movement-disorder-api-plus-speech-hearing-and-vision-tests-researchkit-framework)
- [Machine Medicine company profile](https://www.joinef.com/companies/machine-medicine/)
- [Video-based bradykinesia rating across sites, npj Parkinson's Disease (2023)](https://openaccess.sgul.ac.uk/115157/1/s41531-023-00454-8.pdf)
- [FastEval Parkinsonism and camera-angle bias (2024)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10853559)
- [VisionMD, University of Florida (2025)](https://news.ufl.edu/2025/04/visionmd/)
- [mPower first data release and engagement (Fierce Biotech)](https://www.fiercebiotech.com/data-management/iphone-based-parkinson-s-study-shares-6-months-of-data-on-9-500-participants)
- [Remote smartphone monitoring of PD, retention analysis](https://stacks.cdc.gov/view/cdc/262143)
- [CUE1, MDS application repository](https://www.movementdisorders.org/MDS/Application-Repository/CUE1.htm)
- [A patient's account of CUE1](https://rorycellanjones.substack.com/p/the-parkinsons-buzzer-is-it-working)
- [Parkinson's ON, Parkinson's UK tech guide review](https://techguide.parkinsons.org.uk/catalogue/parkinsons-on/review)
- [My CareCycle: Parkinson's listing](https://appshunter.io/ios/app/my-carecycle-parkinsons/id6743374105)
- [Electronic symptom diary and recall bias, Frontiers in Neurology (2024)](https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2024.1476708/pdf)
- [Smartphone voice and speech training for PD, feasibility study (2025)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11888063/)
- [Loud and Clear on the App Store](https://apps.apple.com/us/app/-/id1491171131)
- [Smartphone spiral and tapping tests (2017)](https://doaj.org/article/1436fb37ea9d4f608d588dc89060bf8b)
- [Let's Draw: PD on smartphones (2020)](https://urn.fi/urn:nbn:fi-fe2020050725521)
- [Rhythmic cueing with Google Glass for gait in PD](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4893372/)
- [Three cueing devices for gait initiation](https://clok.uclan.ac.uk/12695)
- [Digital health literacy in PD, Journal of Parkinson's Disease (2024)](https://journals.sagepub.com/doi/10.3233/JPD-230229)
- [JPMA letter on PD care and telemedicine in Pakistan](https://jpma.org.pk/index.php/public_html/article/view/4611)
- [JPMA editorial on neurologist numbers](https://archive.jpma.org.pk/article-details/1988)
- [PD diagnoses in Pakistan (The News)](https://www.thenews.com.pk/print/196566-Up-to-100-Pakistanis-becoming-Parkinsons-disease-victims-daily)
- [Parkinson's disease care in Pakistan, BMJ Neurology Open (2026), record only](https://ecommons.aku.edu/pakistan_fhs_mc_med_neurol/284)
