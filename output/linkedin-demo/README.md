# ParkinSense PK — LinkedIn testing demo

## Deliverables
- **Use `ParkinSense-PK-Voice-Captions.mp4` for posting.** Revised 92-second video; 1080 × 1350; 24 fps; H.264/yuv420p plus AAC English narration; fast-start MP4. Larger, synchronized English captions are permanently burned into the frames, so they remain visible even with subtitles disabled.
- `ParkinSense-PK-Testing-Demo.mp4`: the earlier silent version, retained as the visual source for the revision.
- `ParkinSense-PK-cover.jpg`: matching cover image.
- `ParkinSense-PK-Voice-Captions.srt`: synchronized subtitles for the revised video. They are optional because the video already displays them. `ParkinSense-PK-English.srt` belongs to the earlier version.
- `LinkedIn-post.txt`: proposed post text, including credits. Copy/edit before posting; nothing has been published.
- `storyboard.json`: scene timings and captions.

## What the film shows
This is an edited, data-driven demonstration of measured outputs, not a screen recording of app interactions. Its graphics were composed for the film and are not a claim about the exact app interface. Three actual pipeline analyses were rerun for this film: indoor gait, left-hand finger tapping and a 30-second reading-audio excerpt. Their complete JSON outputs and source hashes are in `evidence/`.

The 463-test figure is the archived 19 October 2026 verification result, not a newly rerun full suite. The video distinguishes software correctness from clinical accuracy and discloses wrong-task acceptance. Six assessment sections are described, but matched real-recording examples in this film cover gait, hand and voice only. There is no claim that all six sections have independent clinical validation.

The 3D visuals use actual saved MediaPipe world landmarks, interpolated for playback, with a gently rotating view. Replays loop at source-time speed. These are model-local estimated coordinates, not a calibrated body scan or global walking trajectory. The waveform uses real audio samples; no participant speech or original patient image is played in the film. No private account records or credentials appear.

## Source attribution and transformations
All three source catalogues identify CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

1. Eva Schaeffer, Gerd Linke and Daniela Berg (2016). “Cueing for Levodopa-Induced Dyskinesias in Parkinson’s Disease,” Video S1. https://doi.org/10.3389/fneur.2016.00237
   - Source excerpt: 31.5–37.5 seconds, indoor visual cue training from the published clinical case.
   - Preparation: original excerpt transcoded to H.264; audio removed. For this film, only extracted landmarks and numerical measurements are visualized; new perspective projection, interpolation and visual styling were applied. Original identifiable patient footage is not included.
2. Narongrit Kasemsap (2025). “Example Video Finger tapping for bradykinesia detection.” https://figshare.com/articles/dataset/Example_Video_Finger_tapping_for_bradykinesia_detection/28930706
   - Full 11.8-second source, left-hand analysis. Participant diagnosis is not stated by the source.
   - For this film, derived landmarks and distance ratios are re-rendered with interpolation and camera rotation; original footage is not included.
3. Hagen Jaeger, Dhaval Trivedi and Michael Stadtschnitzer. MDVR-KCL. https://doi.org/10.5281/zenodo.2867216
   - ReadText/PD-labelled recording; fixed 30–60-second excerpt at the original sample rate, PCM16. The displayed waveform is a peak envelope of that excerpt. Features come from the actual audio pipeline, which applies its documented preprocessing.
   - No source audio is played. Dataset label is not an app diagnosis.

No source author, participant or institution is implied to endorse this project. Keep credits with the published video. The source licence does not imply rights to make medical or endorsement claims.

## Reproducibility
Run from the repository root with its existing virtual environment:

```sh
.venv/bin/python output/linkedin-demo/evidence/rerun_samples.py
.venv/bin/python output/linkedin-demo/build_video.py
```

The render requires the locally retained source media, audit evidence, Pillow, NumPy, SoundFile, Lato fonts and FFmpeg. It does not connect to or modify the running app, patient database or LinkedIn.

## Voice and caption revision
English narration is synthesized with the standard en-US-AriaNeural voice through edge-tts. It is a narrator, not a patient recording or a clinician endorsement. Only the public demo script was sent for speech synthesis. The audio is aligned scene by scene, with small tempo adjustments where needed, then normalized to a target of -16 LUFS and encoded to AAC.

Captions use word-boundary timing from the generated speech, grouped into short phrases, with a maximum of two lines. Their font is 44 pixels on the 1080 × 1350 canvas, increased from the earlier 28-pixel paragraphs. The text is burned into a high-contrast panel; no player subtitle support is required.

To reproduce after the original visual MP4 exists:

```sh
output/linkedin-demo/.voice-venv/bin/python output/linkedin-demo/add_voice.py
.venv/bin/python output/linkedin-demo/compose_voice_captions.py
```

The synthesis environment requires `edge-tts` and network access for uncached phrases. The composition step uses the already installed project image/audio libraries and FFmpeg.
