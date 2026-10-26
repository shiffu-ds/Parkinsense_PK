"""Locally written patient instructions, with stable task and response IDs.

These translations are product copy, not a validated questionnaire translation.
No external font, translation service or patient data is needed to render them.
"""

from html import escape

import streamlit as st

SUPPORTED_LANGUAGES = ("English", "Urdu", "Roman Urdu")

# Every row contains English, Urdu script and Roman Urdu, in that order.
COPY = {
    "movement_task": ("Movement task", "حرکت کا کام", "Harkat ka task"),
    "setup": ("Set up a consistent recording", "ہر بار ایک جیسی ریکارڈنگ کی تیاری", "Har baar aik jaisi recording ki tayyari"),
    "setup_camera": ("Use a stable camera, a clear background and good lighting. Keep the same camera position and usual assistance when repeating this task.", "کیمرہ مضبوط جگہ پر رکھیں، پس منظر صاف اور روشنی مناسب ہو۔ دوبارہ کرتے وقت کیمرے کی جگہ اور معمول کی مدد ایک جیسی رکھیں۔", "Camera mazboot jagah par rakhein, background saaf aur roshni munasib ho. Dobara karte waqt camera ki jagah aur apni aam madad aik jaisi rakhein."),
    "setup_stop": ("Give yourself enough space, keep the relevant body or hand joints in view, and stop if the task feels unsafe or uncomfortable.", "کافی جگہ رکھیں اور متعلقہ جسم یا ہاتھ کے جوڑ کیمرے میں دکھائیں۔ بے آرامی، چکر یا عدم توازن ہو تو فوراً رک جائیں؛ زبردستی کام مکمل نہ کریں۔", "Kaafi jagah rakhein aur mutaliqa jism ya haath ke joints camera mein dikhayein. Be-aarami, chakkar ya tawazun bigray to foran ruk jaayein; zabardasti task mukammal na karein."),
    "quality_check": ("Visibility and recording quality are checked before measurements are accepted.", "پیمائش قبول کرنے سے پہلے جوڑوں کی نمائش اور ریکارڈنگ کا معیار دیکھا جاتا ہے۔", "Measurement qabool karne se pehle joints ki visibility aur recording ka mayaar check hota hai."),
    "recording_source": ("Recording source", "ریکارڈنگ کا طریقہ", "Recording ka tareeqa"),
    "upload_video": ("Upload Recorded Video", "پہلے سے ریکارڈ کی ہوئی ویڈیو", "Pehle se record ki hui video"),
    "live_camera": ("Live Camera", "براہِ راست کیمرہ", "Live camera"),
    "upload_assessment": ("Upload assessment video", "جانچ کی ویڈیو منتخب کریں", "Jaiza ki video select karein"),
    "video_limits": ("Maximum 100 MB. Clips must be at most 45 seconds. Select the matching movement task before uploading.", "ویڈیو زیادہ سے زیادہ 100 MB اور 45 سیکنڈ کی ہو۔ اپ لوڈ کرنے سے پہلے ویڈیو کے مطابق حرکت منتخب کریں۔", "Video zyada se zyada 100 MB aur 45 seconds ki ho. Upload se pehle video ke mutabiq harkat select karein."),
    "mobile_recording": ("On a phone, you can record with your usual camera app and upload the clip here. Keep the video upright, use normal speed, and do not mirror or trim away the task.", "فون پر اپنی کیمرہ ایپ سے ویڈیو بنا کر یہاں اپ لوڈ بھی کر سکتے ہیں۔ ویڈیو سیدھی اور عام رفتار پر ہو؛ آئینے جیسی الٹی تصویر نہ بنائیں اور اصل کام کا حصہ نہ کاٹیں۔", "Phone par apni camera app se video bana kar yahan upload bhi kar sakte hain. Video seedhi aur aam raftaar par ho; mirror na karein aur asal task ka hissa na kaatein."),
    "mobile_live": ("Live camera needs browser permission and a secure HTTPS connection on a phone. If it does not connect, use your phone camera and upload a saved video.", "فون پر براہِ راست کیمرے کے لیے براؤزر کی اجازت اور محفوظ HTTPS رابطہ چاہیے۔ رابطہ نہ بنے تو فون کی کیمرہ ایپ سے ویڈیو بنا کر اپ لوڈ کریں۔", "Phone par live camera ke liye browser ki ijazat aur mehfooz HTTPS connection chahiye. Connection na banay to phone ki camera app se video bana kar upload karein."),
    "analyze_video": ("Check and analyze video", "ویڈیو کی جانچ اور تجزیہ کریں", "Video ki jaanch aur analysis karein"),
    "movement_spinner": ("Checking recording quality and extracting movement landmarks…", "ریکارڈنگ کا معیار اور حرکت کے جوڑ دیکھے جا رہے ہیں…", "Recording ka mayaar aur harkat ke joints check ho rahe hain…"),
    "review_save": ("Review and save", "دیکھیں اور محفوظ کریں", "Dekhein aur save karein"),
    "choose_recording": ("Choose a recording and check its quality", "ریکارڈنگ منتخب کریں اور معیار دیکھیں", "Recording select karein aur mayaar dekhein"),
    "live_steps": ("Allow browser camera access, press START, then start recording below. Stop the recording before reviewing it.", "براؤزر کو کیمرے کی اجازت دیں اور کیمرے پر START دبائیں۔ پھر نیچے ریکارڈنگ شروع کریں۔ کام کے بعد «مکمل کریں اور تجزیہ کریں» دبائیں۔ کیمرے کا STOP صرف رابطہ بند کرتا ہے۔", "Browser ko camera ki ijazat dein aur camera par START dabayein. Phir neeche recording shuru karein. Task ke baad 'Mukammal karein aur analysis karein' dabayein. Camera ka STOP sirf connection band karta hai."),
    "live_tracking": ("Live movement tracking", "حرکت کی براہِ راست نگرانی", "Harkat ki live tracking"),
    "focused_joints": ("Keep the selected task's joints visible while you move comfortably.", "آرام سے حرکت کرتے ہوئے منتخب کام کے جوڑ کیمرے میں دکھاتے رہیں۔", "Aaram se harkat karte huay chunay huay task ke joints camera mein dikhate rahein."),
    "joint_lines": ("Show focused joint lines on camera", "کیمرے پر متعلقہ جوڑوں کی لکیریں دکھائیں", "Camera par mutaliqa joints ki lakeerein dikhayein"),
    "joint_lines_help": ("Depth-styled lines follow detected joints on the camera image. The adjacent view shows their estimated 3D coordinates.", "لکیریں کیمرے میں نظر آنے والے جوڑوں کے ساتھ چلتی ہیں۔ ساتھ والا منظر ان کی اندازاً سہ جہتی جگہ دکھاتا ہے۔", "Lakeerein camera mein nazar aane wale joints ke saath chalti hain. Saath wala view un ki andazan 3D jagah dikhata hai."),
    "movement_trails": ("Show short movement trails", "حرکت کا مختصر راستہ دکھائیں", "Harkat ka mukhtasar rasta dikhayein"),
    "viewpoint": ("Live 3D viewpoint", "سہ جہتی منظر کا زاویہ", "Live 3D view ka zaviya"),
    "camera_lines": ("Camera & focused joint lines", "کیمرہ اور متعلقہ جوڑوں کی لکیریں", "Camera aur mutaliqa joints ki lakeerein"),
    "anatomical_side": ("The highlighted joints follow this task. Confirm the selected anatomical side for left/right hand tasks.", "روشن لکیریں اس کام کے جوڑ دکھاتی ہیں۔ بائیں یا دائیں ہاتھ کے کام میں اپنے اصل ہاتھ کی طرف کی تصدیق کریں۔", "Roshan lakeerein is task ke joints dikhati hain. Baen ya daen haath ke task mein apne asal haath ki taraf ki tasdeeq karein."),
    "save_result": ("Save result", "نتیجہ محفوظ کریں", "Nateeja save karein"),
    "saved_analysis": ("Saved task analysis", "محفوظ کیا گیا تجزیہ", "Save kiya gaya analysis"),
    "current_visit": ("These results belong to your current visit.", "یہ نتائج آپ کی موجودہ جانچ کے ہیں۔", "Ye nataij aap ke maujooda jaiza ke hain."),
    "accepted_responses": ("Your responses are ready for review.", "آپ کے جوابات جائزے کے لیے تیار ہیں۔", "Aap ke jawabat review ke liye tayyar hain."),
    "accepted_recording": ("Recording accepted for measurement.", "ریکارڈنگ پیمائش کے لیے قبول ہو گئی ہے۔", "Recording measurement ke liye qabool ho gayi hai."),
    "task_review_required": ("Before using these measurements, review the recording and confirm the selected task and hand side. Quality checks can also accept a different movement or speech task; they do not verify task completion or diagnosis.", "پیمائش استعمال کرنے سے پہلے ریکارڈنگ دیکھیں اور منتخب کام اور ہاتھ کی طرف کی تصدیق کریں۔ معیار کی جانچ مختلف حرکت یا آواز کو بھی قبول کر سکتی ہے؛ اس سے کام کی تکمیل یا تشخیص کی تصدیق نہیں ہوتی۔", "Pemaish istemal karne se pehle recording dekh kar chunay huay task aur haath ki taraf ki tasdeeq karein. Quality check mukhtalif harkat ya speech task ko bhi qabool kar sakta hai; is se task mukammal hone ya diagnosis ki tasdeeq nahi hoti."),
    "retry": ("This attempt needs attention. Follow the steps below before trying again.", "اس کوشش میں مسئلہ ہے۔ دوبارہ کرنے سے پہلے نیچے دیے گئے مرحلے دیکھیں۔", "Is koshish mein masla hai. Dobara karne se pehle neeche diye gaye marahil dekhein."),
    "measurement_details": ("Measurement details", "پیمائش کی تفصیل", "Measurement ki tafseel"),
    "analysis_title": ("{task} analysis", "{task} کا تجزیہ", "{task} ka analysis"),
    "latest_analysis": ("Latest analysis for this task. Analyze again after changing a recording or your answers.", "اس کام کا تازہ تجزیہ۔ ریکارڈنگ یا جواب بدلنے پر دوبارہ تجزیہ کریں۔", "Is task ka taza analysis. Recording ya jawab badalne par dobara analysis karein."),
    "voice_title": ("Voice / Speech", "آواز اور گفتگو", "Aawaz aur guftagu"),
    "voice_setup": ("Record in a quiet room. Use your usual speaking voice.", "پرسکون کمرے میں ریکارڈ کریں۔ اپنی معمول کی آواز استعمال کریں۔", "Pur-sukoon kamray mein record karein. Apni aam bolne wali aawaz istemal karein."),
    "speech_language": ("Speech language", "گفتگو کی زبان", "Guftagu ki zaban"),
    "voice_task": ("Voice task", "آواز کا کام", "Aawaz ka task"),
    "vowel": ("Sustained vowel", "مسلسل آ کی آواز", "Musalsal aa ki aawaz"),
    "sentence": ("Fixed sentence", "مقررہ جملہ", "Muqarrara jumla"),
    "natural": ("Natural speech", "عام گفتگو", "Aam guftagu"),
    "audio_source": ("Audio source", "آواز ریکارڈ کرنے کا طریقہ", "Aawaz record karne ka tareeqa"),
    "microphone": ("Microphone", "مائیکروفون", "Microphone"),
    "upload_wav": ("Upload WAV", "WAV فائل اپ لوڈ کریں", "WAV file upload karein"),
    "record_voice": ("Record voice", "آواز ریکارڈ کریں", "Aawaz record karein"),
    "upload_audio": ("Upload WAV recording", "آواز کی WAV فائل منتخب کریں", "Aawaz ki WAV file select karein"),
    "audio_stop": ("Press the microphone's stop control when the task is complete. Wait for the recorded clip, then choose Analyze and save voice recording.", "کام مکمل ہو تو مائیکروفون کی روکنے والی علامت دبائیں۔ ریکارڈ کی گئی آواز ظاہر ہونے کا انتظار کریں، پھر «آواز کا تجزیہ اور محفوظ کریں» دبائیں۔", "Task mukammal ho to microphone ka stop control dabayein. Record ki hui aawaz aane ka intezar karein, phir 'Aawaz ka analysis aur save karein' dabayein."),
    "save_voice": ("Analyze and save voice recording", "آواز کا تجزیہ اور محفوظ کریں", "Aawaz ka analysis aur save karein"),
    "audio_spinner": ("Checking audio quality and extracting acoustic features…", "آواز کا معیار اور خصوصیات دیکھی جا رہی ہیں…", "Aawaz ka mayaar aur khasusiyat check ho rahi hain…"),
    "voice_saved": ("Voice recording saved. Your patient report has been updated automatically.", "آواز محفوظ ہو گئی ہے۔ آپ کی رپورٹ بھی تازہ کر دی گئی ہے۔", "Aawaz save ho gayi hai. Aap ki report bhi update kar di gayi hai."),
    "asr_unavailable": ("Automatic speech recognition is not configured. You can enter a transcript for multilingual self-report analysis.", "آواز کو خودکار طور پر تحریر میں بدلنے کی سہولت ابھی فعال نہیں۔ آپ اپنی بات خود لکھ سکتے ہیں۔", "Aawaz ko khudkar taur par tehreer mein badalne ki sahulat abhi faal nahi. Aap apni baat khud likh sakte hain."),
    "transcript": ("What was difficult today? / Transcript", "آج کیا مشکل پیش آئی؟ / اپنی بات لکھیں", "Aaj kya mushkil pesh aayi? / Apni baat likhein"),
    "save_description": ("Save daily-life description", "روزمرہ زندگی کی بات محفوظ کریں", "Rozmarra zindagi ki baat save karein"),
    "description_saved": ("Your description was saved and your patient report has been updated.", "آپ کی بات محفوظ ہو گئی اور رپورٹ تازہ کر دی گئی ہے۔", "Aap ki baat save ho gayi aur report update kar di gayi hai."),
    "adl_title": ("Daily Activities", "روزمرہ کے کام", "Rozmarra ke kaam"),
    "adl_intro": ("Think about today. Choose how much difficulty you experienced in each activity.", "آج کے بارے میں سوچیں۔ ہر کام میں جتنی مشکل ہوئی وہ جواب منتخب کریں۔", "Aaj ke bare mein sochein. Har kaam mein jitni mushkil hui woh jawab select karein."),
    "adl_caveat": ("This is a custom self-report questionnaire. It is not a validated clinical scale.", "یہ آپ کی اپنی بات جاننے کے لیے مقامی سوالنامہ ہے۔ یہ طبی طور پر توثیق شدہ پیمانہ نہیں ہے۔", "Ye aap ki apni baat jaanne ke liye maqami sawalnama hai. Ye tibbi taur par tasdeeq shuda paimana nahi hai."),
    "choose_experience": ("Choose your experience", "اپنا جواب منتخب کریں", "Apna jawab select karein"),
    "other_difficulty": ("Other daily-life difficulty", "روزمرہ زندگی کی کوئی اور مشکل", "Rozmarra zindagi ki koi aur mushkil"),
    "save_adl": ("Save daily activities", "روزمرہ کے جواب محفوظ کریں", "Rozmarra ke jawab save karein"),
    "adl_saved": ("Daily activities saved. Your patient report has been updated automatically.", "روزمرہ کے جواب محفوظ ہو گئے ہیں۔ آپ کی رپورٹ بھی تازہ کر دی گئی ہے۔", "Rozmarra ke jawab save ho gaye hain. Aap ki report bhi update kar di gayi hai."),
    "welcome": ("Welcome, {name}", "خوش آمدید، {name}", "Khush aamdeed, {name}"),
    "home_intro": ("Take this at your own pace. Record a task, add a note about your day, or review your earlier visits.", "اپنی سہولت سے آگے بڑھیں۔ کوئی کام ریکارڈ کریں، اپنے دن کی بات لکھیں یا پچھلے نتائج دیکھیں۔", "Apni sahulat se aage barhein. Koi task record karein, apne din ki baat likhein ya pichhle nataij dekhein."),
    "assessments": ("Assessments", "جانچیں", "Jaize"),
    "completed": ("Completed", "مکمل", "Mukammal"),
    "latest_visit": ("Latest visit", "تازہ جانچ", "Taza jaiza"),
    "no_visits": ("No visits yet", "ابھی کوئی جانچ نہیں", "Abhi koi jaiza nahi"),
    "start_resume": ("Start or resume an assessment", "جانچ شروع کریں یا جاری رکھیں", "Jaiza shuru karein ya jari rakhein"),
    "my_goals": ("Daily check-in & my goals", "آج کا حال اور میرے مقصد", "Aaj ka haal aur mere maqsad"),
    "recent_visits": ("Recent visits", "حالیہ جانچیں", "Haliya jaize"),
    "visits_detail": ("Each visit keeps its recordings, your responses and the care team's review together.", "ہر جانچ میں ریکارڈنگ، آپ کے جواب اور نگہداشت کی ٹیم کا جائزہ ایک ساتھ رہتا ہے۔", "Har jaiza mein recording, aap ke jawab aur dekh bhaal ki team ka review aik saath rehta hai."),
    "first_visit": ("Your first visit starts here", "آپ کی پہلی جانچ یہیں سے شروع ہوتی ہے", "Aap ka pehla jaiza yahin se shuru hota hai"),
    "first_visit_detail": ("One reliable task is enough to begin. A later recording of that same task can be compared with your first.", "شروع کرنے کے لیے ایک قابلِ استعمال کام کافی ہے۔ بعد میں اسی کام کی ریکارڈنگ کو پہلی سے ملا کر دیکھا جا سکتا ہے۔", "Shuru karne ke liye aik qabil-e-istemal task kaafi hai. Baad mein usi task ki recording ko pehli se mila kar dekha ja sakta hai."),
    "hub_title": ("Start Assessment", "جانچ شروع کریں", "Jaiza shuru karein"),
    "hub_intro": ("Choose the tasks agreed with your care team. Each recording gets a quality check before it is saved.", "اپنی نگہداشت کی ٹیم سے طے کیے گئے کام منتخب کریں۔ محفوظ کرنے سے پہلے ہر ریکارڈنگ کا معیار دیکھا جاتا ہے۔", "Apni dekh bhaal ki team se tay kiye gaye tasks select karein. Save karne se pehle har recording ka mayaar check hota hai."),
    "new_assessment": ("Start new assessment", "نئی جانچ شروع کریں", "Naya jaiza shuru karein"),
    "resume_assessment": ("Resume an unfinished assessment", "نامکمل جانچ منتخب کریں", "Na-mukammal jaiza select karein"),
    "resume_selected": ("Resume selected assessment", "منتخب جانچ جاری رکھیں", "Chuna hua jaiza jari rakhein"),
    "open_hub": ("Go to Start Assessment", "«جانچ شروع کریں» کھولیں", "'Jaiza shuru karein' kholein"),
    "need_assessment": ("Start or resume a visit on the Start Assessment page first.", "پہلے «جانچ شروع کریں» والے صفحے پر نئی جانچ شروع کریں یا پچھلی جاری رکھیں۔", "Pehle 'Jaiza shuru karein' page par naya jaiza shuru karein ya pichhla jari rakhein."),
    "ready": ("Ready when you are", "جب آپ تیار ہوں", "Jab aap tayyar hon"),
    "saved_count": ("{count} saved in this visit", "اس جانچ میں {count} محفوظ", "Is jaiza mein {count} save"),
    "tasks_saved": ("{count} tasks saved", "{count} کام محفوظ", "{count} tasks save"),
    "open_task": ("Open {task}", "{task} کھولیں", "{task} kholein"),
    "complete_assessment": ("Complete this assessment", "یہ جانچ مکمل کریں", "Ye jaiza mukammal karein"),
    "assessment_completed": ("Assessment completed. It is ready for your care team to review.", "جانچ مکمل ہو گئی ہے۔ آپ کی نگہداشت کی ٹیم اب جائزہ لے سکتی ہے۔", "Jaiza mukammal ho gaya hai. Aap ki dekh bhaal ki team ab review kar sakti hai."),
    "restart_visit": ("Restart this visit", "یہ جانچ دوبارہ شروع کریں", "Ye jaiza dobara shuru karein"),
    "abandon_visit": ("Keep this visit as abandoned and start an empty assessment", "یہ جانچ چھوڑے گئے ریکارڈ کے طور پر رکھیں اور خالی جانچ شروع کریں", "Ye jaiza chhora hua record rakhein aur khali jaiza shuru karein"),
    "restart_assessment": ("Restart assessment", "جانچ دوبارہ شروع کریں", "Jaiza dobara shuru karein"),
    "switch_visit": ("Open another visit or start a new one", "کوئی اور جانچ کھولیں یا نئی شروع کریں", "Koi aur jaiza kholein ya naya shuru karein"),
    # Touchscreen spiral and tapping tests.
    "touch_title": ("Spiral & tapping", "اسپائرل اور ٹیپنگ", "Spiral aur tapping"),
    "touch_intro": ("Two short tests on this screen, with your finger. They measure drawing and tapping only; they are not a diagnosis.", "اسی اسکرین پر انگلی سے دو مختصر ٹیسٹ۔ یہ صرف ڈرائنگ اور چھونے کی پیمائش کرتے ہیں؛ یہ تشخیص نہیں۔", "Isi screen par ungli se do mukhtasar test. Ye sirf drawing aur chhoone ki pemaish karte hain; ye tashkhees nahi."),
    "touch_test": ("Test", "ٹیسٹ", "Test"),
    "touch_spiral": ("Spiral drawing", "اسپائرل بنانا", "Spiral banana"),
    "touch_tapping": ("Two-circle tapping", "دو دائروں پر ٹیپنگ", "Do daairon par tapping"),
    "touch_hand": ("Hand used", "کون سا ہاتھ", "Kaunsa haath"),
    "hand_right": ("Right hand", "دایاں ہاتھ", "Dayan haath"),
    "hand_left": ("Left hand", "بایاں ہاتھ", "Bayan haath"),
    "touch_ready_spiral": ("Start on the green dot and trace the grey spiral outwards.", "سبز نقطے سے شروع کریں اور سرمئی اسپائرل پر باہر کی طرف چلیں۔", "Hare nuqte se shuru karein aur grey spiral par bahar ki taraf chalein."),
    "touch_ready_tapping": ("Tap the highlighted circle, then the other. The 20 seconds start with your first tap.", "نمایاں دائرے کو چھوئیں، پھر دوسرے کو۔ 20 سیکنڈ پہلی بار چھونے سے شروع ہوں گے۔", "Numayan daaire ko chhoein, phir doosre ko. 20 seconds pehli dafa chhoone se shuru honge."),
    "touch_remaining": ("{seconds} seconds left", "{seconds} سیکنڈ باقی", "{seconds} seconds baqi"),
    "touch_analysing": ("Measuring…", "پیمائش ہو رہی ہے…", "Pemaish ho rahi hai…"),
    "touch_measured": ("Measured — see the result below. Clear to try again.", "پیمائش ہو گئی — نتیجہ نیچے دیکھیں۔ دوبارہ کرنے کے لیے صاف کریں۔", "Pemaish ho gayi — natija neeche dekhein. Dobara karne ke liye saaf karein."),
    "touch_clear": ("Clear and start again", "صاف کر کے دوبارہ", "Saaf kar ke dobara"),
    "touch_done": ("Done", "مکمل", "Mukammal"),
    "touch_stop": ("Stop early", "پہلے روکیں", "Pehle rokein"),
    "touch_canvas": ("Drawing area for the touch test", "ٹچ ٹیسٹ کی ڈرائنگ کی جگہ", "Touch test ki drawing ki jagah"),
    "touch_same_device": ("Use the same phone, hand and test each time so that visits can be compared.", "ہر بار وہی فون، وہی ہاتھ اور وہی ٹیسٹ استعمال کریں تاکہ جانچوں کا موازنہ ہو سکے۔", "Har baar wohi phone, wohi haath aur wohi test istemal karein taake jaizon ka muqabla ho sake."),
    # Who helped, and walking aids: context for comparing like with like.
    "assist_title": ("Help and walking aid for this visit", "اس جانچ میں مدد اور چلنے کا سہارا", "Is jaiza mein madad aur chalne ka sahara"),
    "assist_intro": ("Help and walking aids change how tasks are done, so your care team compares visits made the same way.", "مدد اور سہارا کام کرنے کا طریقہ بدل دیتے ہیں، اس لیے آپ کی ٹیم ایک جیسی جانچوں کا موازنہ کرتی ہے۔", "Madad aur sahara kaam karne ka tareeqa badal dete hain, is liye aap ki team aik jaisi jaanchon ka muqabla karti hai."),
    "assist_helper": ("Who helped with this visit?", "اس جانچ میں کس نے مدد کی؟", "Is jaiza mein kis ne madad ki?"),
    "assist_aid": ("Walking aid used", "چلنے کا سہارا", "Chalne ka sahara"),
    "assist_save": ("Save help and walking aid", "مدد اور سہارا محفوظ کریں", "Madad aur sahara save karein"),
    "assist_saved": ("Saved for this visit.", "اس جانچ کے لیے محفوظ ہو گیا۔", "Is jaiza ke liye save ho gaya."),
    "helper_alone": ("No one — I did it myself", "کسی نے نہیں — خود کیا", "Kisi ne nahi — khud kiya"),
    "helper_family": ("Family member", "گھر کا فرد", "Ghar ka fard"),
    "helper_caregiver": ("Paid caregiver", "تنخواہ دار دیکھ بھال کرنے والا", "Tankhwahdaar dekh bhaal karne wala"),
    "helper_clinic_staff": ("Clinic staff", "کلینک کا عملہ", "Clinic ka amla"),
    "helper_other": ("Someone else", "کوئی اور", "Koi aur"),
    "aid_none": ("No walking aid", "کوئی سہارا نہیں", "Koi sahara nahi"),
    "aid_cane": ("Walking stick", "چھڑی", "Chhari"),
    "aid_walker": ("Walker", "واکر", "Walker"),
    "aid_wheelchair": ("Wheelchair", "وہیل چیئر", "Wheelchair"),
    "aid_other": ("Other aid", "کوئی اور سہارا", "Koi aur sahara"),
    "checkin_helper": ("Did someone help you fill this in? (optional)", "کیا کسی نے یہ بھرنے میں مدد کی؟ (اختیاری)", "Kya kisi ne ye bharne mein madad ki? (ikhtiyari)"),
    "helped_by": ("Entered with help from: {helper}", "مدد کے ساتھ درج: {helper}", "Madad ke saath darj: {helper}"),
    # Read-aloud for fixed instructions.
    "listen": ("Listen", "سنیں", "Sunein"),
    "no_urdu_voice": ("This device has no Urdu voice installed, so the instructions cannot be read aloud.", "اس آلے پر اردو آواز موجود نہیں، اس لیے ہدایات پڑھ کر نہیں سنائی جا سکتیں۔", "Is device par Urdu aawaz maujood nahi, is liye hidayat parh kar nahi sunayi ja saktein."),
    "no_speech": ("This browser cannot read text aloud.", "یہ براؤزر عبارت پڑھ کر نہیں سنا سکتا۔", "Ye browser ibarat parh kar nahi suna sakta."),
    # Browser-only practice aids; nothing is recorded or saved.
    "practice_title": ("Practice", "مشق", "Mashq"),
    "practice_intro": ("Two practice aids that run only in this browser. Nothing is recorded or saved, and they are not measurements.", "دو مشقیں جو صرف اسی براؤزر میں چلتی ہیں۔ کچھ ریکارڈ یا محفوظ نہیں ہوتا، اور یہ پیمائش نہیں۔", "Do mashqein jo sirf isi browser mein chalti hain. Kuch record ya save nahi hota, aur ye pemaish nahi."),
    "practice_walk": ("Walking beat", "چلنے کی تال", "Chalne ki taal"),
    "practice_voice": ("Louder voice", "اونچی آواز", "Oonchi aawaz"),
    "metronome_intro": ("A steady beat helps some people with Parkinson's start walking and keep a rhythm. Step on each beat.", "کچھ پارکنسن کے مریضوں کو یکساں تال سے چلنا شروع کرنے اور رفتار برقرار رکھنے میں مدد ملتی ہے۔ ہر تال پر قدم رکھیں۔", "Kuch Parkinson ke mareezon ko yaksaan taal se chalna shuru karne aur raftaar barqarar rakhne mein madad milti hai. Har taal par qadam rakhein."),
    "metronome_safety": ("Practise only where it is safe, with your usual walking aid or a helper nearby. Stop if you feel unsteady, and ask your care team which pace suits you.", "صرف محفوظ جگہ پر، اپنے معمول کے سہارے یا کسی مددگار کے ساتھ مشق کریں۔ عدم توازن ہو تو رک جائیں، اور اپنی ٹیم سے پوچھیں کہ کون سی رفتار آپ کے لیے مناسب ہے۔", "Sirf mehfooz jagah par, apne maamool ke sahare ya kisi madadgar ke saath mashq karein. Tawazun bigray to ruk jayein, aur apni team se poochhein ke kaunsi raftaar aap ke liye munasib hai."),
    "metronome_from_cadence": ("The beat starts at your last measured walking pace.", "تال آپ کی پچھلی ناپی گئی چلنے کی رفتار سے شروع ہوتی ہے۔", "Taal aap ki pichhli naapi gayi chalne ki raftaar se shuru hoti hai."),
    "metronome_start": ("Start beat", "تال شروع کریں", "Taal shuru karein"),
    "metronome_stop": ("Stop", "روکیں", "Rokein"),
    "metronome_slower": ("Slower", "آہستہ", "Ahista"),
    "metronome_faster": ("Faster", "تیز", "Tez"),
    "metronome_bpm": ("{bpm} steps per minute", "{bpm} قدم فی منٹ", "{bpm} qadam fi minute"),
    "loudness_intro": ("Say 'aah' or read aloud. For the first 3 seconds speak in your usual voice; then keep the bar past the orange line — a little louder than usual, without straining.", "«آ» کہیں یا اونچی آواز میں پڑھیں۔ پہلے 3 سیکنڈ اپنی معمول کی آواز میں بولیں؛ پھر پٹی کو نارنجی لکیر سے آگے رکھیں — معمول سے تھوڑا اونچا، زور لگائے بغیر۔", "'Aa' kahein ya oonchi aawaz mein parhein. Pehle 3 seconds apni maamool ki aawaz mein bolein; phir patti ko narangi lakeer se aage rakhein — maamool se thora ooncha, zor lagaye baghair."),
    "loudness_privacy": ("Your voice is processed only in this browser; nothing is recorded, saved or sent.", "آپ کی آواز صرف اسی براؤزر میں پرکھی جاتی ہے؛ کچھ ریکارڈ، محفوظ یا بھیجا نہیں جاتا۔", "Aap ki aawaz sirf isi browser mein parkhi jati hai; kuch record, save ya bheja nahi jata."),
    "loudness_ready": ("Press Start, then speak.", "شروع دبائیں، پھر بولیں۔", "Shuru dabayein, phir bolein."),
    "loudness_start": ("Start listening", "سننا شروع کریں", "Sunna shuru karein"),
    "loudness_stop": ("Stop", "روکیں", "Rokein"),
    "loudness_calibrating": ("Speak in your usual voice…", "اپنی معمول کی آواز میں بولیں…", "Apni maamool ki aawaz mein bolein…"),
    "loudness_go": ("Now a little louder — past the orange line.", "اب تھوڑا اونچا — نارنجی لکیر سے آگے۔", "Ab thora ooncha — narangi lakeer se aage."),
    "loudness_time": ("Time in the louder zone: {seconds} s", "اونچی آواز کے حصے میں وقت: {seconds} سیکنڈ", "Oonchi aawaz ke hissay mein waqt: {seconds} seconds"),
    "loudness_denied": ("The microphone could not be opened. Allow microphone access for this site and try again.", "مائیکروفون نہیں کھل سکا۔ اس سائٹ کو مائیکروفون کی اجازت دیں اور دوبارہ کوشش کریں۔", "Microphone nahi khul saka. Is site ko microphone ki ijazat dein aur dobara koshish karein."),
    # Weekly task plan suggested by the care team.
    "plan_today": ("Today's plan: {tasks}", "آج کا منصوبہ: {tasks}", "Aaj ka mansooba: {tasks}"),
    "plan_today_detail": ("Your care team suggested these for today. Do them only if you feel able.", "آپ کی ٹیم نے آج کے لیے یہ تجویز کیے ہیں۔ صرف تب کریں جب آپ ٹھیک محسوس کریں۔", "Aap ki team ne aaj ke liye ye tajweez kiye hain. Sirf tab karein jab aap theek mehsoos karein."),
    "plan_week": ("This week's plan from your care team: {plan}", "آپ کی ٹیم کا اس ہفتے کا منصوبہ: {plan}", "Aap ki team ka is haftay ka mansooba: {plan}"),
    "planned_today": ("Planned for today", "آج کے لیے طے", "Aaj ke liye tay"),
    # Medicine ON/OFF diary and usual medicine times. Context only; never advice or doses.
    "diary_tab": ("Medicine diary", "دوا کی ڈائری", "Dawa ki diary"),
    "diary_title": ("How is your medicine working right now?", "اس وقت آپ کی دوا کیسا کام کر رہی ہے؟", "Is waqt aap ki dawa kaisa kaam kar rahi hai?"),
    "diary_intro": ("One tap saves the time and how you feel. It helps your care team understand your day; it does not change your treatment.", "ایک بار دبانے سے وقت اور آپ کی کیفیت محفوظ ہو جاتی ہے۔ اس سے آپ کی ٹیم آپ کا دن سمجھتی ہے؛ اس سے علاج نہیں بدلتا۔", "Aik dafa dabane se waqt aur aap ki kaifiyat save ho jati hai. Is se aap ki team aap ka din samajhti hai; is se ilaaj nahi badalta."),
    "diary_on": ("ON — working well", "ON — اچھا کام کر رہی ہے", "ON — achha kaam kar rahi hai"),
    "diary_on_dyskinesia": ("ON, with extra movements", "ON، مگر اضافی حرکت کے ساتھ", "ON, magar izafi harkat ke saath"),
    "diary_wearing_off": ("Wearing off", "اثر کم ہو رہا ہے", "Asar kam ho raha hai"),
    "diary_off": ("OFF — not working", "OFF — کام نہیں کر رہی", "OFF — kaam nahi kar rahi"),
    "diary_saved": ("Saved for {time}.", "{time} کے لیے محفوظ ہو گیا۔", "{time} ke liye save ho gaya."),
    "diary_earlier": ("Add an earlier time today", "آج کا کوئی پہلے کا وقت درج کریں", "Aaj ka koi pehle ka waqt darj karein"),
    "diary_time": ("Time", "وقت", "Waqt"),
    "diary_state": ("How the medicine was working", "دوا کیسا کام کر رہی تھی", "Dawa kaisa kaam kar rahi thi"),
    "diary_note": ("Note (optional)", "نوٹ (اختیاری)", "Note (ikhtiyari)"),
    "diary_save": ("Save diary entry", "ڈائری میں محفوظ کریں", "Diary mein save karein"),
    "diary_choose": ("Choose the time and an answer", "وقت اور جواب منتخب کریں", "Waqt aur jawab chunein"),
    "diary_counts": ("Last 7 days: {on} ON · {dyskinesia} ON with extra movements · {wearing} wearing off · {off} OFF", "پچھلے 7 دن: {on} ON · {dyskinesia} اضافی حرکت کے ساتھ ON · {wearing} اثر کم · {off} OFF", "Pichhle 7 din: {on} ON · {dyskinesia} izafi harkat ke saath ON · {wearing} asar kam · {off} OFF"),
    "diary_empty": ("No diary entries yet", "ابھی ڈائری میں کچھ نہیں", "Abhi diary mein kuch nahi"),
    "diary_empty_detail": ("Tap a button above whenever you notice your medicine working or wearing off.", "جب بھی دوا کا اثر شروع یا کم ہوتا محسوس ہو، اوپر کا بٹن دبائیں۔", "Jab bhi dawa ka asar shuru ya kam hota mehsoos ho, oopar ka button dabayein."),
    "times_title": ("Your usual medicine times", "دوا کے آپ کے معمول کے اوقات", "Dawa ke aap ke maamool ke auqat"),
    "times_detail": ("Only the times, never medicine names or doses. After each time, Home asks how your medicine is working.", "صرف اوقات، دوا کا نام یا مقدار نہیں۔ ہر وقت کے بعد ابتدائی صفحہ پوچھے گا کہ دوا کیسا کام کر رہی ہے۔", "Sirf auqat, dawa ka naam ya miqdar nahi. Har waqt ke baad Home poochhega ke dawa kaisa kaam kar rahi hai."),
    "times_label": ("Times", "اوقات", "Auqat"),
    "times_save": ("Save times", "اوقات محفوظ کریں", "Auqat save karein"),
    "times_saved": ("Medicine times saved.", "دوا کے اوقات محفوظ ہو گئے۔", "Dawa ke auqat save ho gaye."),
    "next_diary": ("It is past your usual medicine time ({time})", "دوا کا آپ کا معمول کا وقت ({time}) گزر چکا ہے", "Dawa ka aap ka maamool ka waqt ({time}) guzar chuka hai"),
    "next_diary_detail": ("How is your medicine working now? One tap below saves it to your diary.", "اب دوا کیسا کام کر رہی ہے؟ نیچے ایک بار دبانے سے ڈائری میں محفوظ ہو جائے گا۔", "Ab dawa kaisa kaam kar rahi hai? Neeche aik dafa dabane se diary mein save ho jayega."),
    # Same-setup check between a recording and its comparison recording.
    "setup_differs": ("This recording was set up differently from your earlier one", "یہ ریکارڈنگ پچھلی ریکارڈنگ سے مختلف ترتیب میں بنی", "Ye recording pichli recording se mukhtalif tarteeb mein bani"),
    "setup_closer": ("you appear closer to the camera", "آپ کیمرے کے زیادہ قریب نظر آتے ہیں", "aap camera ke zyada qareeb nazar aate hain"),
    "setup_farther": ("you appear farther from the camera", "آپ کیمرے سے زیادہ دور نظر آتے ہیں", "aap camera se zyada door nazar aate hain"),
    "setup_position": ("you are in a different part of the picture", "آپ تصویر کے کسی اور حصے میں ہیں", "aap tasveer ke kisi aur hissay mein hain"),
    "setup_view": ("the camera sees you from a different side or angle", "کیمرہ آپ کو کسی اور رخ یا زاویے سے دیکھ رہا ہے", "camera aap ko kisi aur rukh ya zaviye se dekh raha hai"),
    "setup_orientation": ("the phone was turned the other way (upright or sideways)", "فون دوسری طرف گھمایا گیا تھا (سیدھا یا لیٹا ہوا)", "phone doosri taraf ghumaya gaya tha (seedha ya leta hua)"),
    "setup_screen": ("a different screen size was used", "مختلف سائز کی اسکرین استعمال ہوئی", "mukhtalif size ki screen istemal hui"),
    "setup_pointer": ("a different input was used (finger or stylus)", "چھونے کا مختلف طریقہ استعمال ہوا (انگلی یا قلم)", "chhoone ka mukhtalif tareeqa istemal hua (ungli ya qalam)"),
    "setup_advice": ("Measurements change with setup, so compare these visits with care. Next time, match the earlier setup.", "ترتیب بدلنے سے پیمائش بدلتی ہے، اس لیے ان جانچوں کا موازنہ احتیاط سے کریں۔ اگلی بار پچھلی ترتیب جیسا رکھیں۔", "Tarteeb badalne se pemaish badalti hai, is liye in jaizon ka muqabla ehtiyat se karein. Agli baar pichli tarteeb jaisa rakhein."),
    "setup_same": ("Set up like your earlier recording, so the two can be compared.", "پچھلی ریکارڈنگ جیسی ترتیب ہے، اس لیے دونوں کا موازنہ ہو سکتا ہے۔", "Pichli recording jaisi tarteeb hai, is liye dono ka muqabla ho sakta hai."),
    "setup_last_time": ("How you were framed last time", "پچھلی بار آپ تصویر میں کیسے تھے", "Pichli baar aap tasveer mein kaise thay"),
    "setup_last_time_detail": ("Fill the picture the same way: same distance, same side facing the camera, phone held the same way.", "تصویر میں اسی طرح آئیں: وہی فاصلہ، کیمرے کی طرف وہی رخ، اور فون اسی طرح پکڑا ہوا۔", "Tasveer mein usi tarah aayein: wohi faasla, camera ki taraf wohi rukh, aur phone usi tarah pakra hua."),
    "touch_saved": ("Touch test saved. Your report has been updated.", "ٹچ ٹیسٹ محفوظ ہو گیا۔ آپ کی رپورٹ تازہ کر دی گئی ہے۔", "Touch test save ho gaya. Aap ki report update kar di gayi hai."),
    "profile": ("Profile", "میری معلومات", "Meri maloomat"),
    "full_name": ("Full name", "پورا نام", "Poora naam"),
    "preferred_language": ("Preferred language", "پسندیدہ زبان", "Pasandeeda zaban"),
    "save_profile": ("Save profile", "معلومات محفوظ کریں", "Maloomat save karein"),
    "profile_saved": ("Profile saved.", "معلومات محفوظ ہو گئیں۔", "Maloomat save ho gayin."),
    # Shared live-camera controls are also used by the root UI component.
    "start_recording": ("Start recording", "ریکارڈنگ شروع کریں", "Recording shuru karein"),
    "finish_analyze": ("Finish & analyze", "مکمل کریں اور تجزیہ کریں", "Mukammal karein aur analysis karein"),
    "tracking_ready": ("Ready for live tracking", "براہِ راست نگرانی کے لیے تیار", "Live tracking ke liye tayyar"),
    "tracking_start": ("Press START on the camera and keep the selected body part in view. The focused 3D lines appear when those joints are detected.", "کیمرے پر START دبائیں اور منتخب جسمانی حصہ دکھائیں۔ جوڑ نظر آنے پر سہ جہتی لکیریں ظاہر ہوں گی۔", "Camera par START dabayein aur chuna hua jismani hissa dikhayein. Joints nazar aane par 3D lakeerein zahir hongi."),
    "camera_stopped": ("The camera stopped. Your recorded clip is ready to finish and review.", "کیمرہ رک گیا ہے۔ آپ کی ویڈیو مکمل کرنے اور دیکھنے کے لیے تیار ہے۔", "Camera ruk gaya hai. Aap ki video mukammal karne aur dekhne ke liye tayyar hai."),
    "recording_progress": ("Recording in progress", "ریکارڈنگ جاری ہے", "Recording jari hai"),
    "camera_ready": ("Camera preview ready", "کیمرے کا منظر تیار ہے", "Camera ka view tayyar hai"),
    "camera_paused": ("Camera paused", "کیمرہ رکا ہوا ہے", "Camera ruka hua hai"),
    "even_light": ("Use even light on the selected body part so the joints are easier to see.", "منتخب جسمانی حصے پر یکساں روشنی رکھیں تاکہ جوڑ واضح نظر آئیں۔", "Chunay huay jismani hissay par barabar roshni rakhein taake joints wazeh nazar aayein."),
    "pending_clip": ("A clip from before the camera reconnected is waiting for review. Finish it before starting another recording.", "کیمرہ دوبارہ جڑنے سے پہلے کی ویڈیو جائزے کے لیے موجود ہے۔ نئی ریکارڈنگ سے پہلے اسے مکمل کریں۔", "Camera dobara jurnay se pehle ki video review ke liye maujood hai. Nayi recording se pehle usay mukammal karein."),
    "recording_complete": ("Recording complete. Choose Finish & analyze to review this clip.", "ریکارڈنگ مکمل ہے۔ یہ ویڈیو دیکھنے کے لیے «مکمل کریں اور تجزیہ کریں» دبائیں۔", "Recording mukammal hai. Ye video dekhne ke liye 'Mukammal karein aur analysis karein' dabayein."),
    "camera_lens": ("Camera lens", "کیمرے کا رخ", "Camera ka rukh"),
    "lens_auto": ("Automatic / choose in camera settings", "خودکار / کیمرے کی ترتیبات میں منتخب کریں", "Khudkar / camera settings mein select karein"),
    "lens_front": ("Front camera", "سامنے والا کیمرہ", "Saamne wala camera"),
    "lens_rear": ("Rear camera", "پیچھے والا کیمرہ", "Peechhe wala camera"),
    "lens_help": ("A camera preference is a request to your browser. Use the camera's device selector if your phone chooses a different lens. Keep the same lens for repeat visits.", "یہ کیمرے کی ترجیح براؤزر سے درخواست ہے۔ فون دوسرا کیمرہ چنے تو کیمرے کی ترتیبات سے درست کیمرہ منتخب کریں۔ بار بار جانچ میں ایک ہی کیمرہ رکھیں۔", "Ye camera ki pasand browser se darkhwast hai. Phone doosra camera chunay to camera settings se durust camera select karein. Dobara jaiza mein aik hi camera rakhein."),
    # Home: one stated next step, chosen from the patient's own records.
    "next_resume": ("Carry on with your visit from {date}", "{date} والی جانچ جاری رکھیں", "{date} wala jaiza jari rakhein"),
    "next_resume_detail": ("{done} of {total} task groups saved so far. Each recording is checked before it is kept.", "اب تک {total} میں سے {done} حصے محفوظ ہیں۔ ہر ریکارڈنگ محفوظ ہونے سے پہلے جانچی جاتی ہے۔", "Ab tak {total} mein se {done} hissay save hain. Har recording save hone se pehle check hoti hai."),
    "next_checkin": ("How is today going?", "آج کا دن کیسا گزر رہا ہے؟", "Aaj ka din kaisa guzar raha hai?"),
    "next_checkin_detail": ("A one-minute check-in about energy, sleep, movement and mood helps your care team read your recordings.", "توانائی، نیند، حرکت اور مزاج کے بارے میں ایک منٹ کا حال آپ کی ٹیم کو ریکارڈنگ سمجھنے میں مدد دیتا ہے۔", "Energy, neend, harkat aur mood ke baare mein aik minute ka haal aap ki team ko recordings samajhne mein madad deta hai."),
    "next_reviewed": ("Your care team reviewed your visit from {date}", "آپ کی ٹیم نے {date} والی جانچ کا جائزہ لے لیا ہے", "Aap ki team ne {date} wale jaiza ka review kar liya hai"),
    "next_reviewed_detail": ("Open Reports to read their note next to your measurements.", "ان کا نوٹ اپنی پیمائش کے ساتھ پڑھنے کے لیے رپورٹس کھولیں۔", "Un ka note apni measurements ke saath parhne ke liye Reports kholein."),
    "next_new": ("Start a visit when you feel ready", "جب آپ تیار ہوں تو نئی جانچ شروع کریں", "Jab aap tayyar hon to naya jaiza shuru karein"),
    "next_new_detail": ("Pick one task agreed with your care team. One good recording is enough for a visit.", "اپنی ٹیم سے طے شدہ ایک کام چنیں۔ ایک اچھی ریکارڈنگ بھی کافی ہے۔", "Apni team se tay shuda aik task chunein. Aik achhi recording bhi kaafi hai."),
    "last_checkin": ("Last check-in", "آخری حال", "Aakhri check-in"),
    "checkin_today": ("Today", "آج", "Aaj"),
    "no_checkin": ("Not yet", "ابھی نہیں", "Abhi nahi"),
    "next_review_date": ("Your care team plans to review again on {date}.", "آپ کی ٹیم {date} کو دوبارہ جائزہ لینے کا ارادہ رکھتی ہے۔", "Aap ki team {date} ko dobara review karne ka irada rakhti hai."),
    "open_reports": ("Read the review in Reports", "رپورٹس میں جائزہ پڑھیں", "Reports mein review parhein"),
    "visit_progress": ("{done} of {total} task groups saved", "{total} میں سے {done} حصے محفوظ", "{total} mein se {done} hissay save"),
    "visit_label": ("Visit started {date}", "جانچ کا آغاز: {date}", "Jaiza shuru hua: {date}"),
    # Medicine timing at the time of recording. Context only; never advice.
    "med_title": ("Medicine timing for this visit", "اس جانچ کے وقت دوا کی صورتحال", "Is jaiza ke waqt dawa ki surat-e-haal"),
    "med_intro": ("Movement can change through the day with Parkinson's medicine. Noting the timing lets your care team compare recordings made at similar times. It does not change your treatment.", "پارکنسن کی دوا کے اثر سے دن بھر حرکت بدل سکتی ہے۔ وقت لکھنے سے آپ کی ٹیم ایک جیسے وقت کی ریکارڈنگ کا موازنہ کر سکتی ہے۔ اس سے آپ کا علاج تبدیل نہیں ہوتا۔", "Parkinson ki dawa ke asar se din bhar harkat badal sakti hai. Waqt likhne se aap ki team aik jaise waqt ki recordings ka muqabla kar sakti hai. Is se aap ka ilaaj tabdeel nahi hota."),
    "med_state": ("How are your Parkinson's medicines working right now?", "اس وقت پارکنسن کی دوا کیسا اثر کر رہی ہے؟", "Is waqt Parkinson ki dawa kaisa asar kar rahi hai?"),
    "med_dose": ("When did you take your last dose?", "آخری خوراک کب لی تھی؟", "Aakhri khuraak kab li thi?"),
    "med_dyskinesia": ("Any extra movements you cannot control right now?", "کیا اس وقت کوئی ایسی اضافی حرکت ہو رہی ہے جو آپ کے قابو میں نہیں؟", "Kya is waqt koi aisi izafi harkat ho rahi hai jo aap ke qaabu mein nahi?"),
    "med_note": ("Anything else about today's medicine (optional)", "آج کی دوا کے بارے میں کوئی اور بات (اختیاری)", "Aaj ki dawa ke baare mein koi aur baat (ikhtiyari)"),
    "med_save": ("Save medicine timing", "دوا کا وقت محفوظ کریں", "Dawa ka waqt save karein"),
    "med_saved": ("Medicine timing saved for this visit.", "اس جانچ کے لیے دوا کا وقت محفوظ ہو گیا۔", "Is jaiza ke liye dawa ka waqt save ho gaya."),
    "med_missing": ("Not recorded yet", "ابھی درج نہیں", "Abhi darj nahi"),
    "med_choose": ("Choose an answer", "جواب منتخب کریں", "Jawab chunein"),
    "med_on": ("Working well (ON)", "اچھا اثر کر رہی ہے (ON)", "Achha asar kar rahi hai (ON)"),
    "med_wearing_off": ("Starting to wear off", "اثر کم ہونے لگا ہے", "Asar kam hone laga hai"),
    "med_off": ("Not working yet, or worn off (OFF)", "ابھی اثر نہیں، یا اثر ختم (OFF)", "Abhi asar nahi, ya asar khatam (OFF)"),
    "med_unsure": ("Not sure", "معلوم نہیں", "Maloom nahi"),
    "med_none": ("I don't take Parkinson's medicine", "میں پارکنسن کی دوا نہیں لیتا/لیتی", "Main Parkinson ki dawa nahi leta/leti"),
    "dose_lt1": ("Less than 1 hour ago", "ایک گھنٹے سے کم", "Aik ghante se kam"),
    "dose_1_2": ("1 to 2 hours ago", "ایک سے دو گھنٹے پہلے", "Aik se do ghante pehle"),
    "dose_2_4": ("2 to 4 hours ago", "دو سے چار گھنٹے پہلے", "Do se chaar ghante pehle"),
    "dose_gt4": ("More than 4 hours ago", "چار گھنٹے سے زیادہ", "Chaar ghante se zyada"),
    "dose_unsure": ("Not sure", "معلوم نہیں", "Maloom nahi"),
    "dysk_yes": ("Yes", "ہاں", "Haan"),
    "dysk_no": ("No", "نہیں", "Nahi"),
    "dysk_unsure": ("Not sure", "معلوم نہیں", "Maloom nahi"),
    "med_reminder": ("Medicine timing is not recorded for this visit", "اس جانچ کے لیے دوا کا وقت درج نہیں", "Is jaiza ke liye dawa ka waqt darj nahi"),
    "med_reminder_detail": ("Add it on the Start Assessment page so this recording can be compared with others made at a similar time.", "جانچ شروع کریں والے صفحے پر درج کریں تاکہ اس ریکارڈنگ کا موازنہ ایک جیسے وقت کی ریکارڈنگ سے ہو سکے۔", "Jaiza shuru karein wale page par darj karein taa ke is recording ka muqabla aik jaise waqt ki recordings se ho sake."),
    "med_context_line": ("Medicine timing: {summary}", "دوا کا وقت: {summary}", "Dawa ka waqt: {summary}"),

}

