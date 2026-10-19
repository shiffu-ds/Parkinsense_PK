# Public real-video check — 15 October 2026

Two complete public recordings were analyzed locally through `ml.vision.pipeline.analyze_video`, the same entry point used for saved upload/live movement analysis. A generated dark clip was the negative control. No patient database, patient identity or clinical record was used. This exercise covers gait, the offline use of the advanced overlay renderer, 3D replay, statistical graphs and generated reports. It does not test browser camera capture, other task modules or diagnostic accuracy.

## Observed outcomes

| Input | Decoded video | Usable samples | Decision | Result |
|---|---|---|---|---|
| Shoreline walking | 533 frames, 17.77 s, 1280×720, 30 fps | 178/178 (100%) | ACCEPT | Continuous required-joint tracking; 178 world-coordinate observations, 90-frame interactive replay, statistical curves and report generated. |
| Treadmill with occlusion | 1,346 frames, 44.91 s, 640×480, 29.97 fps | 343/449 (76.39%) | REPEAT | A 1.1011-second landmark gap correctly prevents measurements; features and metadata remain empty. |
| Generated dark control | 150 frames, 6 s, 640×480, 25 fps | 0/75 | REPEAT | No pose, features or available 3D measurement; recording guidance generated. |

“100%” above is the fraction of sampled frames meeting this implementation's required-joint visibility rules. It is not measurement or diagnostic accuracy. The shoreline clip includes turns, pauses, waves, sloping sand and camera movement. It is useful software test footage, not a standardized clinical walking trial. There are no reference measurements or clinician labels.

The advanced camera overlay was generated from the same `draw_live_overlay` function used during live capture. It projects observed joints onto the actual recording and uses estimated world depth for styling. The most recent observation is used for at most 0.12 seconds; no interpolation or missing joints are invented. Six source/overlay pairs were inspected across the clip. The separate 3D viewer uses estimated hip-centered world XYZ; it does not recover travel distance, a room-coordinate route or calibrated anatomy.

## Confirmed defect and correction

The original shoreline result supplied an arm-swing proxy even though the left wrist had visibility below 0.5 in 145/178 observations (81.5%). Gait's required-joint gate does not include wrists, so accepting the recording did not establish arm-measurement reliability.

`ml/vision/features.py` now requires at least 20 observations and 70% usable samples **for each arm**. Each included wrist and corresponding shoulder must be finite, in the image and have visibility at least 0.5. The range uses only usable observations and their corresponding body scale. If either arm lacks sufficient evidence, the combined metric and its metadata are omitted. A genuine visible zero remains zero.

`ml/vision/pipeline.py` adds an explicit unavailability explanation to the analysis display and generated report. Gait now carries `mediapipe_tasks_gait_proxies_v2`, keeping incompatible earlier method results out of automatic baseline comparisons. Other movement tasks retain their existing version. Existing saved records are not rewritten.

The corrected full-video analysis reproduced every original landmark, quality value, curve and retained feature exactly. The unsupported arm-swing metric was removed. The corrected report visibly explains its absence. Overlay video was reused only after exact landmark/timestamp equality was asserted. The original v1 same-file rerun also produced identical features and quality; this is computational consistency, not repeatability across separate recordings.

## Verification

- 50 feature/vision tests passed; one optional model smoke test was skipped in that suite. Actual MediaPipe inference was run on the public clips separately.
- 63 report, statistical graph and measurement-validation tests passed.
- Ruff and `git diff --check` passed for the code changes.
- All 36 recorded result checks passed across the three cases: finite JSON, consistent frame counts, ordered timestamps, bounded 3D replay, rejected-value withholding, overlay non-mutation and the corrected report explanation.
- Source and overlay videos played in the browser. The 3D Play control advanced from 0.0 s to 17.7 s; the WebGL avatar rendered from the observed coordinates.

An initial background verification attempt ended with exit 143 after the corrected raw result/report were written. It was not counted as a completed suite. The 63-test suite was rerun successfully. Saved corrected results were checked explicitly, and matching previously rendered visual assets were reused; no inference output was fabricated to complete the review.

## Sources and transformations

1. **“Walking in the sands” — sgu18ify**, [Wikimedia Commons source](https://commons.wikimedia.org/wiki/File:Walking_in_the_sands.webm), [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). Source SHA256 `f0d21f5f6e085cb8f613b02803b99c4b01a2d002300872760df2a8d5580114ef`. Converted from WebM to H.264 MP4, audio removed, full 533 video frames retained at the original 30 fps and 1280×720. No trim or speed change. Converted SHA256 `ef551b21d187ccdb1832061c7401d61fcb5c4e131e0fc74ea4cbefe74d01772b`.
2. **Yoon J, Park H, Damiano D (2012), walking-with-treadmill-controller supplement**, [Wikimedia Commons source](https://commons.wikimedia.org/wiki/File:A-novel-walking-speed-estimation-scheme-and-its-application-to-treadmill-control-for-gait-1743-0003-9-62-S1.ogv), [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/). Downloaded bytes and SHA1 exactly match Commons (`04b975bbdeb677b11d90e8bbfccd1104a0eef67a`). Converted from Ogg to MP4; original coded 720×480 with SAR 8:9 normalized to intended square-pixel 640×480. All video frames and timing preserved. The audio/container duration differs slightly from decoded video duration.

Depth-styled overlays and comparison snapshots were added to these licensed recordings. No creator endorsement is implied. Earlier street/park candidates were inspected but **not analyzed**; they are excluded from all result counts.

## Reproduce and inspect

Local artifacts are in `artifacts/public-video-check-2026-10-15/` (ignored by Git):

- `index.html`: review page with source/overlay video, interactive 3D replay and report links.
- `sources.json`: attribution, URLs, hashes and exact conversion commands.
- `sands/`, `treadmill/`, `dark-control/`: raw results, summaries, reports and visualization exports.
- `sands-before-wrist-fix/`: original evidence, explicitly superseded for the arm-swing metric.
- `run_check.py`: reproducible runner using installed application code and models.

From the repository root, rerun into a fresh name:

```sh
.venv/bin/python artifacts/public-video-check-2026-10-15/run_check.py \
  artifacts/public-video-check-2026-10-15/sands-walking.mp4 sands-rerun --repeat
```

Independent reference measurements, standardized repeat recordings and representative participant/camera/lighting coverage remain necessary before clinical accuracy or real-world repeatability can be claimed.
