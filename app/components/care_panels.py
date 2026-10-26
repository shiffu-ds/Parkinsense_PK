"""Patient words, personal goals and clinician-authored follow-up.

These panels intentionally keep self-reported experiences apart from movement
measurements. No rating is a diagnostic scale or an automated recommendation.
Authorization and consent are enforced by the care service on every request.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from backend.services import care

from .design import empty_state, plain_text, section_header, status_pill


_RATINGS = {
    "energy": ("Energy", ["Very low", "Low", "Some energy", "Good", "Very good"]),
    "sleep_quality": ("Sleep last night", ["Very poor", "Poor", "Mixed", "Good", "Restful"]),
    "movement_ease": ("Ease of everyday movement", ["Very difficult", "Difficult", "Mixed", "Comfortable", "Very comfortable"]),
    "mood": ("Mood", ["Very low", "Low", "Mixed", "Good", "Very good"]),
}
_GOAL_STATUSES = {"active": "In progress", "completed": "Completed", "paused": "Paused"}

# Patient-side copy in Urdu script and Roman Urdu. Staff screens stay English.
_RATINGS_LOCAL = {
    "Urdu": {
        "energy": ("توانائی", ["بہت کم", "کم", "کچھ توانائی", "اچھی", "بہت اچھی"]),
        "sleep_quality": ("گزشتہ رات کی نیند", ["بہت خراب", "خراب", "ملی جلی", "اچھی", "پرسکون"]),
        "movement_ease": ("روزمرہ حرکت میں آسانی", ["بہت مشکل", "مشکل", "ملی جلی", "آرام دہ", "بہت آرام دہ"]),
        "mood": ("مزاج", ["بہت اداس", "اداس", "ملا جلا", "اچھا", "بہت اچھا"]),
    },
    "Roman Urdu": {
        "energy": ("Energy (taqat)", ["Bohat kam", "Kam", "Kuch taqat", "Achhi", "Bohat achhi"]),
        "sleep_quality": ("Pichhli raat ki neend", ["Bohat kharab", "Kharab", "Mili juli", "Achhi", "Pur-sukoon"]),
        "movement_ease": ("Rozmarra harkat mein aasani", ["Bohat mushkil", "Mushkil", "Mili juli", "Aaram deh", "Bohat aaram deh"]),
        "mood": ("Mood (mizaaj)", ["Bohat udaas", "Udaas", "Mila jula", "Achha", "Bohat achha"]),
    },
}
_COPY = {
    "between": ("Between visits", "دو جانچوں کے درمیان", "Do jaizon ke darmiyan"),
    "between_detail": ("A few details from your day, and the people helping you make sense of them.",
                       "آپ کے دن کی چند باتیں، اور وہ لوگ جو انہیں سمجھنے میں آپ کی مدد کرتے ہیں۔",
                       "Aap ke din ki chand baatein, aur woh log jo inhein samajhne mein aap ki madad karte hain."),
    "tab_checkin": ("Daily check-in", "روزانہ حال", "Rozana haal"),
    "tab_goals": ("My goals", "میرے مقصد", "Mere maqsad"),
    "tab_followup": ("Care team follow-up", "نگہداشت کی ٹیم کا فالو اپ", "Care team ka follow-up"),
    "checkin_caption": ("A short record of how your day felt. Your own words help your care team understand the recordings.",
                        "آپ کا دن کیسا گزرا، اس کا مختصر ریکارڈ۔ آپ کے اپنے الفاظ ٹیم کو ریکارڈنگ سمجھنے میں مدد دیتے ہیں۔",
                        "Aaj ka din kaisa raha? Jo aap ne mehsoos kiya, woh yahan likh dein. Aap ke apne alfaaz team ki madad karte hain."),
    "day": ("Day of check-in", "کس دن کا حال", "Kis din ka haal"),
    "choose": ("Choose your answer", "جواب منتخب کریں", "Jawab chunein"),
    "falls": ("Any falls on this day? (optional)", "کیا اس دن آپ گرے؟ (اختیاری)", "Kya is din aap giray? (ikhtiyari)"),
    "fall_yes": ("Yes, a fall", "ہاں، گرا یا گری", "Haan, gira ya giri"),
    "fall_no": ("No falls", "نہیں گرا یا گری", "Nahi gira ya giri"),
    "fall_blank": ("Leave blank if unknown", "معلوم نہ ہو تو خالی چھوڑ دیں", "Maloom na ho to khali chhor dein"),
    "note": ("Anything you'd like your care team to know?", "اپنی ٹیم کو کچھ بتانا چاہیں؟", "Apni team ko kuch batana chahein?"),
    "note_hint": ("For example, an activity that felt easier or a question for your next visit.",
                  "مثلاً کوئی کام جو آسان لگا، یا اگلی ملاقات کے لیے سوال۔",
                  "Maslan koi kaam jo aasaan laga, ya agli mulaqat ke liye sawal."),
    "form_caption": ("Choose all four answers. A second check-in for the same day updates that day's entry. These questions do not produce a clinical score.",
                     "چاروں جواب منتخب کریں۔ اسی دن دوبارہ محفوظ کرنے سے اسی دن کا حال بدل جاتا ہے۔ ان سوالات سے کوئی طبی اسکور نہیں بنتا۔",
                     "Charon jawab chunein. Usi din dobara save karne se usi din ka haal badal jata hai. In sawalat se koi tibbi score nahi banta."),
    "save": ("Save daily check-in", "روزانہ حال محفوظ کریں", "Rozana haal save karein"),
    "saved": ("Check-in saved. Your care team can read it alongside your assessments.",
              "حال محفوظ ہو گیا۔ آپ کی ٹیم اسے آپ کی جانچوں کے ساتھ پڑھ سکتی ہے۔",
              "Haal save ho gaya. Aap ki team ise aap ke jaizon ke saath parh sakti hai."),
    "no_checkins": ("No check-ins yet", "ابھی کوئی حال درج نہیں", "Abhi koi haal darj nahi"),
    "no_checkins_detail": ("When a day feels different, a short note can help you remember it at your next visit.",
                           "جب کوئی دن مختلف لگے تو ایک مختصر نوٹ اگلی ملاقات پر یاد دلانے میں مدد دیتا ہے۔",
                           "Jab koi din mukhtalif lage to aik mukhtasar note agli mulaqat par yaad dilane mein madad deta hai."),
    "latest": ("Latest check-in", "تازہ حال", "Taza haal"),
    "experience": ("Experience", "تجربہ", "Tajurba"),
    "answer": ("Answer", "جواب", "Jawab"),
    "falls_row": ("Falls", "گرنا", "Girna"),
    "not_recorded": ("Not recorded", "درج نہیں", "Darj nahi"),
    "fell": ("Reported a fall", "گرنے کا بتایا", "Girne ka bataya"),
    "no_fall": ("No falls reported", "گرنے کا نہیں بتایا", "Girne ka nahi bataya"),
    "goals_title": ("What matters to you", "آپ کے لیے کیا اہم ہے", "Aap ke liye kya ahem hai"),
    "goals_detail": ("Everyday priorities, written by the patient. Goals stay separate from measured results.",
                     "روزمرہ کی ترجیحات، آپ کے اپنے الفاظ میں۔ مقصد پیمائش سے الگ رہتے ہیں۔",
                     "Rozmarra ki tarjeehat, aap ke apne alfaaz mein. Maqsad pemaish se alag rehte hain."),
    "no_goals": ("No personal goals saved", "ابھی کوئی مقصد نہیں", "Abhi koi maqsad nahi"),
    "no_goals_detail": ("A goal can be small: an everyday activity you'd like to feel more confident doing.",
                        "مقصد چھوٹا بھی ہو سکتا ہے: کوئی روزمرہ کام جسے آپ زیادہ اعتماد سے کرنا چاہیں۔",
                        "Maqsad chhota bhi ho sakta hai: koi rozmarra kaam jise aap zyada aitmaad se karna chahein."),
    "goal_status": ("Goal status", "مقصد کی حالت", "Maqsad ki haalat"),
    "update_goal": ("Update goal", "مقصد اپ ڈیٹ کریں", "Maqsad update karein"),
    "add_goal": ("Add a personal goal", "نیا مقصد لکھیں", "Naya maqsad likhein"),
    "goal_label": ("An activity or priority that matters to you", "کوئی کام یا ترجیح جو آپ کے لیے اہم ہو", "Koi kaam ya tarjeeh jo aap ke liye ahem ho"),
    "goal_hint": ("For example, feeling more comfortable getting dressed.", "مثلاً کپڑے پہنتے وقت زیادہ آرام محسوس کرنا۔", "Maslan kapre pehante waqt zyada aaram mehsoos karna."),
    "goal_detail": ("A little more detail (optional)", "تھوڑی اور تفصیل (اختیاری)", "Thori aur tafseel (ikhtiyari)"),
    "goal_detail_hint": ("What would make a difference in your day?", "آپ کے دن میں کیا فرق لائے گا؟", "Aap ke din mein kya farq laye ga?"),
    "save_goal": ("Save personal goal", "مقصد محفوظ کریں", "Maqsad save karein"),
    "plan_empty": ("A place for your care team's follow-up", "آپ کی ٹیم کے فالو اپ کی جگہ", "Aap ki team ke follow-up ki jagah"),
    "plan_empty_detail": ("Your assigned clinician can leave a note, agreed priorities and a date to review them. No automated care plan is created.",
                          "آپ کا معالج یہاں نوٹ، طے شدہ ترجیحات اور جائزے کی تاریخ لکھ سکتا ہے۔ کوئی خودکار منصوبہ نہیں بنتا۔",
                          "Aap ka moalij yahan note, tay shuda tarjeehat aur review ki tareekh likh sakta hai. Koi khudkar mansooba nahi banta."),
}
_GOAL_LOCAL = {"Urdu": {"active": "جاری", "completed": "مکمل", "paused": "رکا ہوا"},
               "Roman Urdu": {"active": "Jari", "completed": "Mukammal", "paused": "Ruka hua"}}
_INDEX = {"English": 0, "Urdu": 1, "Roman Urdu": 2}


def _lang(user, clinician=False):
    language = user.get("language") if user.get("role") == "patient" and not clinician else "English"
    return language if language in _INDEX else "English"


def _c(key, language="English"):
    return _COPY[key][_INDEX.get(language, 0)]


def _ratings(language="English"):
    return _RATINGS_LOCAL.get(language, _RATINGS)


def _today():
    return datetime.now(ZoneInfo("Asia/Karachi")).date()


def _date_label(value):
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return "Date unavailable"


def _record_checkin(user, patient_id, *, clinician=False):
    prefix = f"checkin_{patient_id}"
    lang = _lang(user, clinician)
    caption = (
        "Record the patient's own answers. These are experiences they report, separate from recorded movement."
        if clinician else _c("checkin_caption", lang)
    )
    st.caption(caption)
    with st.form(prefix, clear_on_submit=True):
        day = st.date_input(_c("day", lang), value=_today(), max_value=_today(), key=f"{prefix}_date")
        responses = {}
        columns = st.columns(2)
        for index, (key, (label, values)) in enumerate(_ratings(lang).items()):
            with columns[index % 2]:
                responses[key] = st.selectbox(
                    label,
                    list(range(5)),
                    index=None,
                    format_func=lambda value, choices=values: choices[value],
                    placeholder=_c("choose", lang) if not clinician else "Choose the patient's answer",
                    key=f"{prefix}_{key}",
                )
        responses["falls"] = st.selectbox(
            _c("falls", lang),
            [False, True],
            index=None,
            format_func=lambda value: _c("fall_yes", lang) if value else _c("fall_no", lang),
            placeholder=_c("fall_blank", lang),
            key=f"{prefix}_falls",
        )
        responses["note"] = st.text_area(
            _c("note", lang) if not clinician else "Patient's words / relevant context",
            max_chars=2000,
            placeholder=_c("note_hint", lang),
            key=f"{prefix}_note",
        )
        from backend.db.context_models import HELPERS
        from .patient_language import text
        responses["helper"] = st.selectbox(
            text("checkin_helper", lang) if not clinician else "Did someone help the patient fill this in? (optional)",
            list(HELPERS), index=None, placeholder=_c("fall_blank", lang),
            format_func=lambda value: text(f"helper_{value}", lang), key=f"{prefix}_helper",
        )
        st.caption(_c("form_caption", lang))
        if st.form_submit_button(_c("save", lang), type="primary"):
            try:
                care.save_checkin(user["id"], {**responses, "date": day.isoformat()}, patient_id=patient_id)
                st.success(_c("saved", lang))
            except (ValueError, PermissionError, LookupError) as exc:
                st.error(str(exc))


def _checkin_history(records, lang="English"):
    if not records:
        empty_state(_c("no_checkins", lang), _c("no_checkins_detail", lang))
        return
    latest = records[0]
    with st.container(border=True):
        st.write(f"**{_c('latest', lang)}: {_date_label(latest['date'])}**")
        status_pill("Patient self-report")
        responses = latest["responses"]
        rows = []
        experience, answer = _c("experience", lang), _c("answer", lang)
        for key, (label, choices) in _ratings(lang).items():
            value = responses.get(key)
            rows.append({experience: label, answer: choices[value] if isinstance(value, int) and 0 <= value <= 4 else _c("not_recorded", lang)})
        falls = responses.get("falls")
        rows.append({experience: _c("falls_row", lang), answer: _c("not_recorded", lang) if falls is None else (_c("fell", lang) if falls else _c("no_fall", lang))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if responses.get("note"):
            st.write(plain_text(responses["note"]))
        if responses.get("helper") and responses["helper"] != "alone":
            from .patient_language import text
            st.caption(text("helped_by", lang, helper=text(f"helper_{responses['helper']}", lang)))
        st.caption(f"Recorded by {plain_text(latest['author_name'])} · {_date_label(latest.get('updated_at', latest.get('created_at')))}")
    if len(records) > 1:
        with st.expander(f"Earlier check-ins ({len(records) - 1})"):
            for item in records[1:]:
                values = item["responses"]
                st.write(f"**{_date_label(item['date'])}**")
                labels = []
                for key, (label, choices) in _ratings(lang).items():
                    value = values.get(key)
                    if isinstance(value, int) and 0 <= value <= 4:
                        labels.append(f"{label}: {choices[value]}")
                st.caption(" · ".join(labels))
                if values.get("falls") is True:
                    st.write("Patient reported a fall.")
                if values.get("note"):
                    st.write(plain_text(values["note"]))
                st.divider()


def _goals(user, patient_id, *, editable):
    lang = _lang(user, not editable)
    statuses = _GOAL_LOCAL.get(lang, _GOAL_STATUSES)
    records = care.list_goals(user["id"], patient_id=patient_id)
    section_header(_c("goals_title", lang) if editable else "The patient's personal goals", _c("goals_detail", lang))
    if not records:
        empty_state(_c("no_goals", lang), _c("no_goals_detail", lang) if editable else "The patient can add priorities from their Check-in & goals page.")
    for goal in records:
        with st.container(border=True):
            st.write(f"**{plain_text(goal['label'])}**")
            status_pill(statuses.get(goal["status"], "Status unavailable"), "care" if goal["status"] == "completed" else "neutral")
            if goal.get("detail"):
                st.write(plain_text(goal["detail"]))
            st.caption(f"Written by {plain_text(goal['author_name'])} · {_date_label(goal['created_at'])}")
            if editable:
                with st.form(f"goal_update_{goal['id']}"):
                    status = st.selectbox(_c("goal_status", lang), list(_GOAL_STATUSES), index=list(_GOAL_STATUSES).index(goal["status"]), format_func=statuses.get, key=f"goal_status_{goal['id']}")
                    if st.form_submit_button(_c("update_goal", lang)):
                        try:
                            care.update_goal(user["id"], goal["id"], status=status)
                            st.rerun()
                        except (ValueError, PermissionError, LookupError) as exc:
                            st.error(str(exc))
    if editable:
        with st.expander(_c("add_goal", lang), expanded=not records):
            with st.form(f"new_goal_{patient_id}", clear_on_submit=True):
                label = st.text_input(_c("goal_label", lang), max_chars=160, placeholder=_c("goal_hint", lang))
                detail = st.text_area(_c("goal_detail", lang), max_chars=1000, placeholder=_c("goal_detail_hint", lang))
                if st.form_submit_button(_c("save_goal", lang)):
                    try:
                        care.save_personal_goal(user["id"], label, detail=detail, patient_id=patient_id)
                        st.rerun()
                    except (ValueError, PermissionError, LookupError) as exc:
                        st.error(str(exc))


def _care_plan_records(records, lang="English"):
    if not records:
        empty_state(_c("plan_empty", lang), _c("plan_empty_detail", lang))
        return
    for index, plan in enumerate(records):
        with st.container(border=True) if index == 0 else st.expander(f"Earlier follow-up · {_date_label(plan['created_at'])}"):
            st.write(f"**{plain_text(plan['focus'])}**")
            status_pill("Clinician-written follow-up", "care")
            st.write(plain_text(plan["notes"]))
            st.caption(f"Written by {plain_text(plan['author_name'])} · {_date_label(plan['created_at'])}")
            if plan.get("next_review_date"):
                st.caption(f"Planned review: {_date_label(plan['next_review_date'])}")
                st.caption("This is a review date recorded by your clinician, rather than a booked appointment.")


def patient_care_panel(user):
    """Render a patient's daily check-in, own goals and assigned team notes."""
    patient_id = user["patient_id"]
    lang = _lang(user)
    section_header(_c("between", lang), _c("between_detail", lang))
    from .diary_panel import diary_panel
    from .patient_language import text
    checkin, medicine, goals, followup = st.tabs([_c("tab_checkin", lang), text("diary_tab", lang),
                                                  _c("tab_goals", lang), _c("tab_followup", lang)])
    with checkin:
        _record_checkin(user, patient_id)
        _checkin_history(care.list_checkins(user["id"], patient_id=patient_id), lang)
    with medicine:
        diary_panel(user, lang, key=f"diary_{patient_id}")
    with goals:
        _goals(user, patient_id, editable=True)
    with followup:
        _care_plan_records(care.list_care_plans(user["id"], patient_id=patient_id), lang)


