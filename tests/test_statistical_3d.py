"""Synthetic graph fixtures check truthful encoding, not clinical validation."""
from __future__ import annotations

from copy import deepcopy
import json
import math

import pytest
from streamlit.testing.v1 import AppTest

from app.components.statistical_3d import build_module_statistics_figure, module_statistics_groups
from ml.common.statistics import bounded_curve, descriptive_rows, measurement_definition, measurements, recording_curves
from ml.nlp.functional import analyze_text
from ml.tabular.adl import ADL_ITEMS, analyze_adl

MOVEMENT = ("gait", "turning", "finger_left", "finger_right", "hand_open_close", "sit_to_stand", "reach", "grasp", "object_transfer")


def movement_result(task="gait"):
    # Manually constructed unit-test values, never detector output or a demo.
    return {"status": "completed", "task": task, "analysis_version": "test-proxies-v1",
            "quality": {"accepted": True, "decision": "ACCEPT"},
            "features": {"duration_s": 3.0, "angle": 90.0, "angle_second": 45.0, "cycles": 0.0},
            "feature_metadata": {"duration_s": {"label": "Duration", "unit": "seconds"},
                                 "angle": {"label": "Left knee", "unit": "degrees (estimated)"},
                                 "angle_second": {"label": "Right knee", "unit": "degrees (estimated)"},
                                 "cycles": {"label": "Cycle count", "unit": "cycles (proxy)"}},
            "curves": {"timestamp_s": [0, 0.1, 0.2, 0.3],
                       "left_knee_angle_deg_proxy": [80, 85, 90, 95],
                       "right_knee_angle_deg_proxy": [90, 91, 92, 93],
                       "ankle_separation_trunk_lengths_proxy": [0.1, 0.2, 0.1, 0]}}


def audio_result(task="voice_natural"):
    return {"status": "accepted", "task": task.replace("voice", "audio"), "method": "acoustic-features-1.0", "language": "urdu",
            "quality": {"accepted": True}, "features": {"duration_seconds": 5, "internal_pause_seconds": 0,
            "signal_rms_dbfs": -25, "signal_active_fraction": 0.8, "internal_pause_count": 0,
            "spectral_centroid_mean_hz": 210, "mfcc_01_mean": -16, "mfcc_13_mean": 0}}


@pytest.mark.parametrize("task", MOVEMENT)
def test_all_movement_modules_have_real_3d_curves_and_separate_units(task):
    result = movement_result(task)
    figure = build_module_statistics_figure(result, task)
    assert figure.layout.meta["available"] is True
    assert figure.layout.scene.xaxis.title.text == "Elapsed time (seconds)"
    assert figure.layout.scene.zaxis.title.text == "degrees (estimated)"
    assert all(trace.type == "scatter3d" for trace in figure.data)
    assert len(figure.data) == 2
    assert list(figure.data[0].z) == [80, 85, 90, 95]
    assert "trunk lengths (relative)" in module_statistics_groups(result, task)
    relative = build_module_statistics_figure(result, task, unit="trunk lengths (relative)")
    assert len(relative.data) == 1
    assert 0 in relative.data[0].z
    assert all(trace.connectgaps is False for trace in figure.data)
    json.loads(figure.to_json())


@pytest.mark.parametrize("task", ("voice_natural", "voice_vowel", "voice_sentence", "voice"))
def test_each_voice_module_uses_actual_native_unit_scalar_bars(task):
    result = audio_result(task)
    seconds = build_module_statistics_figure(result, task, unit="seconds")
    assert seconds.data[0].type == "mesh3d"
    assert list(seconds.data[-1].z) == [5.0, 0.0]
    assert "Local WAV measurement" in seconds.data[-1].customdata[0]
    decibels = build_module_statistics_figure(result, task, unit="dBFS")
    assert min(decibels.data[0].z) == -25
    assert list(decibels.data[-1].z) == [-25]
    assert recording_curves(result, task) == []
    assert len(decibels.data) == 2
    mfcc = build_module_statistics_figure(result, task, unit="log-mel DCT units")
    assert list(mfcc.data[-1].z) == [-16.0, 0.0]
    assert "Hz" in module_statistics_groups(result, task)