CAMERA_COPY = {
    "start": ("START", "کیمرہ شروع کریں (START)", "Camera shuru karein (START)"),
    "stop": ("STOP", "کیمرہ بند کریں (STOP)", "Camera band karein (STOP)"),
    "select_device": ("SELECT DEVICE", "کیمرہ منتخب کریں", "Camera select karein"),
    "media_api_not_available": ("Camera access is unavailable in this browser. Use HTTPS on a phone, or upload a saved recording.", "اس براؤزر میں کیمرہ دستیاب نہیں۔ فون پر HTTPS رابطہ کھولیں یا محفوظ ویڈیو اپ لوڈ کریں۔", "Is browser mein camera dastiyab nahi. Phone par HTTPS connection kholein ya saved video upload karein."),
    "device_ask_permission": ("Allow camera access in your browser to show the preview.", "منظر دکھانے کے لیے براؤزر میں کیمرے کی اجازت دیں۔", "View dikhane ke liye browser mein camera ki ijazat dein."),
    "device_not_available": ("No camera was found. Connect a camera or upload a saved recording.", "کوئی کیمرہ نہیں ملا۔ کیمرہ جوڑیں یا محفوظ ویڈیو اپ لوڈ کریں۔", "Koi camera nahi mila. Camera jorein ya saved video upload karein."),
    "device_access_denied": ("Camera permission was denied. Check browser site permissions or upload a saved recording.", "کیمرے کی اجازت نہیں ملی۔ براؤزر کی اس سائٹ کی اجازت دیکھیں یا محفوظ ویڈیو اپ لوڈ کریں۔", "Camera ki ijazat nahi mili. Browser ki is site ki permissions dekhein ya saved video upload karein."),
    "turn_camera_on": ("Turn camera on", "کیمرہ چلائیں", "Camera chalayein"),
    "turn_camera_off": ("Turn camera off", "کیمرہ بند کریں", "Camera band karein"),
    "mute_microphone": ("Mute microphone", "مائیکروفون خاموش کریں", "Microphone khamosh karein"),
    "unmute_microphone": ("Unmute microphone", "مائیکروفون کی آواز کھولیں", "Microphone ki aawaz kholein"),
    "select_camera": ("Select camera", "کیمرہ منتخب کریں", "Camera select karein"),
    "select_microphone": ("Select microphone", "مائیکروفون منتخب کریں", "Microphone select karein"),
}