def _task_plan_form(user, patient_id):
    """A linked clinician suggests which task groups to do on which weekdays."""
    from backend.db.context_models import PLAN_GROUPS
    from backend.services import task_plan
    from .patient_language import hub_card, weekday_name
    current = task_plan.get_task_plan(user["id"], patient_id)
    schedule = current["schedule"] if current else {}
    st.caption("Suggest which tasks the patient does on which days. Today's tasks appear on their Home page and "
               "task cards. This is a suggestion, not a prescription; leave every row empty to clear the plan.")
    with st.form(f"task_plan_{patient_id}"):
        chosen = {group: st.multiselect(hub_card(group)[0], list(range(7)), default=schedule.get(group, []),
                                        format_func=weekday_name, key=f"plan_days_{patient_id}_{group}")
                  for group in PLAN_GROUPS}
        note = st.text_input("Note for the patient (optional)", value=current["note"] if current else "", max_chars=500,
                             key=f"plan_note_{patient_id}")
        if st.form_submit_button("Save weekly plan", type="primary"):
            try:
                task_plan.save_task_plan(user["id"], patient_id, chosen, note=note)
                st.success("Plan saved. The patient sees today's tasks on their Home page.")
            except (ValueError, PermissionError, LookupError) as exc:
                st.error(str(exc))


