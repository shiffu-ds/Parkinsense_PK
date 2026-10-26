"""Local, source-aware patient next steps for actual analysis outcomes.

This catalogue explains input and processing problems. It never interprets a
motion proxy as a disease finding. Clinical follow-up requires an explicit
self-report with its provenance; arbitrary error text is never echoed or used
to retrieve information online. Sources were reviewed on 2026-10-03.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ml.vision.tasks import TASKS
from .guidance_urdu import urdu_catalogue

Guidance = dict[str, Any]
SOURCE_REVIEW_DATE = "2026-10-03"
SOURCES = {
    "pose": {
        "title": "Google MediaPipe: pose landmark detection",
        "url": "https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python",
    },
    "hand": {
        "title": "Google MediaPipe: hand landmark detection",
        "url": "https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python",
    },
    "falls": {
        "title": "Parkinson's Foundation: Fall Prevention in Parkinson's",
        "url": "https://www.parkinson.org/sites/default/files/documents/Fall-Prevention-2024.pdf",
    },
    "freezing": {
        "title": "Parkinson's Foundation: Freezing and PD",
        "url": "https://www.parkinson.org/library/fact-sheets/freezing",
    },
}


def _language(value: str) -> tuple[str, str | None]:
    name = str(value).strip().lower().replace("_", " ")
    if name in {"roman urdu", "roman"}:
        return "roman urdu", None
    if name in {"english", "en"}:
        return "english", None
    if name in {"urdu", "ur"}:
        return "urdu", None
    # A real translation is required before claiming support for another script.
    notes = {
        "pashto": "Guidance is currently shown in English; a Pashto translation is not available.",
        "ps": "Guidance is currently shown in English; a Pashto translation is not available.",
        "mixed": "Guidance is currently shown in English for Mixed language selection.",
    }
    return "english", notes.get(name, "Guidance is currently available in English, Urdu and Roman Urdu.")


def _task_name(task: str | None, result: Mapping) -> str:
    name = str(task or result.get("task") or "").lower()
    aliases = {
        "voice_vowel": "vowel", "audio_vowel": "vowel",
        "voice_sentence": "sentence", "audio_sentence": "sentence",
        "voice_natural": "natural", "audio_natural": "natural",
        "voice": "natural", "nlp": "text",
    }
    return aliases.get(name, name)


def _catalogue(task: str) -> dict[str, Guidance]:
    spec = TASKS.get(task, {})
    audio = task in {"natural", "vowel", "sentence"}
    minimum = spec.get("min_seconds", 2 if task == "vowel" else 3)
    side = spec.get("side", "selected")
    roman_side = {"Left": "baen", "Right": "daen"}.get(side, "chunay huay")
    motion_steps = [
        "Read the selected task instructions and check that the required body parts stay in view.",
        "If safe and comfortable, repeat at your usual pace; do not force larger or faster movements to pass a recording check.",
        "If you cannot comfortably complete the task, leave it unsaved and tell your clinician rather than repeatedly attempting it.",
    ]
    roman_motion_steps = [
        "Chunay huay task ki hidayat parhein aur zaroori jism ke hissay camera mein rakhein.",
        "Sirf jab mehfooz aur aaram se ho sake, apni aam raftaar par dobara karein. Check pass karne ke liye harkat ko zabardasti bara ya tez na karein.",
        "Agar task aaram se nahi hota to usay save na karein aur bar bar koshish karne ke bajaye clinician ko batayein.",
    ]
    entries: dict[str, Guidance] = {}

    def add(code, kind, title, reason, steps, roman_title, roman_reason, roman_steps, source=None):
        entries[code] = {
            "code": code, "kind": kind, "title": title, "reason": reason, "steps": steps,
            "roman": {"title": roman_title, "reason": roman_reason, "steps": roman_steps},
            "source": SOURCES.get(source),
            "basis": "Local input/quality rule" if kind != "follow_up" else "Explicit patient self-report; educational follow-up",
        }

    add("duration_short", "recording", "Record a complete task", "This recording is shorter than the task's local minimum duration.",
        [f"Start a fresh recording and follow the selected task for at least {minimum} seconds.",
         "Keep the recording running through the complete task, then stop and review it.",
         "Analyze the new recording; repeat only if doing the task is safe and comfortable."],
        "Task ki mukammal recording karein", "Recording is task ke liye zaroori waqt se chhoti hai.",
        [f"Nayi recording shuru karein aur chunay huay task ko kam az kam {minimum} seconds tak karein.",
         "Task mukammal honay tak recording chalne dein, phir rok kar check karein.",
         "Nayi recording ka analysis karein; sirf jab mehfooz aur aaram se ho sake dobara karein."])
    add("duration_long", "recording", "Use a shorter video", "Movement analysis accepts videos up to 45 seconds.",
        ["Keep a complete task within a video of 45 seconds or less.",
         "Trim only spare time before and after the task; keep the actual task intact.",
         "Export the shorter video and upload it again."],
        "Video ka waqt kam karein", "Movement analysis mein 45 seconds tak ki video istemal hoti hai.",
        ["Mukammal task ko 45 seconds ya is se kam ki video mein rakhein.",
         "Sirf task se pehle aur baad ka fazool waqt trim karein; asal task ko mukammal rakhein.",
         "Chhoti video export kar ke dobara upload karein."])
    add("file_size", "recording", "Reduce the recording file size", "The recording exceeds the local processing size limit.",
        ["For video, use a complete clip no longer than 45 seconds and no larger than 100 MB; WAV audio must be 72 MB or less.",
         "Export at a sensible recording resolution without removing part of the task.",
         "Upload the exported file again; keep the original if you need it for review."],
        "Recording file ka size kam karein", "File local processing ki size limit se bari hai.",
        ["Video mukammal task ke saath 45 seconds aur 100 MB se zyada na ho; WAV audio 72 MB ya is se kam ho.",
         "Munāsib recording resolution par export karein aur task ka hissa na hatayein.",
         "Exported file dobara upload karein; review ke liye asal file apne paas rakhein."])
    add("empty_recording", "recording", "Check that a recording was saved", "A complete recording could not be found or opened.",
        ["Open the saved recording on your device and check that it plays.",
         "If it is empty, record the task again and wait for saving to finish.",
         "Select the complete saved file and analyze it again."],
        "Check karein ke recording save hui hai", "Mukammal recording mili nahi ya khul nahi saki.",
        ["Apne device par saved recording khol kar check karein ke woh chalti hai.",
         "Agar file khali hai to task dobara record karein aur saving mukammal honay dein.",
         "Mukammal saved file select kar ke dobara analysis karein."])
    add("video_format", "recording", "Export a readable video", "The file format or video data could not be read reliably.",
        ["Play the original video to check that it is complete.",
         "Export an MP4, MOV, AVI or MKV video using a standard video export; simply renaming the extension does not convert a file.",
         "Upload the exported video and try analysis again."],
        "Parhi ja sakne wali video export karein", "Video ka format ya data theek tarah parha nahi ja saka.",
        ["Asal video chala kar dekhein ke woh mukammal hai.",
         "Standard export se MP4, MOV, AVI ya MKV banayein. Sirf file ka naam ya extension badalne se format nahi badalta.",
         "Exported video upload kar ke analysis dobara karein."])
    add("audio_format", "recording", "Use a readable WAV recording", "The audio is not a valid, readable WAV recording.",
        ["Play the original audio and check that it contains the complete selected speech task.",
         "Use the app's microphone recorder or export a real WAV file; do not just rename an MP3 to WAV.",
         "Upload the WAV and analyze it again."],
        "Durust WAV recording istemal karein", "Audio durust WAV format mein nahi ya parhi nahi ja sakti.",
        ["Asal audio sun kar check karein ke chunay huay speech task ki mukammal recording hai.",
         "App ka microphone recorder istemal karein ya asal WAV export karein; MP3 ka sirf naam WAV na karein.",
         "WAV upload kar ke dobara analysis karein."])
    add("audio_sample_rate", "recording", "Export audio at a supported sample rate", "The local WAV decoder accepts sample rates from 8 to 192 kHz.",
        ["Export the original audio as a real WAV file at a standard sample rate such as 16, 44.1 or 48 kHz.",
         "Keep the complete speech task and its normal playback speed.",
         "Listen to the exported WAV, then upload it for analysis."],
        "Audio ko supported sample rate par export karein", "Local WAV decoder 8 se 192 kHz tak ki sample rates qabool karta hai.",
        ["Asal audio ko WAV mein 16, 44.1 ya 48 kHz jaisi standard sample rate par export karein.",
         "Mukammal speech task aur us ki aam playback speed rakhein.",
         "Exported WAV sun kar analysis ke liye upload karein."])
    add("frame_rate", "recording", "Check the camera frame rate", "The recording frame rate is outside the local task requirements.",
        ["Choose a standard camera video setting between 8 and 120 fps; finger tapping requires at least 15 fps.",
         "Keep the camera steady and avoid slow-motion or time-lapse exports.",
         "Record the selected task again and analyze the normal-speed video."],
        "Camera ki frame rate check karein", "Recording ki frame rate is task ki local zaroorat ke mutabiq nahi hai.",
        ["Camera mein 8 se 120 fps ki standard setting chunein; finger tapping ke liye kam az kam 15 fps chahiye.",
         "Camera seedha aur stable rakhein; slow-motion ya time-lapse export se parhez karein.",
         "Task dobara record kar ke normal-speed video ka analysis karein."])
    add("resolution", "recording", "Choose a usable recording resolution", "The video is too small or larger than the local 4K limit.",
        ["Choose a normal video setting such as 720p or 1080p.",
         "Keep both sides of the image at least 240 pixels and the full image no larger than 4K.",
         "Record or export the complete task again and upload the new file."],
        "Munāsib video resolution chunein", "Video bohat chhoti hai ya local 4K limit se bari hai.",
        ["720p ya 1080p jaisi aam video setting chunein.",
         "Tasveer ki dono taraf kam az kam 240 pixels hon aur poori video 4K se bari na ho.",
         "Mukammal task dobara record ya export kar ke nayi file upload karein."])
    add("body_view", "recording", "Keep the required body parts in view", "Required joints were hidden, outside the image, or not tracked clearly enough.",
        ["Place the camera on a stable surface and move it far enough away for the selected task.",
         "Check the task instructions: keep the required joints in the image throughout, without furniture or another person blocking them.",
         "Review the framing, then repeat only if safe and comfortable."],
        "Zaroori jism ke hissay camera mein rakhein", "Zaroori joints chhup gaye, tasveer se bahar thay ya wazeh track nahi huay.",
        ["Camera stable jagah par rakhein aur task ke mutabiq kaafi door set karein.",
         "Task ki hidayat check karein: zaroori joints poori recording mein nazar aayein aur furniture ya koi shakhs unhein na chhupaye.",
         "Framing check kar ke sirf jab mehfooz aur aaram se ho sake task dobara karein."], "pose")
    add("hand_view", "recording", "Check the complete selected hand", "The requested hand was not tracked clearly enough; framing or left/right selection may be the cause.",
        [f"Confirm that this task uses the {side.lower()} hand and that the video is not mirrored.",
         "Keep the wrist and all fingertips visible, with one selected hand clearly separated from the background.",
         "Use steady lighting and repeat the task at a comfortable pace."],
        "Chunay huay haath ko mukammal dikhayein", "Chuna hua haath wazeh track nahi hua; framing ya left/right selection ki wajah ho sakti hai.",
        [f"Check karein ke task {roman_side} haath ka hai aur video mirror nahi hui.",
         "Kalai aur tamam ungliyon ke siray nazar aayein; chuna hua haath background se wazeh alag ho.",
         "Roshni stable rakhein aur task apni aaram wali raftaar par dobara karein."], "hand")
    add("lighting", "recording", "Improve the lighting", "The local quality check found unsuitable lighting.",
        ["Use even light on your body or hand; avoid a bright window directly behind you.",
         "Check the camera preview for very dark or washed-out areas.",
         "Keep the lighting steady and record the complete task again."],
        "Roshni behtar karein", "Local quality check mein roshni munāsib nahi thi.",
        ["Jism ya haath par barabar roshni rakhein; apne bilkul peechay tez roshni wali khirki se parhez karein.",
         "Camera preview mein bohat andheray ya safed ho kar ghaib hissay check karein.",
         "Roshni stable rakh kar mukammal task dobara record karein."])
    add("blur", "recording", "Make the image clearer", "The recording was too blurred or featureless for reliable tracking.",
        ["Clean the camera lens and focus on the body or hand required for this task.",
         "Support the camera on a stable surface and avoid moving it during recording.",
         "Check that the preview is sharp, then record the task again."],
        "Tasveer ko wazeh karein", "Recording bohat dhundli thi ya tracking ke liye wazeh tafseel nahi thi.",
        ["Camera lens saaf karein aur is task ke jism ya haath par focus karein.",
         "Camera stable surface par rakhein aur recording ke dauran na hilayein.",
         "Preview wazeh honay par task dobara record karein."])
    add("landmarks_lost", "recording", "Help the camera track the task", "Too few usable landmark frames were available for a reliable measurement.",
        ["Use clear, even lighting and a stable camera.",
         "Keep the full selected hand or required body joints visible for the complete task.",
         f"Record at least {minimum} seconds; if tracking still fails, use a clearer recording or ask the clinic for help with setup."],
        "Camera ko task track karne mein madad dein", "Bharosemand measurement ke liye kaafi usable landmark frames nahi milay.",
        ["Wazeh aur barabar roshni ke saath camera stable rakhein.",
         "Mukammal task mein poora chuna hua haath ya zaroori body joints nazar aayein.",
         f"Kam az kam {minimum} seconds record karein; tracking phir bhi na ho to behtar recording ya setup ke liye clinic se madad lein."])
    add("orientation", "recording", "Keep the video upright", "The local orientation check could not confirm an upright recording.",
        ["Check that the saved video plays upright, rather than sideways or upside down.",
         "Rotate and export it correctly, or record again with the camera upright.",
         "Keep all required joints visible and try analysis again."],
        "Video seedhi rakhein", "Local check mein upright recording ki tasdeeq nahi ho saki.",
        ["Saved video chala kar check karein ke woh seedhi hai, side par ya ulti nahi.",
         "Sahi rotate kar ke export karein ya camera seedha rakh kar dobara record karein.",
         "Zaroori joints dikhate huay dobara analysis karein."])
    add("stream_gaps", "recording", "Use a steadier camera connection", "The live recording had gaps or too few unique camera frames; repeated frames cannot recover missed movement.",
        ["Stop the current capture and close other apps using the camera or heavy processing.",
         "Use a stable local connection and check that the camera preview moves smoothly.",
         "Start a fresh capture; if gaps persist, record a normal-speed video on your device and upload it instead."],
        "Camera connection ko stable karein", "Live recording mein gaps ya bohat kam asal camera frames thay; repeated frames chhuti hui harkat wapas nahi la sakte.",
        ["Maujooda capture rok dein aur camera ya heavy processing istemal karne wali dusri apps band karein.",
         "Stable local connection istemal karein aur dekhein ke camera preview smoothly chal raha hai.",
         "Naya capture shuru karein; gaps rahain to device par normal-speed video record kar ke upload karein."])
    add("occlusion", "recording", "Avoid losing the tracked body or hand", "Required landmarks disappeared for part of the recording.",
        ["Keep the required joints visible and avoid moving outside the camera frame.",
         "Adjust the camera position so furniture, clothing or the other hand does not block the tracked area.",
         "Record a complete, safely performed task again."],
        "Tracked jism ya haath ko nazar se ghaib na honay dein", "Recording ke kuch hissay mein zaroori landmarks nazar nahi aaye.",
        ["Zaroori joints nazar mein rakhein aur camera frame se bahar na jayein.",
         "Camera aise set karein ke furniture, kapray ya dusra haath tracked jagah na chhupaye.",
         "Mehfooz tareeqay se mukammal task dobara record karein."])
    add("movement_not_visible", "recording", "Check that the selected task is captured", "The selected task's movement could not be measured clearly. This recording check is not a clinical finding.",
        motion_steps, "Check karein ke chuna hua task record hua hai", "Chunay huay task ki harkat wazeh measure nahi hui. Yeh recording check hai, clinical finding nahi.", roman_motion_steps)
    add("silence", "recording", "Check the microphone and voice level", "The audio was silent, too quiet, or had too little usable signal.",
        ["Check microphone permission and select the microphone you intend to use.",
         "Record in a quiet room, with the microphone a comfortable, consistent distance away; speak at your usual voice level.",
         f"Play back a complete recording of at least {minimum if audio else 3} seconds and analyze it again; do not strain or shout."],
        "Microphone aur awaz ka level check karein", "Audio khamosh, bohat halki thi ya usable signal ka waqt bohat kam tha.",
        ["Microphone permission aur chuna hua microphone check karein.",
         "Pur-sukoon kamray mein microphone ko aaram deh, ek jaisay faslay par rakh kar apni aam awaz mein bolein.",
         f"Kam az kam {minimum if audio else 3} seconds ki mukammal recording sun kar dobara analysis karein; gala zor laga kar na bolein."])
    add("clipping", "recording", "Reduce microphone overload", "The audio signal was clipped by the recording equipment.",
        ["Reduce the microphone's input gain if a gain control is available.",
         "Move the microphone slightly farther away and use your usual comfortable voice level.",
         "Record and listen again before analyzing; keep this setup consistent for future comparisons."],
        "Microphone ka overload kam karein", "Recording equipment ne audio signal ko clip kar diya.",
        ["Agar input gain control hai to microphone gain kam karein.",
         "Microphone ko thora door rakhein aur apni aam aaram wali awaz istemal karein.",
         "Dobara record kar ke pehle sunein, phir analysis karein; aglay comparisons ke liye yahi setup rakhein."])
    add("adl_complete", "recording", "Complete the daily activities answers", "Each of the nine activities needs an explicit answer from 0 to 4; an unanswered item is not a 'no difficulty' response.",
        ["Review all nine activities and select the answer that best matches your own experience.",
         "Use 'No difficulty' only when that is your answer; leave no item unanswered before submitting.",
         "If you need help understanding an item, ask a care partner or clinician, then submit your own answers."],
        "Rozmarra kaamon ke jawab mukammal karein", "Nau kaamon mein har aik ka 0 se 4 tak wazeh jawab chahiye; khali jawab ka matlab 'koi mushkil nahi' nahi hai.",
        ["Nau kaamon ko check kar ke apne tajurbe ke mutabiq jawab chunein.",
         "'No difficulty' sirf tab chunein jab yeh aap ka asal jawab ho; submit se pehle koi jawab khali na ho.",
         "Koi sawal samajh na aaye to care partner ya clinician se samjhein, phir apne jawab submit karein."])
    add("adl_note_length", "recording", "Shorten the daily-life note", "The optional note must be text no longer than 2,000 characters.",
        ["Keep the main daily-life difficulty in a short note.",
         "Remove repeated text so the note stays within 2,000 characters.",
         "Keep all activity answers unchanged and submit again."],
        "Rozmarra zindagi ka note chhota karein", "Optional note text ho aur 2,000 characters se zyada na ho.",
        ["Asal rozmarra mushkil ko chhotay note mein rakhein.",
         "Dohrayi hui baat hata kar note ko 2,000 characters ke andar rakhein.",
         "Kaamon ke jawab waise hi rakh kar dobara submit karein."])
    add("transcript_required", "recording", "Enter and review the transcript", "Text analysis requires a reviewed transcript or self-report between 3 and 5,000 characters.",
        ["Enter what was actually said, or write your own description of daily-life difficulty.",
         "Review the text for accuracy, including words such as 'no' or 'not' that change the meaning.",
         "Keep it between 3 and 5,000 characters, choose the language used, and analyze the reviewed text."],
        "Transcript likhein aur review karein", "Text analysis ke liye 3 se 5,000 characters ka reviewed transcript ya apna self-report chahiye.",
        ["Jo asal mein kaha gaya woh likhein, ya apni rozmarra mushkil apne alfaaz mein batayein.",
         "Text ki durusti check karein, khaas taur par 'nahi' jaisay alfaaz jo matlab badal dete hain.",
         "Text 3 se 5,000 characters rakhein, istemal hui zuban chunein aur reviewed text ka analysis karein."])
    add("model_unavailable", "processing", "The movement service needs setup", "The landmark model is missing or could not be loaded. This is a system setup issue, not a problem with your movement.",
        ["Keep the original recording; recording it again will not install the missing model.",
         "Ask the app administrator to install or check the required landmark model and its dependencies.",
         "When the service is ready, analyze the saved recording again."],
        "Movement service ka setup zaroori hai", "Landmark model missing hai ya load nahi hua. Yeh system setup ka masla hai, aap ki harkat ka nahi.",
        ["Asal recording apne paas rakhein; dobara recording se missing model install nahi hota.",
         "App administrator se zaroori landmark model aur dependencies install ya check karwayein.",
         "Service tayyar honay par saved recording ka analysis dobara karein."], "hand" if spec.get("kind") == "hand" else "pose")
    add("audio_dependency", "processing", "The audio service needs setup", "The local audio decoder is unavailable.",
        ["Keep the original WAV recording.", "Ask the app administrator to check the audio decoder installation.",
         "Try the saved recording again after the service is available."],
        "Audio service ka setup zaroori hai", "Local audio decoder dastiyab nahi hai.",
        ["Asal WAV recording apne paas rakhein.", "App administrator se audio decoder ki installation check karwayein.",
         "Service dastiyab honay par saved recording dobara try karein."])
    add("asr_unconfigured", "processing", "Add a reviewed transcript if needed", "Automatic transcription is not configured. Acoustic analysis can still be usable; this does not indicate a voice problem.",
        ["Listen to the saved audio if you want to prepare a text summary.",
         "Type and review the words actually spoken in the transcript section.",
         "Analyze that reviewed text separately; acoustic measurements do not require an automatic transcript."],
        "Zaroorat ho to reviewed transcript likhein", "Automatic transcription configure nahi hai. Acoustic analysis phir bhi usable ho sakta hai; is ka matlab awaz ka masla nahi.",
        ["Text summary banana ho to saved audio sunein.",
         "Transcript section mein asal bolay huay alfaaz likh kar review karein.",
         "Reviewed text ka alag analysis karein; acoustic measurements ke liye automatic transcript zaroori nahi."])
    add("analysis_busy", "processing", "Wait for the current analysis", "Another movement recording is being processed.",
        ["Wait until the current analysis finishes.", "Keep the selected recording ready; repeated clicks do not speed up processing.",
         "Try analyzing your recording again when the service is free."],
        "Maujooda analysis mukammal honay dein", "Dusri movement recording abhi process ho rahi hai.",
        ["Maujooda analysis mukammal honay ka intezar karein.", "Chuni hui recording tayyar rakhein; bar bar click se processing tez nahi hoti.",
         "Service free honay par apni recording ka analysis dobara karein."])
    add("storage_unavailable", "processing", "The recording could not be saved", "The local recording storage was unavailable.",
        ["Stop the capture and keep any original file already saved on your device.",
         "Ask the app administrator to check storage space and recording permissions.",
         "Start a fresh recording only after storage is available, or upload a complete existing file."],
        "Recording save nahi ho saki", "Local recording storage dastiyab nahi thi.",
        ["Capture rok dein aur device par pehle se saved asal file apne paas rakhein.",
         "App administrator se storage space aur recording permissions check karwayein.",
         "Storage dastiyab honay par nayi recording shuru karein ya mukammal existing file upload karein."])
    add("task_selection", "processing", "Choose a supported task", "This analysis needs a supported task selection.",
        ["Return to the module and select one of the listed tasks.", "Check that the recording matches that task.",
         "Try analysis again with the supported selection."],
        "Dastiyab task chunein", "Is analysis ke liye supported task selection zaroori hai.",
        ["Module mein wapas ja kar list se task chunein.", "Check karein ke recording usi task ki hai.",
         "Supported selection ke saath dobara analysis karein."])
    add("touch_incomplete", "recording", "Complete the touch test", "The touch test was not completed in a way that can be measured.",
        ["Rest the phone on a table, or hold it steady in your other hand.",
         "For the spiral, trace the grey guide from the centre outwards without rushing. For tapping, tap the two circles one after the other for the full 20 seconds.",
         "Clear the drawing area and try again only if it is comfortable; tell your care team if the test is difficult."],
        "Touch test mukammal karein", "Touch test aise mukammal nahi hua ke us ki pemaish ho sake.",
        ["Phone ko mez par rakhein, ya doosre haath mein mazbooti se pakrein.",
         "Spiral mein grey lakeer par beech se bahar ki taraf aaram se chalein. Tapping mein dono daairon ko baari baari poore 20 seconds tak chhoein.",
         "Sirf aaram se ho to drawing saaf kar ke dobara karein; test mushkil ho to apni team ko batayein."])
    add("analysis_retry", "processing", "Try the analysis again", "The analysis could not finish. A technical interruption does not establish a movement or speech problem.",
        ["Keep the original recording or answers and check that they are complete.",
         "Try the same analysis once more after the service is available.",
         "If it fails again, ask the app administrator for help with this module; do not repeat a physically difficult task just to fix a technical error."],
        "Analysis dobara try karein", "Analysis mukammal nahi hua. Technical rukawat se movement ya speech ka masla sabit nahi hota.",
        ["Asal recording ya jawab apne paas rakhein aur un ki mukammal honay ki tasdeeq karein.",
         "Service dastiyab honay par usi analysis ko aik martaba dobara try karein.",
         "Phir bhi fail ho to is module ke liye app administrator se madad lein; technical maslay ke liye mushkil physical task bar bar na karein."])
    add("recording_review", "recording", "Review the task before trying again", "The recording did not pass a local quality check. Its measurements should not be interpreted as a clinical result.",
        ["Review the selected task instructions and the saved recording.",
         "Check camera or microphone setup and whether the complete task was captured.",
         "If safe and comfortable, record again; if the cause is unclear, ask the clinic to help review the recording."],
        "Dobara koshish se pehle task review karein", "Recording local quality check mein pass nahi hui. Is ki measurements ko clinical result na samjhein.",
        ["Chunay huay task ki hidayat aur saved recording review karein.",
         "Camera ya microphone setup aur mukammal task record honay ko check karein.",
         "Mehfooz aur aaram se ho to dobara record karein; wajah wazeh na ho to recording review mein clinic se madad lein."])
    add("self_reported_falls", "follow_up", "Discuss the reported fall with your clinician", "Falls were explicitly reported in the reviewed text. This is a self-report follow-up, not a fall detected by the camera.",
        ["Tell your clinician about the fall and any injury; seek local medical help if you are injured or need help after a fall.",
         "Note when and where it happened and what you were doing, so your care team can review it.",
         "Ask about a personalized fall-prevention and home-safety review before attempting tasks you feel unsafe doing."],
        "Report kiye gaye girne ka clinician se zikr karein", "Reviewed text mein girne ka wazeh zikr kiya gaya. Yeh self-report ka follow-up hai, camera ne fall detect nahi kiya.",
        ["Clinician ko girne aur kisi chot ka batayein; chot ho ya girne ke baad madad chahiye to local medical madad lein.",
         "Waqt, jagah aur us waqt jo kaam kar rahe thay note karein taa-ke care team review kar sake.",
         "Jo task unsafe lage usay karne se pehle apni fall-prevention aur ghar ki safety review ke bare mein poochein."], "falls")
    add("self_reported_freezing", "follow_up", "Discuss the reported freezing with your clinician", "Freezing was explicitly reported in the reviewed text. The app has not confirmed a freezing episode or its cause.",
        ["Tell your clinician when the reported episodes happen and what situations seem to bring them on.",
         "If movement stops during a task, pause; a care partner should not rush or push you to move.",
         "Ask your clinician whether a Parkinson's-experienced physical or occupational therapist can help with safe, personalized strategies."],
        "Report kiye gaye freezing ka clinician se zikr karein", "Reviewed text mein freezing ka wazeh zikr hai. App ne episode ya us ki wajah confirm nahi ki.",
        ["Clinician ko batayein ke report kiye gaye episodes kab aur kin halat mein hotay hain.",
         "Task ke dauran harkat ruk jaye to pause karein; care partner jaldi ya dhakka de kar na chalaye.",
         "Clinician se poochein ke Parkinson's ka tajurba rakhne wala physical ya occupational therapist mehfooz, aap ke mutabiq strategies mein madad de sakta hai."], "freezing")
    urdu = urdu_catalogue(minimum=minimum, side=side, audio=audio)
    for code, entry in entries.items():
        entry["urdu"] = urdu[code]
    return entries


def _classify(message: str, task: str) -> str | None:
    """Map only known local failure wording; never return caller-supplied prose."""
    text = message.lower()
    rules = [
        ("model_unavailable", ("landmark model is missing", "landmark model could not be loaded")),
        ("audio_dependency", ("soundfile audio dependency",)),
        ("asr_unconfigured", ("no local asr model configured", "automatic transcription is not configured")),
        ("analysis_busy", ("another movement recording is being analyzed",)),
        ("storage_unavailable", ("could not open local recording file",)),
        ("task_selection", ("supported movement task", "audio task must be", "supported touch test", "test before drawing", "test before tapping")),
        ("touch_incomplete", ("the touch test needs", "touch test data could not be read")),
        ("adl_complete", ("all nine adl", "whole number from 0 to 4", "adl responses must be an object", "unknown adl item")),
        ("adl_note_length", ("other daily-life difficulty must be text",)),
        ("transcript_required", ("reviewed transcript or self-report between 3",)),
        ("duration_short", ("record at least",)),
        ("duration_long", ("trim the video to 45 seconds",)),
        ("file_size", ("exceeds 100 mb", "exceeds the 72 mb",)),
        ("empty_recording", ("video is empty or missing", "audio file is missing or empty", "recording is missing or empty", "no recorded frames",)),
        ("frame_rate", ("valid frame rate", "at least 15 fps",)),
        ("resolution", ("at least 240 pixels",)),
        ("hand_view", ("complete selected hand visible", "requested left/right side", "wrong hand")),
        ("body_view", ("all required joints visible",)),
        ("landmarks_lost", ("too few usable landmark", "too few visible landmark", "visible for too little")),
        ("lighting", ("lighting is unsuitable",)),
        ("blur", ("very blurred or featureless",)),
        ("orientation", ("orientation appears incorrect",)),
        ("stream_gaps", ("frame gaps", "too few unique camera frames", "camera connection gaps during recording",)),
        ("occlusion", ("landmarks were lost for more than a second",)),
        ("movement_not_visible", ("little wrist travel", "little opening/closing", "fewer than two distinct movement cycles", "little stepping", "clear turning movement was not visible", "clear knee extension transition was not visible", "little reaching")),
        ("silence", ("silent or too quiet", "less than one second of usable signal",)),
        ("clipping", ("recording is clipping",)),
        ("audio_sample_rate", ("unsupported sample rate",)),
        ("audio_format", ("use a wav recording", "cannot decode wav recording", "invalid audio samples",)),
        ("video_format", ("mp4, mov, avi or mkv", "file content does not match", "video cannot be decoded", "duration could not be verified", "decoder could not read the complete recording")),
        ("analysis_retry", ("movement analysis failed", "live landmarks are unavailable",)),
    ]
    for code, phrases in rules:
        if any(phrase in text for phrase in phrases):
            return code
    return None


def _reported_followups(result: Mapping, task: str) -> list[str]:
    if task != "text":
        return []
    provenance = result.get("provenance", {})
    if not isinstance(provenance, Mapping) or not isinstance(provenance.get("source"), str) or provenance.get("source") not in {
        "manual_transcript_or_self_report", "patient_self_report_reviewed_transcript",
    }:
        return []
    quality = result.get("quality", {})
    if not isinstance(quality, Mapping) or quality.get("accepted") is not True or result.get("status") not in ("accepted", "completed", "ACCEPT") or quality.get("decision") in ("REPEAT", "REJECT"):
        return []
    flags = result.get("review_flags", [])
    flags = flags if isinstance(flags, list) else []
    entities = result.get("entities", [])
    entities = entities if isinstance(entities, list) else []
    out = []
    for domain in ("falls", "freezing"):
        # Do not accept an arbitrary sentence containing a keyword or infer a
        # medical problem from a count, proxy, mentioned-only or negated term.
        explicit = any(
            isinstance(entity, Mapping)
            and entity.get("activity") == domain
            and entity.get("status") == "reported_difficulty"
            and entity.get("provenance") == "patient_self_report_reviewed_transcript"
            for entity in entities
        )
        known_flag = f"Self-reported {domain} needs clinician review." in flags
        contradictory = any(
            isinstance(entity, Mapping)
            and entity.get("activity") == domain
            and entity.get("status") in ("denied_or_negated", "mentioned_only")
            for entity in entities
        )
        if explicit or (known_flag and not contradictory):
            out.append(f"self_reported_{domain}")
    return out


def build_guidance(result: dict | None = None, task: str | None = None, *, error: Any = None,
                   language: str = "English") -> list[Guidance]:
    """Return numbered-step data, without mutating results or making diagnoses.

    ``quality.issue_codes`` reproduces earlier classified technical failures
    across reruns. Only fixed recording/processing codes are trusted there;
    clinical follow-up always requires its explicit self-report evidence.
    """
    data = result if isinstance(result, Mapping) else {}
    task_name = _task_name(task, data)
    catalogue = _catalogue(task_name)
    lang, note = _language(language)
    quality = data.get("quality", {})
    quality = quality if isinstance(quality, Mapping) else {}
    rejected = quality.get("accepted") is False or quality.get("decision") in ("REPEAT", "REJECT") or data.get("status") in ("repeat", "rejected", "unavailable", "failed", "error")
    codes: list[str] = []

    def remember(code):
        if code is not None and code in catalogue and code not in codes:
            codes.append(code)

    prior_codes = quality.get("issue_codes", [])
    if isinstance(prior_codes, list):
        for code in prior_codes:
            if isinstance(code, str) and code in catalogue and catalogue[code]["kind"] != "follow_up":
                remember(code)
    if error is not None:
        remember(_classify(str(error), task_name) or ("recording_review" if rejected else "analysis_retry"))
    issues = quality.get("issues", [])
    messages = quality.get("messages", [])
    for values, fault_channel in ((issues, True), (messages, rejected)):
        if not isinstance(values, list):
            continue
        for message in values:
            if not isinstance(message, str):
                continue
            code = _classify(message, task_name)
            if code:
                remember(code)
            elif fault_channel and not prior_codes:
                remember("analysis_retry" if data.get("status") == "unavailable" else "recording_review")
    asr = data.get("asr", {})
    if isinstance(asr, Mapping) and asr.get("status") == "unavailable" and not rejected:
        remember("asr_unconfigured")
    if rejected and not codes:
        remember("analysis_retry" if data.get("status") == "unavailable" else "recording_review")
    for code in _reported_followups(data, task_name):
        remember(code)

    output = []
    for code in codes:
        entry = catalogue[code]
        wording = entry["roman"] if lang == "roman urdu" else entry["urdu"] if lang == "urdu" else entry
        source = entry["source"]
        output.append({
            "code": code, "kind": entry["kind"], "title": wording["title"],
            "reason": wording["reason"], "steps": list(wording["steps"]),
            "source": dict(source) if source else None, "basis": entry["basis"],
            "source_reviewed_on": SOURCE_REVIEW_DATE if source else None,
            "language": lang, "translation_note": note,
        })
    return output