TASK_LABELS = {
    "gait": ("Walking / gait", "چلنا", "Chalna"),
    "turning": ("Turning", "مڑنا", "Murna"),
    "finger_left": ("Finger tapping — left", "انگلی ملانا — بایاں ہاتھ", "Ungli milana — baen haath"),
    "finger_right": ("Finger tapping — right", "انگلی ملانا — دایاں ہاتھ", "Ungli milana — daen haath"),
    "hand_open_close": ("Hand opening / closing", "ہاتھ کھولنا اور بند کرنا", "Haath kholna aur band karna"),
    "sit_to_stand": ("Sit-to-stand", "بیٹھنے سے کھڑا ہونا", "Baithne se khara hona"),
    "reach": ("Functional reach", "ہاتھ آگے بڑھانا", "Haath aage barhana"),
    "grasp": ("Grasp", "چیز پکڑنا", "Cheez pakarna"),
    "object_transfer": ("Object transfer", "چیز ایک جگہ سے دوسری جگہ رکھنا", "Cheez aik jagah se doosri jagah rakhna"),
    "voice_vowel": ("Voice — sustained vowel", "آواز — مسلسل آ", "Aawaz — musalsal aa"),
    "voice_sentence": ("Voice — fixed sentence", "آواز — مقررہ جملہ", "Aawaz — muqarrara jumla"),
    "voice_natural": ("Voice — natural speech", "آواز — عام گفتگو", "Aawaz — aam guftagu"),
    "nlp": ("Daily-life description", "روزمرہ زندگی کی بات", "Rozmarra zindagi ki baat"),
    "adl": COPY["adl_title"],
    "voice": ("Voice", "آواز", "Aawaz"),
    "spiral_left": ("Spiral drawing — left hand", "اسپائرل — بایاں ہاتھ", "Spiral — bayan haath"),
    "spiral_right": ("Spiral drawing — right hand", "اسپائرل — دایاں ہاتھ", "Spiral — dayan haath"),
    "touch_tap_left": ("Two-circle tapping — left hand", "دو دائروں پر ٹیپنگ — بایاں ہاتھ", "Do daairon par tapping — bayan haath"),
    "touch_tap_right": ("Two-circle tapping — right hand", "دو دائروں پر ٹیپنگ — دایاں ہاتھ", "Do daairon par tapping — dayan haath"),
}

