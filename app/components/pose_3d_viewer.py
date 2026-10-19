"""A bounded WebGL movement studio using genuine model-local world XYZ.

The solid avatar is a stylized display mesh around observed joints, not a
recovered skin surface. Unknown joints and lost tracking are never filled in.
"""

from __future__ import annotations

from html import escape

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from ml.vision.spatial import SpatialMotion, motion_frame_summary, prepare_motion
from ml.vision.tasks import HAND_CONNECTIONS, POSE_CONNECTIONS

CAMERAS = {
    "Front": {"x": 0, "y": 0.15, "z": -2.2},
    "Side": {"x": 2.2, "y": 0.15, "z": 0},
    "Top": {"x": 0, "y": 2.2, "z": -0.01},
    "Isometric": {"x": 1.45, "y": 0.75, "z": -1.65},
}
STYLES = ("Solid avatar", "Skeleton")
LEFT_COLOR, RIGHT_COLOR, CORE_COLOR = "#449c98", "#698db7", "#879caf"
BASELINE_COLOR = "#b79b71"
_BODY_LEFT = {11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31}
_BODY_RIGHT = {12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32}
_BODY_CONNECTIONS = POSE_CONNECTIONS + [(15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22)]
JOINT_NAMES = {
    "hand": {0: "Wrist (hand-local)", 4: "Thumb tip", 8: "Index fingertip", 12: "Middle fingertip", 16: "Ring fingertip", 20: "Little fingertip"},
    "pose": {15: "Left wrist", 16: "Right wrist", 23: "Left hip", 24: "Right hip", 25: "Left knee", 26: "Right knee", 27: "Left ankle", 28: "Right ankle"},
}
_GOLDEN = (1 + np.sqrt(5)) / 2
_SPHERE_VERTICES = np.asarray([(-1, _GOLDEN, 0), (1, _GOLDEN, 0), (-1, -_GOLDEN, 0), (1, -_GOLDEN, 0),
                               (0, -1, _GOLDEN), (0, 1, _GOLDEN), (0, -1, -_GOLDEN), (0, 1, -_GOLDEN),
                               (_GOLDEN, 0, -1), (_GOLDEN, 0, 1), (-_GOLDEN, 0, -1), (-_GOLDEN, 0, 1)], dtype=float)