def test_adl_and_nlp_native_scales_sources_and_zero_meaning():
    adl = analyze_adl({key: i % 5 for i, key in enumerate(ADL_ITEMS)})
    figure = build_module_statistics_figure(adl, "adl")
    assert figure.layout.scene.zaxis.title.text == "difficulty rating (0–4)"
    assert len(figure.data[-1].z) == 10
    assert figure.data[-1].z[0] == 0
    assert all("Patient self-report" in row[2] for row in figure.data[-1].customdata)
    nlp = analyze_text("No falls, but walking is difficult.")
    figure = build_module_statistics_figure(nlp, "nlp", unit="rule match (0 or 1)")
    assert set(figure.data[-1].z) == {0, 1}
    assert all("Keyword rules" in row[2] for row in figure.data[-1].customdata)
    count = build_module_statistics_figure(nlp, "nlp", unit="matched domains (count)")
    assert list(count.data[-1].z) == [1.0]


@pytest.mark.parametrize("changes", [
    {"status": "repeat"}, {"status": "unknown"}, {"quality": {}},
    {"quality": {"accepted": False, "decision": "ACCEPT"}},
    {"quality": {"accepted": True, "decision": "REPEAT"}},
    {"quality": {"decision": "REJECT"}},
])
def test_quality_gating_applies_to_curves_and_features(changes):
    result = {**movement_result(), **changes}
    assert not build_module_statistics_figure(result, "gait").data
    assert not recording_curves(result, "gait")
    assert not measurements(result, "gait")


def test_missing_nonfinite_boolean_and_unknown_units_are_not_zero_or_mixed():
    result = audio_result()
    result["features"] = {"duration_seconds": float("nan"), "signal_rms_dbfs": float("inf"),
                          "internal_pause_count": False, "internal_pause_seconds": 0,
                          "unmapped_a": 17, "unmapped_b": 0}
    groups = module_statistics_groups(result, "voice_natural")
    assert groups == ["seconds", "Unit not specified · unmapped_a", "Unit not specified · unmapped_b"]
    figure = build_module_statistics_figure(result, "voice_natural", unit="seconds")
    assert list(figure.data[-1].z) == [0.0]
    assert len(figure.data) == 2
    figure = build_module_statistics_figure(result, "voice_natural", unit="Unit not specified · unmapped_a")
    assert list(figure.data[-1].z) == [17.0]
    missing = build_module_statistics_figure({"status": "accepted", "quality": {"accepted": True}, "features": {}}, "adl")
    assert not missing.data
    assert missing.layout.meta["available"] is False


def test_curve_gaps_survive_decimation_and_every_trace_stays_bounded():
    result = movement_result()
    times = [i * 0.1 for i in range(1500)]
    values = [float(i % 17) for i in range(len(times))]
    values[123] = None
    values[759] = float("nan")
    times[1000:] = [value + 5 for value in times[1000:]]
    result["curves"] = {"timestamp_s": times, "left_knee_angle_deg_proxy": values}
    figure = build_module_statistics_figure(result, "gait")
    trace = figure.data[0]
    assert len(trace.x) <= 300
    assert list(trace.x).count(None) == 3
    assert trace.connectgaps is False
    assert all(value is None or math.isfinite(value) for value in trace.z)
    rows = descriptive_rows(result, "gait", "degrees (estimated)", curves=True)
    assert rows[0]["Samples"] == 1498
    assert rows[0]["Minimum"] == 0
    json.loads(figure.to_json())


def test_many_gaps_and_malformed_curve_timestamps_are_safe():
    result = movement_result()
    result["curves"] = {"timestamp_s": [i * 0.1 for i in range(1000)],
                        "left_knee_angle_deg_proxy": [1 if i % 2 else None for i in range(1000)]}
    curve = recording_curves(result, "gait")[0]
    times, values = bounded_curve(curve)
    assert len(times) <= 300
    assert all(value == 1 or value is None for value in values)
    for timestamps in ([0, 0], [0, -1], [0, float("nan")], [0, True]):
        result["curves"] = {"timestamp_s": timestamps, "left_knee_angle_deg_proxy": [1, 2]}
        assert recording_curves(result, "gait") == []