# Three practical steps keep preparation, the action and stopping distinct.
TASK_STEPS = {
    "gait": (
        ("Place the camera on a stable stand with your full body visible and a clear, familiar walking route.", "Walk along the route at your usual pace, turn comfortably and return. Use your usual mobility aid and assistance.", "Record 5–45 seconds, then stop. Stop immediately if you feel unsteady or uncomfortable."),
        ("کیمرہ مضبوط جگہ پر رکھیں۔ پورا جسم اور چلنے کا صاف، جانا پہچانا راستہ نظر آئے۔", "معمول کی رفتار سے چلیں، آرام سے مڑیں اور واپس آئیں۔ اپنی معمول کی مدد یا چلنے کا سہارا استعمال کریں۔", "5 سے 45 سیکنڈ ریکارڈ کریں، پھر رک جائیں۔ عدم توازن یا بے آرامی ہو تو فوراً رکیں۔"),
        ("Camera mazboot jagah par rakhein. Poora jism aur chalne ka saaf, jana pehchana rasta nazar aaye.", "Aam raftaar se chalein, aaram se murein aur wapas aayein. Apni aam madad ya chalne ka sahara istemal karein.", "5 se 45 seconds record karein, phir ruk jaayein. Tawazun bigray ya be-aarami ho to foran rukein."),
    ),
    "turning": (
        ("Keep your full body in view. Clear enough space to turn and use your usual support.", "Make a comfortable turn at your usual pace. Do not force a larger or faster turn.", "Record 3–45 seconds, then stop. Stop if you feel unsteady."),
        ("پورا جسم کیمرے میں رکھیں۔ مڑنے کے لیے جگہ صاف کریں اور معمول کا سہارا استعمال کریں۔", "اپنی معمول کی رفتار سے آرام سے مڑیں۔ بڑا یا تیز موڑ زبردستی نہ لیں۔", "3 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ عدم توازن ہو تو فوراً رک جائیں۔"),
        ("Poora jism camera mein rakhein. Murnay ke liye jagah saaf karein aur aam sahara istemal karein.", "Apni aam raftaar se aaram se murein. Bara ya tez mor zabardasti na lein.", "3 se 45 seconds record karein, phir rukein. Tawazun bigray to foran ruk jaayein."),
    ),
    "finger_left": (
        ("Select your left hand. Keep the wrist and every fingertip visible; do not mirror the recording.", "Repeatedly touch your left thumb and index finger together at a comfortable pace.", "Record 5–45 seconds, then stop. Rest if your hand becomes uncomfortable."),
        ("اپنا بایاں ہاتھ منتخب کریں۔ کلائی اور تمام انگلیوں کے سرے دکھائیں؛ ویڈیو کو آئینے جیسا الٹا نہ کریں۔", "بائیں ہاتھ کے انگوٹھے اور شہادت کی انگلی کو آرام کی رفتار سے بار بار ملائیں۔", "5 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ ہاتھ میں بے آرامی ہو تو آرام کریں۔"),
        ("Apna baen haath select karein. Kalai aur tamam ungliyon ke siray dikhayein; video mirror na karein.", "Baen haath ke angoothay aur shahadat ki ungli ko aaram ki raftaar se baar baar milayein.", "5 se 45 seconds record karein, phir rukein. Haath mein be-aarami ho to aaram karein."),
    ),
    "finger_right": (
        ("Select your right hand. Keep the wrist and every fingertip visible; do not mirror the recording.", "Repeatedly touch your right thumb and index finger together at a comfortable pace.", "Record 5–45 seconds, then stop. Rest if your hand becomes uncomfortable."),
        ("اپنا دایاں ہاتھ منتخب کریں۔ کلائی اور تمام انگلیوں کے سرے دکھائیں؛ ویڈیو کو آئینے جیسا الٹا نہ کریں۔", "دائیں ہاتھ کے انگوٹھے اور شہادت کی انگلی کو آرام کی رفتار سے بار بار ملائیں۔", "5 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ ہاتھ میں بے آرامی ہو تو آرام کریں۔"),
        ("Apna daen haath select karein. Kalai aur tamam ungliyon ke siray dikhayein; video mirror na karein.", "Daen haath ke angoothay aur shahadat ki ungli ko aaram ki raftaar se baar baar milayein.", "5 se 45 seconds record karein, phir rukein. Haath mein be-aarami ho to aaram karein."),
    ),
    "hand_open_close": (
        ("Keep one hand fully visible, including the wrist and every fingertip.", "Open and close the same hand repeatedly at a comfortable pace.", "Record 5–45 seconds, then stop. Rest if you feel discomfort."),
        ("ایک ہاتھ مکمل دکھائیں، کلائی اور تمام انگلیوں کے سرے بھی نظر آئیں۔", "اسی ہاتھ کو آرام کی رفتار سے بار بار کھولیں اور بند کریں۔", "5 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ بے آرامی ہو تو آرام کریں۔"),
        ("Aik haath mukammal dikhayein, kalai aur tamam ungliyon ke siray bhi nazar aayein.", "Usi haath ko aaram ki raftaar se baar baar kholein aur band karein.", "5 se 45 seconds record karein, phir rukein. Be-aarami ho to aaram karein."),
    ),
    "sit_to_stand": (
        ("Use a stable chair and your usual assistance. Record from the side with shoulders, hips, knees and ankles visible.", "Stand and sit at your comfortable pace only if this is safe for you.", "Record 3–45 seconds, then stop. If standing feels unsafe, leave this task and tell your care team."),
        ("مضبوط کرسی اور اپنی معمول کی مدد استعمال کریں۔ پہلو سے ریکارڈ کریں، کندھے، کولہے، گھٹنے اور ٹخنے نظر آئیں۔", "صرف جب آپ کے لیے محفوظ ہو، آرام کی رفتار سے کھڑے ہوں اور بیٹھیں۔", "3 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ کھڑا ہونا غیر محفوظ لگے تو کام چھوڑ دیں اور نگہداشت کی ٹیم کو بتائیں۔"),
        ("Mazboot kursi aur apni aam madad istemal karein. Pehlu se record karein, kandhay, koolhay, ghutnay aur takhnay nazar aayein.", "Sirf jab aap ke liye mehfooz ho, aaram ki raftaar se kharay hon aur baithein.", "3 se 45 seconds record karein, phir rukein. Khara hona ghair-mehfooz lagay to task chhor dein aur dekh bhaal ki team ko batayein."),
    ),
    "reach": (
        ("Sit or stand comfortably. Keep your torso, hips, shoulders, elbows and wrists visible.", "Reach toward a nearby safe target and return, without stretching beyond your comfortable range.", "Record 3–45 seconds, then stop. Stop if you lose balance or feel discomfort."),
        ("آرام سے بیٹھیں یا کھڑے ہوں۔ دھڑ، کولہے، کندھے، کہنیاں اور کلائیاں دکھائیں۔", "قریب موجود محفوظ چیز کی طرف ہاتھ بڑھائیں اور واپس لائیں۔ اپنی آرام کی حد سے زیادہ نہ کھینچیں۔", "3 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ توازن بگڑے یا بے آرامی ہو تو فوراً رکیں۔"),
        ("Aaram se baithein ya kharay hon. Dhar, koolhay, kandhay, kohniyan aur kalaiyan dikhayein.", "Qareeb maujood mehfooz cheez ki taraf haath barhayein aur wapas laayein. Apni aaram ki had se zyada na khenchein.", "3 se 45 seconds record karein, phir rukein. Tawazun bigray ya be-aarami ho to foran rukein."),
    ),
    "grasp": (
        ("Place a safe, light everyday object within easy reach. Keep your entire selected hand visible.", "Grasp and release the object at your usual comfortable pace.", "Record 3–45 seconds, then stop. Avoid sharp, hot or breakable objects."),
        ("ہلکی اور محفوظ روزمرہ کی چیز آسان پہنچ میں رکھیں۔ منتخب ہاتھ مکمل نظر آئے۔", "آرام کی معمول کی رفتار سے چیز پکڑیں اور چھوڑیں۔", "3 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ تیز، گرم یا ٹوٹنے والی چیز استعمال نہ کریں۔"),
        ("Halki aur mehfooz rozmarra ki cheez aasaan pohanch mein rakhein. Chuna hua haath mukammal nazar aaye.", "Aaram ki aam raftaar se cheez pakrein aur chhorein.", "3 se 45 seconds record karein, phir rukein. Tez, garam ya tootne wali cheez istemal na karein."),
    ),
    "object_transfer": (
        ("Use a light, safe object and two nearby positions. Keep your selected hand visible throughout.", "Move the object between the nearby positions at a comfortable pace.", "Record 3–45 seconds, then stop. Avoid sharp, hot or breakable objects."),
        ("ہلکی، محفوظ چیز اور قریب کی دو جگہیں استعمال کریں۔ منتخب ہاتھ پورا وقت دکھائیں۔", "آرام کی رفتار سے چیز کو ایک جگہ سے دوسری جگہ رکھیں۔", "3 سے 45 سیکنڈ ریکارڈ کریں، پھر رکیں۔ تیز، گرم یا ٹوٹنے والی چیز استعمال نہ کریں۔"),
        ("Halki, mehfooz cheez aur qareeb ki do jagah istemal karein. Chuna hua haath poora waqt dikhayein.", "Aaram ki raftaar se cheez ko aik jagah se doosri jagah rakhein.", "3 se 45 seconds record karein, phir rukein. Tez, garam ya tootne wali cheez istemal na karein."),
    ),
}

