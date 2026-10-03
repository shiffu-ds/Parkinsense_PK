"""Recording instructions and minimum visibility for each independent task."""

TASKS = {
    "gait": {"label": "Walking / gait", "kind": "pose", "min_seconds": 5, "joints": [11, 12, 23, 24, 25, 26, 27, 28, 31, 32]},
    "turning": {"label": "Turning", "kind": "pose", "min_seconds": 3, "joints": [11, 12, 23, 24, 25, 26, 27, 28]},
    "finger_left": {"label": "Finger tapping — left", "kind": "hand", "side": "Left", "min_seconds": 5, "joints": list(range(21))},
    "finger_right": {"label": "Finger tapping — right", "kind": "hand", "side": "Right", "min_seconds": 5, "joints": list(range(21))},
    "hand_open_close": {"label": "Hand opening / closing", "kind": "hand", "min_seconds": 5, "joints": list(range(21))},
    "sit_to_stand": {"label": "Sit-to-stand", "kind": "pose", "min_seconds": 3, "joints": [11, 12, 23, 24, 25, 26, 27, 28]},
    "reach": {"label": "Functional reach", "kind": "pose", "min_seconds": 3, "joints": [11, 12, 13, 14, 15, 16, 23, 24]},
    "grasp": {"label": "Grasp", "kind": "hand", "min_seconds": 3, "joints": list(range(21))},
    "object_transfer": {"label": "Object transfer", "kind": "hand", "min_seconds": 3, "joints": list(range(21))},
}

POSE_CONNECTIONS = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24), (23, 25), (25, 27), (27, 29), (29, 31), (27, 31), (24, 26), (26, 28), (28, 30), (30, 32), (28, 32)]
HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]