def test_history_matches_alias_method_language_and_has_no_gap_connections():
    result = audio_result("voice_vowel")
    rejected = deepcopy(result)
    rejected["quality"]["accepted"] = False
    different_language = deepcopy(result)
    different_language["language"] = "english"
    different_method = deepcopy(result)
    different_method["method"] = "new-method"
    other_task = deepcopy(result)
    other_task["task"] = "audio_sentence"
    history = [
        {"id": "0", "created_at": "2026-01-01", "status": "completed", "modules": {"voice_vowel": result}},
        {"id": "1", "created_at": "2026-01-02", "status": "completed", "modules": {"voice_vowel": rejected}},
        {"id": "2", "created_at": "2026-01-03", "status": "completed", "modules": {"voice_vowel": different_language}},
        {"id": "3", "created_at": "2026-01-04", "status": "completed", "modules": {}},
        {"id": "4", "created_at": "2026-01-05", "status": "abandoned", "modules": {"voice_vowel": result}},
        {"id": "5", "created_at": "2026-01-06", "status": "completed", "modules": {"voice_vowel": different_method}},
        {"id": "6", "created_at": "2026-01-07", "status": "completed", "modules": {"voice_vowel": other_task}},
        {"id": "7", "created_at": "2026-01-08", "status": "completed", "modules": {"voice_vowel": result}},
    ]
    figure = build_module_statistics_figure(result, "voice_vowel", view="history", history=history, unit="seconds")
    assert all(trace.mode == "markers" for trace in figure.data)
    assert all(list(trace.x) == [0, 6] for trace in figure.data)
    assert all(trace.connectgaps is False for trace in figure.data)
    assert figure.layout.meta["empty_visits"] == 5
    assert figure.layout.meta["history_connections"] is False


def test_untrusted_labels_and_units_do_not_introduce_html_or_external_content():
    result = movement_result()
    result["feature_metadata"]["angle"] = {"label": '<img src="https://evil.test/x" onerror="alert(1)">',
                                             "unit": "<script>alert(1)</script>"}
    definition = measurement_definition(result, "angle", "gait")
    assert "<" not in definition["label"]
    figure = build_module_statistics_figure(result, "gait", view="measurements", unit=definition["unit"])
    assert "<script>" not in figure.to_json()
    assert "<img " not in figure.to_json()
    assert "&lt;" in definition["unit"]


def test_panel_runs_for_every_module_and_explains_self_report_sources():
    # Streamlit checks exercise all controls without touching patient storage.
    for task, result in [(task, movement_result(task)) for task in MOVEMENT] + [
        ("voice_natural", audio_result()), ("voice_vowel", audio_result("voice_vowel")),
        ("voice_sentence", audio_result("voice_sentence")),
        ("nlp", analyze_text("Walking is difficult")), ("adl", analyze_adl({key: 0 for key in ADL_ITEMS})),
    ]:
        app = AppTest.from_string("from app.components.statistical_3d import module_statistics_panel\nimport streamlit as st\nmodule_statistics_panel(st.session_state['result'], st.session_state['task'], identity='test')", default_timeout=20)
        app.session_state["task"] = task
        app.session_state["result"] = result
        app.run()
        assert not app.exception
        assert any(item.label == "Graph viewpoint" for item in app.selectbox)
        if task == "nlp":
            assert any("not confirmed absence" in item.value for item in app.caption)
        if task == "adl":
            assert any("unvalidated" in item.value for item in app.caption)


def test_overflow_values_are_omitted_and_long_unknown_units_do_not_collide():
    result = audio_result()
    first = "measurement_" + "x" * 200 + "first"
    second = "measurement_" + "x" * 200 + "second"
    result["features"] = {"duration_seconds": 10 ** 1000, first: 12, second: 20}
    rows = measurements(result, "voice_natural")
    assert len(rows) == 2
    assert rows[0].unit != rows[1].unit
    assert all(len(row.unit) < 110 for row in rows)
    for row in rows:
        figure = build_module_statistics_figure(result, "voice_natural", unit=row.unit)
        assert list(figure.data[-1].z) == [row.value]


def review_app_source():
    return """import streamlit as st
from app import views
original_actor = views.actor
views.actor = lambda: {'language': 'English', 'role': 'patient'}
try:
    for row in st.session_state['reviews']:
        views.review_result(row['result'], row['task'], identity=row['identity'], history_items=row.get('history'))
finally:
    views.actor = original_actor
"""