_SPIRAL_STEPS = (
    ("Rest the phone on a table, or hold it steady in your other hand. Use the hand chosen above.", "Put your finger on the green dot and trace the grey spiral outwards at a comfortable pace, without lifting if you can.", "Press Done at the end of the spiral. If your finger slipped, clear and start again."),
    ("فون میز پر رکھیں، یا دوسرے ہاتھ میں مضبوطی سے پکڑیں۔ اوپر منتخب کیا گیا ہاتھ استعمال کریں۔", "انگلی سبز نقطے پر رکھیں اور سرمئی اسپائرل پر آرام کی رفتار سے باہر کی طرف چلیں؛ ہو سکے تو انگلی نہ اٹھائیں۔", "اسپائرل کے آخر پر «مکمل» دبائیں۔ انگلی پھسل جائے تو صاف کر کے دوبارہ شروع کریں۔"),
    ("Phone mez par rakhein, ya doosre haath mein mazbooti se pakrein. Oopar chuna hua haath istemal karein.", "Ungli hare nuqte par rakhein aur grey spiral par aaram ki raftaar se bahar ki taraf chalein; ho sake to ungli na uthayein.", "Spiral ke aakhir par 'Mukammal' dabayein. Ungli phisal jaye to saaf kar ke dobara shuru karein."),
)
_TAP_STEPS = (
    ("Rest the phone on a table. Use one finger of the hand chosen above.", "Tap the highlighted circle, then the other, back and forth as quickly and evenly as is comfortable.", "The test lasts 20 seconds from your first tap and then stops by itself."),
    ("فون میز پر رکھیں۔ اوپر منتخب ہاتھ کی ایک انگلی استعمال کریں۔", "نمایاں دائرے کو چھوئیں، پھر دوسرے کو؛ آرام کے مطابق جتنا تیز اور یکساں ہو سکے باری باری چھوئیں۔", "ٹیسٹ پہلی بار چھونے سے 20 سیکنڈ چلتا ہے اور پھر خود رک جاتا ہے۔"),
    ("Phone mez par rakhein. Oopar chunay huay haath ki aik ungli istemal karein.", "Numayan daaire ko chhoein, phir doosre ko; aaram ke mutabiq jitna tez aur yaksaan ho sake baari baari chhoein.", "Test pehli dafa chhoone se 20 seconds chalta hai aur phir khud ruk jata hai."),
)
TASK_STEPS.update({"spiral_left": _SPIRAL_STEPS, "spiral_right": _SPIRAL_STEPS,
                   "touch_tap_left": _TAP_STEPS, "touch_tap_right": _TAP_STEPS})

