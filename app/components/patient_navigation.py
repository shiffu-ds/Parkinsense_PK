"""Patient navigation copy; callable page routes stay unchanged."""

LABELS = {
    "My care": ("میری نگہداشت", "Meri care"), "Home": ("ابتدائی صفحہ", "Home"),
    "My Care": ("میری نگہداشت", "Meri care"), "Start Assessment": ("جانچ شروع کریں", "Jaiza shuru karein"),
    "Movement": ("حرکت", "Harkat"), "3D Movement Studio": ("سہ جہتی حرکت کا منظر", "3D movement studio"),
    "Walking / Gait": ("چلنا", "Chalna"), "Hand / Finger": ("ہاتھ اور انگلی", "Haath aur ungli"),
    "Sit-to-Stand": ("بیٹھنا اور کھڑا ہونا", "Baithna aur khara hona"), "Reach / Grasp": ("پہنچنا اور پکڑنا", "Pohanchna aur pakarna"),
    "Voice and daily life": ("آواز اور روزمرہ زندگی", "Aawaz aur rozmarra zindagi"),
    "Voice / Speech": ("آواز اور گفتگو", "Aawaz aur guftagu"), "ADL Questionnaire": ("روزمرہ کاموں کے سوالات", "Rozmarra kaamon ke sawalat"),
    "My history": ("میرا سابقہ ریکارڈ", "Mera pichla record"), "My Results": ("میرے نتائج", "Mere nataij"),
    "Progress": ("وقت کے ساتھ تبدیلی", "Waqt ke saath tabdeeli"), "Reports": ("رپورٹس", "Reports"),
    "Profile": ("میری معلومات", "Meri maloomat"), "Data & privacy": ("ڈیٹا اور رازداری", "Data aur privacy"),
    "Log out": ("لاگ آؤٹ", "Log out"),
}


def navigation_label(label, user):
    if user and user.get("role") == "patient" and user.get("language") in {"Urdu", "Roman Urdu"}:
        translated = LABELS.get(label)
        if translated:
            return translated[0 if user["language"] == "Urdu" else 1]
    return label
