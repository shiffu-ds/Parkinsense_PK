"""Plain-language data handling and patient control over monitoring consent."""

import streamlit as st

from app.components.design import section_header
from app.components.patient_language import write_patient
from app.components.validation_review import validation_participation_panel
from app.components.clinic_pilot import pilot_participation_panel
from backend import services
from backend.services import privacy as api

COPY = {
    "title": ("Data & privacy", "ڈیٹا اور رازداری", "Data aur privacy"),
    "handling": ("Your recordings, measurements, responses and care notes are stored in this workspace's private media folder and database. Your account and assigned clinicians can access your clinical records; administrators manage accounts and data requests. Short-lived recording/download links check permission again when opened. No external AI or transcription provider receives recordings in this local workflow.",
                 "آپ کی ریکارڈنگ، پیمائش، جوابات اور نگہداشت کے نوٹس اس نظام کے نجی فولڈر اور ڈیٹابیس میں محفوظ ہیں۔ آپ اور مقررہ معالج طبی ریکارڈ دیکھ سکتے ہیں؛ منتظم اکاؤنٹس اور ڈیٹا کی درخواستیں سنبھالتا ہے۔ عارضی لنک کھولتے وقت اجازت دوبارہ دیکھی جاتی ہے۔ اس مقامی طریقے میں ریکارڈنگ کسی بیرونی AI یا آواز لکھنے کی سروس کو نہیں بھیجی جاتی۔",
                 "Aap ki recordings, measurements, jawabat aur care notes is workspace ke private folder aur database mein save hain. Aap aur assigned clinicians clinical records dekh sakte hain; admin accounts aur data requests sambhalta hai. Aarzi links kholte waqt permission dobara check hoti hai. Is local workflow mein recording kisi bahari AI ya transcription service ko nahi bheji jati."),
    "retention": ("Records currently remain stored until the operator reviews a data request; automatic deletion and a fixed retention schedule are not enabled. Encrypted backups are created by an operator, not scheduled automatically. Erasure needs a documented review of live records, generated exports and retained backups. A request does not immediately delete data.",
                  "ریکارڈ منتظم کے جائزے تک محفوظ رہتا ہے؛ خودکار حذف یا مقررہ مدت ابھی فعال نہیں۔ رمز شدہ بیک اپ منتظم بناتا ہے، خودکار شیڈول نہیں۔ حذف کی درخواست میں اصل ریکارڈ، برآمد شدہ فائلیں اور بیک اپ کا جائزہ ضروری ہے۔ درخواست دینے سے ڈیٹا فوراً حذف نہیں ہوتا۔",
                  "Records operator ke review tak save rehte hain; automatic deletion aur fixed retention schedule abhi enabled nahi. Encrypted backup operator banata hai, khudkar schedule nahi. Erasure ke liye asal records, exports aur backups ka documented review chahiye. Request dene se data foran delete nahi hota."),
    "withdraw": ("Withdraw monitoring consent", "نگرانی کی رضامندی واپس لیں", "Monitoring ki razamandi wapas lein"),
    "resume": ("I consent to storing recordings and responses for monitoring and review by my assigned care team.",
               "میں نگرانی اور اپنے مقررہ معالج کے جائزے کے لیے ریکارڈنگ اور جوابات محفوظ کرنے کی رضامندی دیتا/دیتی ہوں۔",
               "Main monitoring aur apni assigned care team ke review ke liye recordings aur jawabat save karne ki razamandi deta/deti hoon."),
    "inactive": ("Monitoring consent is withdrawn. New analysis saves and recording links are blocked. Existing records remain stored while a data request is reviewed.",
                 "نگرانی کی رضامندی واپس لے لی گئی ہے۔ نیا تجزیہ محفوظ کرنا اور ریکارڈنگ کے لنک بند ہیں۔ ڈیٹا کی درخواست کے جائزے تک پرانا ریکارڈ محفوظ ہے۔",
                 "Monitoring ki razamandi wapas le li gayi hai. Naya analysis save karna aur recording links band hain. Data request ke review tak puranay records save hain."),
    "request": ("Request access, a full export or erasure", "رسائی، مکمل برآمد یا حذف کی درخواست", "Access, mukammal export ya erasure ki request"),
    "send": ("Record data request", "ڈیٹا کی درخواست محفوظ کریں", "Data request save karein"),
}


def _copy(key, language):
    return COPY[key][{"English": 0, "Urdu": 1, "Roman Urdu": 2}.get(language, 0)]


def _clear_private_links():
    for key in list(st.session_state):
        if key.startswith(("private_player_", "private_download_")):
            st.session_state.pop(key, None)


def data_privacy_page():
    user = services.get_user(st.session_state.user_id)
    language = user.get("language", "English")
    section_header(_copy("title", language))
    write_patient(_copy("handling", language), language)
    write_patient(_copy("retention", language), language)
    status = api.monitoring_status(user["id"])
    if status["active"]:
        if st.button(_copy("withdraw", language), key="withdraw_monitoring"):
            api.set_monitoring_consent(user["id"], acknowledged=False)
            _clear_private_links()
            st.rerun()
    else:
        st.info(_copy("inactive", language))
        with st.form("resume_monitoring"):
            agree = st.checkbox(_copy("resume", language))
            if st.form_submit_button("Resume monitoring" if language == "English" else "نگرانی دوبارہ شروع کریں" if language == "Urdu" else "Monitoring dobara shuru karein"):
                if agree:
                    api.set_monitoring_consent(user["id"], acknowledged=True)
                    _clear_private_links()
                    st.rerun()
                else:
                    st.error(_copy("resume", language))
    with st.form("data_request"):
        st.write(_copy("request", language))
        labels = {"access": ("Access review", "رسائی کا جائزہ", "Access ka review"),
                  "export": ("Full data export", "مکمل ڈیٹا کی برآمد", "Mukammal data export"),
                  "erasure": ("Erasure review", "حذف کا جائزہ", "Erasure ka review")}
        index = {"Urdu": 1, "Roman Urdu": 2}.get(language, 0)
        kind = st.selectbox(_copy("request", language), list(labels), format_func=lambda k: labels[k][index])
        if st.form_submit_button(_copy("send", language)):
            api.create_data_request(user["id"], kind)
            st.rerun()
    requests = api.list_data_requests(user["id"])
    if requests:
        st.dataframe([{k: r[k] for k in ("kind", "status", "created_at", "handled_at")} for r in requests], hide_index=True, width="stretch")
    pilot_participation_panel(user)
    validation_participation_panel(user)


def data_requests_page():
    user = services.get_user(st.session_state.user_id)
    rows = api.list_data_requests(user["id"])
    section_header("Data requests", "Review and fulfil requests through the documented operator process. This queue does not delete or export clinical records.")
    st.caption("Set resolved only after documenting fulfilment, including retained backup handling, outside this queue. No automatic email or erasure is triggered.")
    if not rows:
        st.info("No patient data requests.")
        return
    st.dataframe(rows, hide_index=True, width="stretch")
    row = st.selectbox("Request", rows, format_func=lambda r: f"{r['kind']} · {r['id']} · {r['status']}")
    status = st.selectbox("Operator status", ["received", "reviewing", "resolved", "declined"])
    if st.button("Update request status"):
        api.update_request_status(user["id"], row["id"], status)
        st.rerun()