VOICE_PROMPTS = {
    "vowel": ("Sustain a comfortable ‘aa’ sound for at least 3 seconds. Stop if you need a breath; do not strain.", "کم از کم 3 سیکنڈ آرام سے مسلسل «آ» کی آواز نکالیں۔ سانس کی ضرورت ہو تو رک جائیں؛ زور نہ لگائیں۔", "Kam az kam 3 seconds aaram se musalsal 'aa' ki aawaz nikalein. Saans ki zaroorat ho to ruk jaayein; zor na lagayein."),
    "sentence": ("Repeat: ‘Today I am describing my everyday activities.’ Use the same sentence and language at each visit.", "یہ جملہ بولیں: «آج میں اپنے روزمرہ کے کاموں کے بارے میں بتا رہا ہوں۔» ہر جانچ میں یہی جملہ اور یہی زبان رکھیں۔", "Ye jumla bolein: 'Aaj main apne rozmarra ke kaamon ke bare mein bata raha hoon.' Har jaiza mein yahi jumla aur yahi zaban rakhein."),
    "natural": ("Describe what was difficult in your everyday activities today. Speak in your own words and at your usual pace.", "بتائیں آج روزمرہ کے کاموں میں کیا مشکل ہوئی۔ اپنی بات اپنے الفاظ میں اور معمول کی رفتار سے کہیں۔", "Batayein aaj rozmarra ke kaamon mein kya mushkil hui. Apni baat apne alfaaz mein aur aam raftaar se kahein."),
}