_SPHERE_VERTICES /= np.linalg.norm(_SPHERE_VERTICES, axis=1)[:, None]
_SPHERE_FACES = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
                 (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
                 (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]


def _rounded_sphere():
    """One cached subdivision for the head; joints keep their small mesh."""
    vertices, faces, midpoints = list(_SPHERE_VERTICES.copy()), [], {}

    def midpoint(a, b):
        edge = tuple(sorted((a, b)))
        if edge not in midpoints:
            point = vertices[a] + vertices[b]
            midpoints[edge] = len(vertices)
            vertices.append(point / np.linalg.norm(point))
        return midpoints[edge]

    for a, b, c in _SPHERE_FACES:
        ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
        faces.extend(((a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)))
    return np.asarray(vertices), faces


_HEAD_VERTICES, _HEAD_FACES = _rounded_sphere()


class _Mesh:
    """Batch disconnected bone tubes and spherical joints into a single mesh."""

    def __init__(self):
        self.vertices = []
        self.faces = []

    def add(self, vertices, faces):
        offset = len(self.vertices)
        self.vertices.extend(np.round(vertices, 5).tolist())
        self.faces.extend([(a + offset, b + offset, c + offset) for a, b, c in faces])

    def sphere(self, point, radius, *, rounded=False):
        vertices, faces = (_HEAD_VERTICES, _HEAD_FACES) if rounded else (_SPHERE_VERTICES, _SPHERE_FACES)
        self.add(vertices * radius + point, faces)

    def tube(self, start, end, radius, *, taper=1.0):
        direction = end - start
        length = np.linalg.norm(direction)
        if not np.isfinite(length) or length < 1e-6:
            return
        direction /= length
        helper = np.asarray([0.0, 1.0, 0.0]) if abs(direction[1]) < 0.85 else np.asarray([1.0, 0.0, 0.0])
        first = np.cross(direction, helper)
        first /= np.linalg.norm(first)
        second = np.cross(direction, first)
        count = 8
        angles = np.arange(count) * (2 * np.pi / count)
        ring = radius * (np.cos(angles)[:, None] * first + np.sin(angles)[:, None] * second)
        vertices = np.concatenate((ring + start, ring * taper + end, [start, end]))
        faces = []
        for n in range(count):
            after = (n + 1) % count
            faces.extend([(n, after, count + n), (after, count + after, count + n)])
            faces.extend([(2 * count, after, n), (2 * count + 1, count + n, count + after)])
        self.add(vertices, faces)

    def slab(self, perimeter, thickness):
        """Thin visual torso/palm shell; no estimated clinical anatomy added."""
        normal = np.cross(perimeter[1] - perimeter[0], perimeter[2] - perimeter[0])
        norm = np.linalg.norm(normal)
        if not np.isfinite(norm) or norm < 1e-8:
            return
        normal = normal / norm * thickness / 2
        count = len(perimeter)
        vertices = np.concatenate((perimeter + normal, perimeter - normal))
        faces = []
        for n in range(1, count - 1):
            faces.extend([(0, n, n + 1), (count, count + n + 1, count + n)])
        for n in range(count):
            after = (n + 1) % count
            faces.extend([(n, after, count + n), (after, count + after, count + n)])
        self.add(vertices, faces)

    def trace(self, color, label):
        points = np.asarray(self.vertices).reshape((-1, 3))
        faces = np.asarray(self.faces, dtype=int).reshape((-1, 3))
        return go.Mesh3d(x=points[:, 0].tolist(), y=points[:, 1].tolist(), z=points[:, 2].tolist(),
                         i=faces[:, 0].tolist(), j=faces[:, 1].tolist(), k=faces[:, 2].tolist(),
                         color=color, name=label, showlegend=True, flatshading=False,
                         lighting={"ambient": 0.48, "diffuse": 0.85, "roughness": 0.72, "specular": 0.28,
                                   "fresnel": 0.12},
                         lightposition={"x": -180, "y": 260, "z": -300},
                         hoverinfo="name", opacity=1)


def _bone_radius(points, a, b, hand):
    """Stylized thickness follows the observed segment, without moving joints."""
    length = float(np.linalg.norm(points[b] - points[a]))
    ratio = 0.13 if hand else 0.11 if a in (23, 24) else 0.08
    return min(0.006 if hand else 0.045, length * ratio)


def _groups(motion: SpatialMotion):
    if motion.kind == "hand":
        side = motion.side or "Selected"
        return [(set(range(21)), HAND_CONNECTIONS, LEFT_COLOR if side == "Left" else RIGHT_COLOR, f"{side} hand")]
    core = [(a, b) for a, b in _BODY_CONNECTIONS if a not in _BODY_LEFT or b not in _BODY_LEFT]
    core = [(a, b) for a, b in core if a not in _BODY_RIGHT or b not in _BODY_RIGHT]
    return [(_BODY_LEFT, [(a, b) for a, b in _BODY_CONNECTIONS if a in _BODY_LEFT and b in _BODY_LEFT], LEFT_COLOR, "Left side"),
            (_BODY_RIGHT, [(a, b) for a, b in _BODY_CONNECTIONS if a in _BODY_RIGHT and b in _BODY_RIGHT], RIGHT_COLOR, "Right side"),
            (set(), core, CORE_COLOR, "Torso / head")]


def _avatar(motion: SpatialMotion, n: int, style: str, *, baseline: bool = False):
    points, valid = motion.points[n], motion.valid[n]
    hand = motion.kind == "hand"
    traces = []
    for group_number, (joints, connections, color, label) in enumerate(_groups(motion)):
        if baseline:
            color, label = BASELINE_COLOR, "Baseline " + label.lower()
        if style == "Skeleton" or baseline:
            coords = []
            for a, b in connections:
                if valid[a] and valid[b]:
                    coords.extend((points[a].tolist(), points[b].tolist(), [None, None, None]))
            values = np.asarray(coords, dtype=object).reshape((-1, 3))
            trace = go.Scatter3d(x=values[:, 0].tolist(), y=values[:, 1].tolist(), z=values[:, 2].tolist(),
                                mode="lines+markers", name=label, marker={"color": color, "size": 2 if baseline else 3}, line={"color": color, "width": 4 if baseline else 6,
                                                               "dash": "dash" if baseline else "solid"},
                                opacity=0.48 if baseline else 1, hoverinfo="name")
            traces.append(trace)
            continue
        mesh = _Mesh()
        for a, b in connections:
            if not (valid[a] and valid[b]):
                continue
            radius = _bone_radius(points, a, b, hand)
            mesh.tube(points[a], points[b], radius, taper=0.78)
        for joint in sorted(joints):
            if valid[joint]:
                adjacent = [_bone_radius(points, a, b, hand) for a, b in connections
                            if joint in (a, b) and valid[a] and valid[b]]
                # An isolated observed joint still remains visible. Its small
                # marker is a display symbol, never an inferred body segment.
                radius = max(adjacent, default=0.002 if hand else 0.008)
                mesh.sphere(points[joint], radius * 1.15)
        if hand:
            palm = [0, 5, 9, 13, 17]
            if np.all(valid[palm]):
                width = float(np.linalg.norm(points[5] - points[17]))
                mesh.slab(points[palm], width * 0.14)
        elif group_number == 2:
            torso = [11, 12, 24, 23]
            if np.all(valid[torso]):
                width = float(np.linalg.norm(points[11] - points[12]))
                mesh.slab(points[torso], width * 0.14)
            face = [0, 7, 8]
            if np.all(valid[face]):
                head = np.mean(points[face], axis=0)
                width = float(np.linalg.norm(points[7] - points[8]))
                radius = min(0.12, width * 0.55)
                mesh.sphere(head, np.asarray([radius, radius * 1.15, radius * 0.92]), rounded=True)
                if np.all(valid[[11, 12]]):
                    mesh.tube(head, np.mean(points[[11, 12]], axis=0), radius * 0.3)
        traces.append(mesh.trace(color, label))
    return traces


def _trail_specs(motion: SpatialMotion, task: str, trail_joint):
    names = JOINT_NAMES[motion.kind]
    if trail_joint is not None:
        if isinstance(trail_joint, str):
            selected = next((index for index, label in names.items() if label.lower() == trail_joint.lower()), None)
        else:
            try:
                selected = int(trail_joint)
            except (TypeError, ValueError):
                selected = None
        return [(selected, names.get(selected, f"Joint {selected}"), LEFT_COLOR)] if selected is not None and 0 <= selected < len(motion.valid[0]) else []
    if motion.kind == "hand":
        return [(4, "Thumb tip", BASELINE_COLOR), (8, "Index fingertip", LEFT_COLOR)]
    if task == "reach":
        return [(15, "Left wrist", LEFT_COLOR), (16, "Right wrist", RIGHT_COLOR)]
    return [(27, "Left ankle", LEFT_COLOR), (28, "Right ankle", RIGHT_COLOR)]


def _trail(motion: SpatialMotion, n: int, index: int, label: str, color: str):
    coordinates = []
    for frame in range(max(0, n - 29), n + 1):
        if motion.breaks[frame, index] or not motion.valid[frame, index]:
            coordinates.append([None, None, None])
        if motion.valid[frame, index]:
            coordinates.append(motion.points[frame, index].tolist())
    points = np.asarray(coordinates, dtype=object).reshape((-1, 3))
    return go.Scatter3d(x=points[:, 0].tolist(), y=points[:, 1].tolist(), z=points[:, 2].tolist(), mode="lines",
                        name=label + " · local trail", line={"color": color, "width": 3}, opacity=0.7,
                        hovertemplate="X %{x:.3f} m<br>Y %{y:.3f} m<br>Z %{z:.3f} m<extra>Model-local estimate</extra>")


def _limits(motions):
    values = np.concatenate([motion.points[motion.valid] for motion in motions])
    limits = []
    minimum = 0.025 if motions[0].kind == "hand" else 0.1
    for dimension in range(3):
        low, high = float(np.min(values[:, dimension])), float(np.max(values[:, dimension]))
        padding = max(minimum, (high - low) * 0.15)
        limits.append([low - padding, high + padding])
    return limits


def _reference_grid(limits):
    coords = []
    for x in np.linspace(*limits[0], 7):
        coords.extend(([x, 0, limits[2][0]], [x, 0, limits[2][1]], [None, None, None]))
    for z in np.linspace(*limits[2], 7):
        coords.extend(([limits[0][0], 0, z], [limits[0][1], 0, z], [None, None, None]))
    values = np.asarray(coords, dtype=object)
    return go.Scatter3d(x=values[:, 0].tolist(), y=values[:, 1].tolist(), z=values[:, 2].tolist(), mode="lines",
                        line={"color": "#304456", "width": 1}, name="Origin plane · not measured floor",
                        showlegend=False, hoverinfo="skip", opacity=0.45)


def _scale_bar(limits, hand):
    """A fixed metric reference, deliberately separate from body dimensions."""
    span = limits[0][1] - limits[0][0]
    candidates = (0.01, 0.02, 0.05) if hand else (0.05, 0.1, 0.25)
    length = next((value for value in reversed(candidates) if value <= span * 0.4), candidates[0])
    start = np.asarray([limits[0][0] + span * 0.08, limits[1][0], limits[2][0]])
    end = start + [length, 0, 0]
    return go.Scatter3d(x=[start[0], end[0]], y=[start[1], end[1]], z=[start[2], end[2]],
                        mode="lines+markers+text", text=["", f"{length * 100:g} cm · estimated scale"],
                        textposition="top right", textfont={"size": 10, "color": "#c3d3df"},
                        line={"color": "#c3d3df", "width": 5}, marker={"color": "#c3d3df", "size": 2},
                        name="Model scale reference", showlegend=False, hoverinfo="name")


def _playback_menus(frame_count, durations, n, speed):
    # Plotly's fromcurrent slices frame names but does not slice its duration
    # array. Each observed frame therefore carries an explicitly aligned
    # continuation queue. Scrubbing and pausing preserve the actual timing.
    start = 0 if n == frame_count - 1 else n
    return [{"type": "buttons", "direction": "left", "showactive": False, "x": 0.02,
             "xanchor": "left", "y": -0.03, "bgcolor": "#263a4b", "bordercolor": "#3a5164", "buttons": [
                 {"label": f"{'↺ Replay' if n == frame_count - 1 else '▶ Play'} · {speed:g}×", "method": "animate",
                  "args": [[str(index) for index in range(start, frame_count)],
                           {"frame": [{"duration": delay, "redraw": True} for delay in durations[start:]],
                            "transition": {"duration": 0}, "mode": "immediate", "fromcurrent": False}]},
                 {"label": "Pause", "method": "animate", "args": [[None], {"frame": {"duration": 0, "redraw": False},
                                                                                  "mode": "immediate", "transition": {"duration": 0}}]},
             ]}]


def _tracking_annotation(motion, n):
    count = int(np.count_nonzero(motion.valid[n]))
    interrupted = n + 1 < len(motion.timestamps) and bool(np.all(motion.breaks[n + 1]))
    label = f"{motion.timestamps[n]:.2f} s · {count} / {len(motion.valid[n])} joints observed"
    if interrupted:
        label += "<br>Last observed pose · tracking interrupted before next sample"
    return {"text": label, "xref": "paper", "yref": "paper", "x": 0.02, "y": 0.98,
            "xanchor": "left", "yanchor": "top", "showarrow": False, "align": "left",
            "font": {"size": 11, "color": "#e0bd83" if interrupted else "#afc8d2"},
            "bgcolor": "rgba(16,27,39,0.88)", "borderpad": 7}


def _empty_figure():
    figure = go.Figure()
    figure.add_annotation(text="3D replay is unavailable for this recording.<br>World landmarks are required; repeat the recording with clear visibility.",
                          showarrow=False, font={"size": 15, "color": "#aabaca"})
    figure.update_layout(template="plotly_dark", paper_bgcolor="#101b27", plot_bgcolor="#101b27", height=460,
                         xaxis={"visible": False}, yaxis={"visible": False}, margin={"t": 20, "b": 20})
    return figure


def build_motion_figure(result: dict, baseline: dict | None = None, *, camera: str = "Isometric",
                        style: str = "Solid avatar", playback_speed: float = 1.0,
                        show_trails: bool = True, trail_joint=None, show_grid: bool = True,
                        center: bool = True, smooth: bool = False) -> go.Figure:
    """Replay world XYZ with fixed units, a scrubber and a bounded mesh payload.

    Baseline aligns initial model-local origins at unchanged scale and matches
    relative recording time. This visual alignment is not clinical registration.
    """
    motion = prepare_motion(result, center=center, smooth=smooth)
    if motion is None:
        return _empty_figure()
    baseline_motion = None
    if baseline and baseline.get("task") == result.get("task"):
        candidate = prepare_motion(baseline, center=center, smooth=smooth)
        if candidate is not None and candidate.kind == motion.kind and (not motion.side or not candidate.side or motion.side == candidate.side):
            baseline_motion = candidate
    style = style if style in STYLES else "Solid avatar"
    try:
        speed = float(playback_speed)
        speed = min(2.0, max(0.25, speed)) if np.isfinite(speed) else 1.0
    except (ValueError, TypeError):
        speed = 1.0
    specs = _trail_specs(motion, result.get("task", ""), trail_joint) if show_trails else []
    limits = _limits([motion] + ([baseline_motion] if baseline_motion is not None else []))
    animated_count = len(_groups(motion)) + (len(_groups(baseline_motion)) if baseline_motion else 0) + len(specs)
    figure = go.Figure()
    frames = []
    total_time = float(motion.timestamps[-1] - motion.timestamps[0])
    with np.errstate(over="ignore"):
        interval_ms = np.diff(motion.timestamps) * 1000 / speed
    # Normal recordings retain their exact intervals. Pathological metadata
    # cannot create an unbounded timer; any compressed gap is disclosed.
    timing_compressed = bool(np.any(interval_ms > 120_000))
    durations = [round(float(value), 3) for value in np.minimum(interval_ms, 120_000)] + [0]
    for n in range(len(motion.timestamps)):
        data = _avatar(motion, n, style)
        if baseline_motion is not None:
            progress = float((motion.timestamps[n] - motion.timestamps[0]) / total_time) if total_time > 0 else 0.0
            baseline_time = baseline_motion.timestamps[0] + progress * (baseline_motion.timestamps[-1] - baseline_motion.timestamps[0])
            index = int(np.argmin(np.abs(baseline_motion.timestamps - baseline_time)))
            data.extend(_avatar(baseline_motion, index, "Skeleton", baseline=True))
        data.extend(_trail(motion, n, index, label, color) for index, label, color in specs)
        if n == 0:
            figure.add_traces(data)
        frames.append(go.Frame(name=str(n), data=data, traces=list(range(animated_count)),
                               layout={"updatemenus": _playback_menus(len(motion.timestamps), durations, n, speed),
                                       "annotations": [_tracking_annotation(motion, n)]}))
    figure.frames = frames
    figure.add_trace(_scale_bar(limits, motion.kind == "hand"))
    if show_grid:
        figure.add_trace(_reference_grid(limits))
    figure.add_trace(go.Scatter3d(x=[0], y=[0], z=[0], mode="markers", marker={"size": 3, "color": "#a5b7c8"},
                                 name="Model origin", showlegend=False, hoverinfo="name"))
    scene = {"bgcolor": "#101b27", "aspectmode": "data", "dragmode": "orbit", "uirevision": f"{camera}-{motion.kind}-{center}",
             "camera": {"eye": CAMERAS.get(camera, CAMERAS["Isometric"]), "up": {"x": 0, "y": 1, "z": 0}, "projection": {"type": "orthographic"}}}
    for n, axis in enumerate(("x", "y", "z")):
        scene[axis + "axis"] = {"title": ("X · right (m)", "Y · up (m)", "Z · depth (estimated m)")[n],
                                "range": limits[n], "autorange": False, "showgrid": show_grid,
                                "gridcolor": "#263646", "zerolinecolor": "#536676", "showbackground": False,
                                "tickfont": {"size": 10, "color": "#98aabd"}, "nticks": 5}
    figure.update_layout(
        template="plotly_dark", height=680, scene=scene, paper_bgcolor="#101b27", font={"family": "Arial, sans-serif", "color": "#bdcbd8"},
        title={"text": "3D hand articulation" if motion.kind == "hand" else "3D body articulation", "font": {"size": 17},
               "x": 0.02, "y": 0.98, "yanchor": "top"},
        margin={"l": 0, "r": 0, "b": 10, "t": 110},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0.02, "xanchor": "left", "font": {"size": 11}},
        annotations=[_tracking_annotation(motion, 0)],
        meta={"coordinate_source": "world_landmarks", "units": "estimated_meters", "model_local": True, "source_frames": motion.source_count,
              "replay_frames": len(frames), "playback_speed": speed,
              "timing": "Recorded intervals; gaps above two replay minutes compressed" if timing_compressed else "Recorded intervals",
              "baseline_alignment": "initial origins; unchanged scale; relative time" if baseline_motion else None},
        updatemenus=_playback_menus(len(motion.timestamps), durations, 0, speed),
        sliders=[{"active": 0, "x": 0.08, "len": 0.88, "pad": {"t": 55}, "currentvalue": {"prefix": "Recording time · ", "font": {"size": 12}}, "bgcolor": "#365569",
                  "steps": [{"label": f"{timestamp:.1f}s", "method": "animate", "args": [[str(n)], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}}]}
                            for n, timestamp in enumerate(motion.timestamps)]}],
    )
    return figure


