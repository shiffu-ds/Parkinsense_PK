"""Touchscreen spiral and tapping tests are scored from raw touches only."""
import math

import numpy as np
import pytest

from ml.common.results import numeric_features
from ml.touch import (
    DEFINITIONS, SPIRAL_GEOMETRY, TAP_GEOMETRY, TAP_SECONDS, analyze_spiral, analyze_tapping, analyze_touch,
)

DEVICE = {"canvas_px": [360, 360], "pointer": "touch", "dpr": 2}


def spiral(seconds=8.0, rate=60.0, tremor_hz=None, amplitude=0.0, turns=None, strokes=1):
    g = SPIRAL_GEOMETRY
    turns = g["turns"] if turns is None else turns
    times = np.arange(0, seconds, 1 / rate)
    theta = times / seconds * 2 * math.pi * turns
    radius = g["r_max"] * theta / (2 * math.pi * g["turns"])
    if tremor_hz:
        radius = radius + amplitude * np.sin(2 * math.pi * tremor_hz * times)
    stroke = np.minimum((times / seconds * strokes).astype(int), strokes - 1)
    return {"mode": "spiral", **DEVICE, "points": [[float(g["cx"] + r * math.cos(a)), float(g["cy"] + r * math.sin(a)),
                                                  float(t), int(s)] for r, a, t, s in zip(radius, theta, times, stroke)]}


def taps(intervals, *, completed=True, offset=(0.0, 0.0)):
    centres = TAP_GEOMETRY["targets"]
    output, moment = [], 0.0
    for number, gap in enumerate(intervals):
        x, y = centres[number % 2]
        output.append([x + offset[0], y + offset[1], round(moment, 4)])
        moment += gap
    return {"mode": "tapping", **DEVICE, "completed": completed, "taps": [tap for tap in output if tap[2] <= TAP_SECONDS]}


def test_a_traced_spiral_is_accepted_with_defined_units():
    result = analyze_spiral("spiral_right", spiral())
    assert result["quality"]["accepted"] and result["status"] == "completed" and result["side"] == "Right"
    features = result["features"]
    assert features["spiral_mean_deviation_pct"] < 1
    assert features["spiral_coverage_pct"] > 95
    assert features["spiral_lifts"] == 0
    assert 7.9 < features["spiral_duration_s"] < 8.0
    assert set(features) <= set(DEFINITIONS)
    assert all(result["feature_metadata"][name]["unit"] == DEFINITIONS[name][1] for name in features)
    assert numeric_features(result) and result["trace"][0][2] == 0
    assert result["device"] == {"canvas_px": [360, 360], "pointer": "touch", "pixel_ratio": 2.0}


def test_regular_oscillation_raises_the_4_to_7_hz_share():
    steady = analyze_spiral("spiral_left", spiral())["features"]["spiral_tremor_band_fraction"]
    shaky = analyze_spiral("spiral_left", spiral(tremor_hz=5.0, amplitude=0.008))["features"]
    assert shaky["spiral_tremor_band_fraction"] > 0.5 > steady
    assert shaky["spiral_mean_deviation_pct"] > 0.3


def test_slow_sampling_omits_the_oscillation_measure_instead_of_guessing():
    features = analyze_spiral("spiral_left", spiral(rate=20.0))["features"]
    assert "spiral_tremor_band_fraction" not in features and "spiral_coverage_pct" in features


def test_lifts_are_counted_and_partial_or_wild_drawings_are_rejected():
    assert analyze_spiral("spiral_right", spiral(strokes=3))["features"]["spiral_lifts"] == 2
    partial = analyze_spiral("spiral_right", spiral(turns=1.0))
    assert not partial["quality"]["accepted"] and partial["features"] == {}
    assert any("most of the guide spiral" in message for message in partial["quality"]["messages"])
    rng = np.random.default_rng(4)
    scribble = {"mode": "spiral", **DEVICE, "points": [[float(x), float(y), n / 60, 0] for n, (x, y) in enumerate(rng.random((300, 2)))]}
    assert not analyze_spiral("spiral_right", scribble)["quality"]["accepted"]
    short = analyze_spiral("spiral_right", {**spiral(), "points": spiral()["points"][:20]})
    assert any("longer drawing" in message for message in short["quality"]["messages"])


@pytest.mark.parametrize("change", [
    {"points": "not a list"}, {"points": [[0.5, 0.5, float("nan"), 0]] * 50}, {"points": [[3, 0.5, 0.1, 0]] * 50},
    {"points": [[0.5, 0.5, 0.1]] * 50}, {"canvas_px": [10, 10]}, {"mode": "tapping"}, {"points": [[0.5, 0.5, 0.1, 0]] * 4001},
])
def test_malformed_spiral_payloads_are_refused(change):
    with pytest.raises(ValueError):
        analyze_spiral("spiral_right", {**spiral(), **change})


def test_even_alternating_tapping_is_measured():
    result = analyze_tapping("touch_tap_left", taps([0.25] * 100))
    assert result["quality"]["accepted"] and result["side"] == "Left"
    features = result["features"]
    assert features["tap_count"] == 81 and features["tap_rate_per_s"] == pytest.approx(81 / TAP_SECONDS)
    assert features["tap_hit_fraction"] == 1 and features["tap_alternation_fraction"] == 1
    assert features["tap_interval_mean_ms"] == pytest.approx(250) and features["tap_interval_cv"] < 0.01
    assert abs(features["tap_rate_change_pct"]) < 5 and features["tap_error_mean_pct"] < 0.1


def test_slowing_taps_show_a_negative_rate_change():
    intervals = [0.2 + 0.006 * n for n in range(80)]
    assert analyze_tapping("touch_tap_right", taps(intervals))["features"]["tap_rate_change_pct"] < -20


def test_incomplete_sparse_or_off_target_tapping_is_rejected():
    stopped = analyze_tapping("touch_tap_right", taps([0.25] * 100, completed=False))
    assert not stopped["quality"]["accepted"] and any("full 20 seconds" in m for m in stopped["quality"]["messages"])
    sparse = analyze_tapping("touch_tap_right", taps([3.0] * 6))
    assert any("at least 8 taps" in m for m in sparse["quality"]["messages"])
    missed = analyze_tapping("touch_tap_right", taps([0.25] * 100, offset=(0.0, 0.25)))
    assert not missed["quality"]["accepted"] and missed["features"] == {}


def test_router_rejects_unknown_tasks():
    with pytest.raises(ValueError):
        analyze_touch("gait", spiral())
    with pytest.raises(ValueError):
        analyze_spiral("touch_tap_left", spiral())
    assert analyze_touch("touch_tap_left", taps([0.25] * 100))["test"] == "tapping"