ADL_LABELS = {
    "dressing": ("Dressing", "کپڑے پہننا", "Kapray pehnna"),
    "feeding": ("Feeding", "کھانا کھانا", "Khana khana"),
    "grooming": ("Grooming", "بال سنوارنا، دانت صاف کرنا یا ذاتی صفائی", "Baal sanwarna, daant saaf karna ya zaati safai"),
    "bathing": ("Bathing", "نہانا", "Nahana"),
    "writing": ("Writing", "لکھنا", "Likhna"),
    "phone_use": ("Phone use", "فون استعمال کرنا", "Phone istemal karna"),
    "walking": ("Walking", "چلنا", "Chalna"),
    "transfers": ("Transfers", "بیٹھنے، اٹھنے یا بستر سے کرسی پر جانے کی حرکت", "Baithne, uthne ya bistar se kursi par jane ki harkat"),
    "household_activities": ("Household activities", "گھر کے کام", "Ghar ke kaam"),
}
ADL_CHOICES = {
    0: ("No difficulty", "کوئی مشکل نہیں", "Koi mushkil nahi"),
    1: ("Slight difficulty", "تھوڑی مشکل", "Thori mushkil"),
    2: ("Moderate difficulty", "درمیانی مشکل", "Darmiyani mushkil"),
    3: ("A lot of difficulty", "بہت مشکل", "Bohat mushkil"),
    4: ("Unable without help", "مدد کے بغیر نہیں ہو سکا", "Madad ke baghair nahi ho saka"),
}