def build_motion_html(result: dict, baseline: dict | None = None, **options) -> str:
    """Self-contained replay export: no patient labels, media or external CDN.

    Coordinates remain sensitive data. The receiving UI must say that the file
    contains movement landmarks; it should not claim they are anonymous.
    """
    figure = build_motion_figure(result, baseline, **options)
    # Only this bounded renderer's whitelisted geometry and fixed labels go to
    # Plotly. Patient identity, clinician notes and media metadata never do.
    plot = pio.to_html(figure, full_html=False, include_plotlyjs=True, auto_play=False,
                       config={"displaylogo": False, "responsive": True, "scrollZoom": True}, div_id="parkinsense-motion")
    summary = motion_frame_summary(result)
    note = escape(summary["note"])
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>ParkinSense · 3D movement replay</title><style>body{margin:0;background:#101b27;color:#bdcbd8;font:15px Arial,sans-serif}"
            "header,footer{padding:18px 28px}h1{font-size:20px;margin:0 0 8px}p{line-height:1.6;margin:0}a{color:#63b9af}</style></head><body>"
            "<header><h1>ParkinSense · 3D movement replay</h1><p>Estimated model-local XYZ · X right / Y up / Z away. "
            "Drag to rotate; use the time bar to inspect movement.</p></header>" + plot +
            "<footer><p>" + note + "</p><p>The solid mesh is a stylized display around observed joints, not a recovered body surface. "
            "This file contains movement landmarks. Share it only with someone you trust.</p></footer></body></html>")


