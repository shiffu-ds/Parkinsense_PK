"""Current-frame focused 3D movement viewer for live recording.

Unlike the saved replay, this figure always starts at the current observation.
It has no animation frames or timeline and never replays stale detections.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import plotly.graph_objects as go

from ml.vision.live_overlay import focus_definition, observation_geometry, recent_observations
from ml.vision.tasks import HAND_CONNECTIONS, POSE_CONNECTIONS

CAMERAS = {
    "Isometric": {"x": 1.35, "y": 0.65, "z": -1.65},
    "Front": {"x": 0, "y": 0.12, "z": -2.1},
    "Side": {"x": 2.1, "y": 0.12, "z": 0},
    "Top": {"x": 0, "y": 2.1, "z": -0.01},
}
_TEAL, _BLUE = "#54eaae", "#63b6ff"
_JOINT_NAMES = {
    "hand": {0: "Wrist", 4: "Thumb tip", 8: "Index fingertip", 12: "Middle fingertip",
             16: "Ring fingertip", 20: "Little fingertip"},
    "pose": {11: "Left shoulder", 12: "Right shoulder", 13: "Left elbow", 14: "Right elbow",
             15: "Left wrist", 16: "Right wrist", 23: "Left hip", 24: "Right hip",
             25: "Left knee", 26: "Right knee", 27: "Left ankle", 28: "Right ankle"},
}


def _segments(points, valid, edges):
    coordinates = []
    for a, b in edges:
        if valid[a] and valid[b]:
            coordinates.extend((points[a].tolist(), points[b].tolist(), [None, None, None]))
    values = np.asarray(coordinates, dtype=object).reshape((-1, 3))
    return {axis: values[:, n].tolist() for n, axis in enumerate(("x", "y", "z"))}


def _layout(figure: go.Figure, task: str, camera: str, *, tracked: bool):
    focus = focus_definition(task)
    # observation_geometry uses the saved studio's native-Y sign reflection:
    # shoulders are above the origin, ankles below it. Keep Y up. A top view
    # needs a perpendicular up vector rather than one parallel to its eye.
    up = {"x": 0, "y": 0, "z": -1} if camera == "Top" else {"x": 0, "y": 1, "z": 0}
    ranges = [(-0.16, 0.16)] * 3 if focus["kind"] == "hand" else [(-1.2, 1.2), (-1.15, 1.05), (-1.1, 1.1)]
    axes = {}
    for name, limits in zip(("X", "Y", "Z"), ranges, strict=True):
        axes[name.lower() + "axis"] = {
            "title": {"text": name + " · m", "font": {"size": 10, "color": "#9caec0"}},
            "range": limits, "autorange": False, "showbackground": False,
            "gridcolor": "#243747", "zerolinecolor": "#36516a", "showspikes": False,
            "tickfont": {"size": 9, "color": "#849bad"}, "nticks": 4,
        }
    figure.update_layout(
        template="plotly_dark", paper_bgcolor="#101e2c", plot_bgcolor="#101e2c", height=450,
        margin={"l": 0, "r": 0, "t": 12, "b": 8},
        scene={**axes, "aspectmode": "data", "bgcolor": "#101e2c",
               "camera": {"eye": CAMERAS.get(camera, CAMERAS["Isometric"]), "up": up,
                          "projection": {"type": "orthographic"}}, "dragmode": "orbit"},
        showlegend=False, uirevision=f"live-{task}-{camera}",
        meta={"coordinate_source": "world_landmarks", "units": "estimated meters", "tracked": tracked,
              "available": tracked,
              "display_axes": "X right · Y up · Z away", "coordinate_transform": "native Y sign reflection only",
              "focus": focus["label"], "model_local": True, "current_frame_only": True},
    )


def build_live_3d_figure(observation: dict | None, task: str, *, history: Iterable[dict] | None = None,
                         show_trails: bool = True, camera: str = "Isometric") -> go.Figure:
    """Render latest real world XYZ with stable metric axes and bounded trails."""
    focus = focus_definition(task)
    geometry = observation_geometry(observation, task)
    figure = go.Figure()
    if geometry is None:
        _layout(figure, task, camera, tracked=False)
        figure.add_annotation(text="Waiting for clear tracking<br>Keep the selected body part in view",
                              showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                              font={"size": 14, "color": "#a4b7c9"})
        return figure
    points, valid = geometry
    connections = HAND_CONNECTIONS if focus["kind"] == "hand" else POSE_CONNECTIONS
    focused = {tuple(sorted(edge)) for edge in focus["edges"]}
    context = [edge for edge in connections if tuple(sorted(edge)) not in focused]
    figure.add_trace(go.Scatter3d(**_segments(points, valid, context), mode="lines",
                                 name="Body context", line={"color": "#657e92", "width": 3},
                                 opacity=0.36, hoverinfo="skip"))
    observations = recent_observations(observation, task, history) if show_trails else []
    if show_trails:
        prepared = [observation_geometry(item, task) for item in observations]
        for group_number, joint in enumerate(focus["trail_joints"]):
            trail = []
            for item_points, item_valid in prepared:
                trail.append(item_points[joint].tolist() if item_valid[joint] else [None, None, None])
            if len(trail) < 2:
                continue
            # Short fading bands keep payload small and preserve every loss gap.
            for band, indexes in enumerate(np.array_split(np.arange(len(trail) - 1), 3)):
                if not len(indexes):
                    continue
                coordinates = np.asarray(trail[int(indexes[0]):int(indexes[-1]) + 2], dtype=object)
                figure.add_trace(go.Scatter3d(
                    x=coordinates[:, 0].tolist(), y=coordinates[:, 1].tolist(), z=coordinates[:, 2].tolist(),
                    mode="lines", name="Recent local trail", hoverinfo="skip",
                    line={"color": _TEAL if group_number % 2 == 0 else _BLUE, "width": 3},
                    opacity=0.14 + band * 0.2,
                ))
    segments = _segments(points, valid, focus["edges"])
    figure.add_trace(go.Scatter3d(**segments, mode="lines", name="Focus glow", hoverinfo="skip",
                                 line={"color": _TEAL, "width": 14}, opacity=0.13))
    depths = [value for value in segments["z"] if value is not None]
    low, high = min(depths), max(depths)
    depth_values = [low if value is None else value for value in segments["z"]]
    figure.add_trace(go.Scatter3d(
        **segments, mode="lines", name="Focused 3D joints", hoverinfo="skip",
        line={"color": depth_values, "colorscale": [[0, _TEAL], [1, _BLUE]], "cmin": low,
              "cmax": max(high, low + 1e-6), "width": 7, "showscale": False},
    ))
    indexes = [joint for joint in focus["joints"] if valid[joint]]
    current = points[indexes]
    figure.add_trace(go.Scatter3d(
        x=current[:, 0].tolist(), y=current[:, 1].tolist(), z=current[:, 2].tolist(),
        mode="markers", name="Current focused joints",
        text=[_JOINT_NAMES[focus["kind"]].get(joint, f"Joint {joint}") for joint in indexes],
        customdata=indexes,
        marker={"size": 5, "color": "#effcf7", "line": {"color": _TEAL, "width": 1}},
        hovertemplate="%{text}<br>X %{x:.3f} m<br>Y %{y:.3f} m<br>Z %{z:.3f} m<extra>Model-local estimate</extra>",
    ))
    _layout(figure, task, camera, tracked=True)
    figure.layout.meta["timestamp_s"] = float(observation["timestamp_s"])
    figure.layout.meta["trail_frames"] = len(observations)
    return figure