def test_review_integration_multiple_modules_have_distinct_keys_and_history_survives_reruns():
    adl = analyze_adl({key: 1 for key in ADL_ITEMS})
    reviews = [{"result": adl, "task": "adl", "identity": "visit-a-adl", "history": [
        {"id": "older", "status": "completed", "created_at": "2026-01-01", "modules": {"adl": adl}},
        {"id": "current", "status": "draft", "created_at": "2026-01-02", "modules": {"adl": adl}},
    ]}, {"result": analyze_text("Walking is difficult"), "task": "nlp", "identity": "visit-a-nlp"},
        {"result": audio_result("voice_vowel"), "task": "voice_vowel", "identity": "visit-a-voice-vowel"},
        {"result": audio_result("voice_sentence"), "task": "voice_sentence", "identity": "visit-a-voice-sentence"}]
    app = AppTest.from_string(review_app_source(), default_timeout=20)
    app.session_state["reviews"] = reviews
    app.run()
    assert not app.exception
    history_control = next(item for item in app.radio if "Visit history" in item.options)
    history_control.set_value("Visit history").run()
    assert not app.exception
    first_camera = next(item for item in app.selectbox if item.label == "Graph viewpoint")
    first_camera.set_value("Top").run()
    assert not app.exception
    assert next(item for item in app.radio if "Visit history" in item.options).value == "Visit history"
    assert next(item for item in app.selectbox if item.label == "Graph viewpoint").value == "Top"
    all_keys = [item.key for item in app.selectbox if item.label == "Graph viewpoint"]
    assert len(all_keys) == len(set(all_keys)) == 4


def test_review_controls_handle_accepted_to_rejected_and_feature_group_changes():
    result = audio_result("voice_vowel")
    app = AppTest.from_string(review_app_source(), default_timeout=20)
    app.session_state["reviews"] = [{"result": result, "task": "voice_vowel", "identity": "constant-visit-task"}]
    app.run()
    assert not app.exception
    next(item for item in app.selectbox if item.label == "Measurement unit").set_value("Hz").run()
    assert not app.exception
    changed = deepcopy(result)
    changed["features"] = {"internal_pause_count": 0, "signal_rms_dbfs": -23}
    app.session_state["reviews"] = [{"result": changed, "task": "voice_vowel", "identity": "constant-visit-task"}]
    app.run()
    assert not app.exception
    assert next(item for item in app.selectbox if item.label == "Measurement unit").value in {"pauses (count)", "dBFS"}
    changed["status"] = "repeat"
    changed["quality"] = {"accepted": False, "messages": ["Recording is silent or too quiet."]}
    app.session_state["reviews"] = [{"result": changed, "task": "voice_vowel", "identity": "constant-visit-task"}]
    app.run()
    assert not app.exception
    assert all(item.label != "Graph viewpoint" for item in app.selectbox)
    assert any("quality check" in item.value for item in app.info)


def test_history_default_opens_progress_view_and_preserves_user_selection_on_reruns():
    adl = analyze_adl({key: 1 for key in ADL_ITEMS})
    history = [{"id": "earlier", "created_at": "2026-01-01", "status": "completed", "modules": {"adl": adl}}]
    app = AppTest.from_string("from app.components.statistical_3d import module_statistics_panel\nimport streamlit as st\nmodule_statistics_panel(st.session_state['result'], 'adl', identity='progress', history=st.session_state['history'], default_view='history')", default_timeout=20)
    app.session_state["result"] = adl
    app.session_state["history"] = history
    app.run()
    assert not app.exception
    assert app.radio[0].value == "Visit history"
    app.radio[0].set_value("Measurement summary").run()
    assert not app.exception
    app.selectbox[0].set_value("Top").run()
    assert not app.exception
    assert app.radio[0].value == "Measurement summary"
    assert app.selectbox[0].value == "Top"
    # A caller may request history before a compatible accepted visit exists.
    # This must fall back to the actual current measurements without failure.
    app.session_state["history"] = []
    app.run()
    assert not app.exception
    assert not app.radio
    assert any(item.label == "Graph viewpoint" for item in app.selectbox)


def test_categorical_scene_has_label_padding_and_short_ticks_without_shortening_hover():
    result = analyze_adl({key: index % 5 for index, key in enumerate(ADL_ITEMS)})
    figure = build_module_statistics_figure(result, "adl")
    assert figure.layout.height == 490
    assert figure.layout.margin.b >= 80
    assert figure.layout.margin.l >= 40
    assert list(figure.layout.scene.yaxis.range) == [-1, 1]
    assert figure.layout.scene.xaxis.tickfont.size <= 11
    assert all(len(label) <= 18 for label in figure.layout.scene.xaxis.ticktext)
    assert "Household" in figure.layout.scene.xaxis.ticktext
    assert "Mean rating" in figure.layout.scene.xaxis.ticktext
    assert "Household activities" in [row[0] for row in figure.data[-1].customdata]
    assert "Mean of patient ratings" in [row[0] for row in figure.data[-1].customdata]