HUB_CARDS = {
    "gait": (("Walking / Gait", "چلنا اور مڑنا", "Chalna aur murna"), ("Walking and turning with a dedicated lower-body motion view.", "چلنے اور مڑنے کے دوران ٹانگوں کی حرکت کا منظر۔", "Chalne aur murnay ke dauran tangon ki harkat ka view.")),
    "hand": (("Hand / Finger", "ہاتھ اور انگلی", "Haath aur ungli"), ("Left and right tapping, and hand opening / closing.", "بائیں اور دائیں ہاتھ کی انگلی ملانا، ہاتھ کھولنا اور بند کرنا۔", "Baen aur daen haath ki ungli milana, haath kholna aur band karna.")),
    "transfer": (("Sit-to-Stand", "بیٹھنے سے کھڑا ہونا", "Baithne se khara hona"), ("A separate view of the seated-to-standing transition.", "بیٹھنے سے کھڑا ہونے کی حرکت کا الگ منظر۔", "Baithne se khara hone ki harkat ka alag view.")),
    "reach": (("Reach / Grasp", "ہاتھ بڑھانا اور چیز پکڑنا", "Haath barhana aur cheez pakarna"), ("Reach, grasp and object transfer tasks.", "ہاتھ بڑھانا، چیز پکڑنا اور دوسری جگہ رکھنا۔", "Haath barhana, cheez pakarna aur doosri jagah rakhna.")),
    "voice": (("Voice / Speech", "آواز اور گفتگو", "Aawaz aur guftagu"), ("A sustained vowel, fixed sentence or natural speech.", "مسلسل آ کی آواز، مقررہ جملہ یا عام گفتگو۔", "Musalsal aa ki aawaz, muqarrara jumla ya aam guftagu.")),
    "adl": (("Daily Activities", "روزمرہ کے کام", "Rozmarra ke kaam"), ("Tell your care team about everyday activities.", "نگہداشت کی ٹیم کو روزمرہ کے کاموں کے بارے میں بتائیں۔", "Dekh bhaal ki team ko rozmarra ke kaamon ke bare mein batayein.")),
    "touch": (("Spiral & tapping", "اسپائرل اور ٹیپنگ", "Spiral aur tapping"), ("Draw a spiral and tap two circles on this screen.", "اسکرین پر اسپائرل بنائیں اور دو دائروں کو چھوئیں۔", "Screen par spiral banayein aur do daairon ko chhoein.")),
}


def resolved_language(language):
    """Keep unsupported preferences honest; never silently claim a translation."""
    normalized = str(language or "English").strip().lower().replace("_", " ")
    aliases = {"en": "English", "english": "English", "ur": "Urdu", "urdu": "Urdu", "roman": "Roman Urdu", "roman urdu": "Roman Urdu"}
    return aliases.get(normalized, "English")


def _pick(values, language):
    return values[SUPPORTED_LANGUAGES.index(resolved_language(language))]


def text(key, language="English", **values):
    return _pick(COPY[key], language).format(**values)


def task_label(task, language="English"):
    return _pick(TASK_LABELS[task], language) if task in TASK_LABELS else str(task).replace("_", " ").title()


def task_steps(task, language="English"):
    return _pick(TASK_STEPS[task], language)


def voice_prompt(task, language="English"):
    return _pick(VOICE_PROMPTS[task], language)


def adl_label(key, language="English"):
    return _pick(ADL_LABELS[key], language)


def adl_choice(value, language="English"):
    return _pick(ADL_CHOICES[value], language)


def hub_card(key, language="English"):
    title, detail = HUB_CARDS[key]
    return _pick(title, language), _pick(detail, language)


def camera_translations(language="English"):
    """Only public streamlit-webrtc translation keys are supplied."""
    return {key: _pick(values, language) for key, values in CAMERA_COPY.items()}


def prose_html(value, language="English", *, ordered=False):
    """Escaped local prose has an explicit reading direction and language."""
    resolved = resolved_language(language)
    lang = {"English": "en", "Urdu": "ur", "Roman Urdu": "ur-Latn"}[resolved]
    direction = "rtl" if resolved == "Urdu" else "ltr"
    content = "<ol>" + "".join(f"<li>{escape(str(step))}</li>" for step in value) + "</ol>" if ordered else f"<p>{escape(str(value))}</p>"
    return f'<div class="ps-patient-copy" lang="{lang}" dir="{direction}">{content}</div>'


def write_patient(value, language="English"):
    st.markdown(prose_html(value, language), unsafe_allow_html=True)


def render_steps(task, language="English"):
    st.markdown(prose_html(task_steps(task, language), language, ordered=True), unsafe_allow_html=True)


def configure_patient_language(language):
    """Mark the patient surface for local RTL CSS without changing graph axes."""
    resolved = resolved_language(language)
    code = {"English": "en", "Urdu": "ur", "Roman Urdu": "ur-Latn"}[resolved]
    st.markdown(f'<span class="ps-patient-locale" lang="{code}" aria-hidden="true"></span>', unsafe_allow_html=True)
    if str(language or "English").strip().lower().replace("_", " ") not in {"english", "en", "urdu", "ur", "roman urdu", "roman"}:
        st.caption("Patient instructions are shown in English for this language preference. English, Urdu and Roman Urdu are available in Profile.")
    return resolved


WEEKDAYS = (
    ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    ("پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ", "اتوار"),
    ("Peer", "Mangal", "Budh", "Jumeraat", "Juma", "Hafta", "Itwaar"),
)


def weekday_name(day, language="English"):
    """Short weekday name; Monday is 0."""
    return _pick(WEEKDAYS, language)[day]