def build_joint_chart(result: dict, baseline: dict | None = None) -> go.Figure:
    """Optional feature/time details; the primary movement view remains 3D."""
    figure = go.Figure()
    colors = [LEFT_COLOR, RIGHT_COLOR, BASELINE_COLOR, CORE_COLOR]
    curves = result.get("curves", {})
    keys = [key for key in curves if key != "timestamp_s"]
    preferred = [key for key in keys if "angle_deg" in key] or [key for key in keys if "distance_ratio" in key or "opening_ratio" in key] or keys[:2]
    for n, key in enumerate(preferred):
        figure.add_trace(go.Scatter(x=curves.get("timestamp_s", []), y=curves[key], mode="lines", name=key.replace("_", " "), line={"color": colors[n % len(colors)]}))
        if baseline and baseline.get("task") == result.get("task"):
            previous = baseline.get("curves", {})
            if key in previous:
                figure.add_trace(go.Scatter(x=previous.get("timestamp_s", []), y=previous[key], mode="lines", name="Baseline " + key.replace("_", " "), line={"color": colors[n % len(colors)], "dash": "dash"}, opacity=0.55))
    figure.update_layout(template="plotly_dark", paper_bgcolor="#101b27", plot_bgcolor="#101b27", height=340,
                         xaxis_title="Recording time (seconds)", yaxis_title="Estimated angle (degrees)" if any("angle_deg" in key for key in preferred) else "Relative movement proxy",
                         margin={"l": 0, "r": 0, "t": 10, "b": 10})
    return figure


__all__ = ["build_motion_figure", "build_motion_html", "build_joint_chart", "motion_frame_summary", "CAMERAS", "STYLES", "JOINT_NAMES"]