def clinician_care_panel(user, patient_id):
    """Render authorized patient context and a human-authored care note form."""
    section_header("Patient context & follow-up", "The patient's daily experiences and priorities help give recordings their context.")
    from .diary_panel import diary_panel
    experiences, medicine, goals, followup, weekly = st.tabs(["Patient check-ins", "Medicine diary", "Personal goals",
                                                              "Care team follow-up", "Weekly task plan"])
    with weekly:
        _task_plan_form(user, patient_id)
    with experiences:
        _checkin_history(care.list_checkins(user["id"], patient_id=patient_id))
        with st.expander("Record answers shared by the patient"):
            _record_checkin(user, patient_id, clinician=True)
    with medicine:
        diary_panel(user, key=f"clinician_diary_{patient_id}", patient_id=patient_id, clinician=True)
    with goals:
        _goals(user, patient_id, editable=False)
    with followup:
        with st.form(f"care_followup_{patient_id}", clear_on_submit=True):
            st.caption("Write the follow-up you discussed with the patient. Your name will appear with the note.")
            focus = st.text_input("Focus for follow-up", max_chars=160, placeholder="Agreed priority for the next review")
            notes = st.text_area("Care team note", max_chars=3000, placeholder="Record the discussion, agreed next steps and questions to revisit.")
            review_date = st.date_input("Planned review date (optional)", value=None)
            if st.form_submit_button("Save care team follow-up", type="primary"):
                try:
                    care.save_care_plan(user["id"], patient_id, focus, notes, next_review_date=review_date.isoformat() if review_date else None)
                    st.success("Follow-up saved with your name. It is visible to the patient and their assigned care team.")
                except (ValueError, PermissionError, LookupError) as exc:
                    st.error(str(exc))
        _care_plan_records(care.list_care_plans(user["id"], patient_id=patient_id))
