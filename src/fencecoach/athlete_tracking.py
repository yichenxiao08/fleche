"""Continuity-based selection among detected poses, with explicit abstention.

This tracks image geometry, not biometric identity. Occlusion and camera cuts
create separate epochs, so downstream evidence cannot bridge uncertain identity.
"""

import math
import re

VERSION = "athlete-tracking-v2"


def selection_hint(description):
    """Use explicit location wording only; never mistake facing for location."""
    text = description.lower()
    if "second from left" in text:
        return "second_from_left"
    if re.search(r"\b(on screen right|right foreground|foreground right|right fencer)\b", text):
        return "right"
    if re.search(r"\b(left fencer|left foreground|foreground left|left-side)\b", text):
        return "left"
    return None


def descriptor(landmarks, width, height):
    if len(landmarks) != 33:
        return None
    ids = (11, 12, 23, 24)
    if any(
        len(landmarks[i]) < 5
        or not all(math.isfinite(v) for v in landmarks[i])
        or min(landmarks[i][3:5]) < 0.5
        for i in ids
    ):
        return None
    points = {i: (landmarks[i][0] * width, landmarks[i][1] * height) for i in ids}
    hip = tuple((points[23][axis] + points[24][axis]) / 2 for axis in (0, 1))
    shoulder = tuple((points[11][axis] + points[12][axis]) / 2 for axis in (0, 1))
    scale = math.dist(hip, shoulder)
    if scale < 10:
        return None
    return {"center": hip, "scale": scale}


class AthleteTracker:
    def __init__(self, crop, width, height, hint=None, foreground=False):
        self.crop, self.width, self.height = crop, width, height
        self.last = None
        self.previous = None
        self.epoch = 0
        self.hint = hint if hint in {"left", "right", "second_from_left"} else None
        self.foreground = foreground

    def select(self, poses, timestamp):
        candidates = [(pose, descriptor(pose, self.width, self.height)) for pose in poses]
        candidates = [(pose, d) for pose, d in candidates if d]
        metadata = {"version": VERSION, "detected_poses": len(poses), "epoch": self.epoch}
        if not candidates:
            return None, {**metadata, "reason": "no_usable_torso"}
        if self.last and timestamp - self.last["time_ms"] > 750:
            self.last = self.previous = None
        if self.last:
            dt = (timestamp - self.last["time_ms"]) / 1000
            predicted = self.last["center"]
            if self.previous:
                previous_dt = (self.last["time_ms"] - self.previous["time_ms"]) / 1000
                if 0 < previous_dt <= 0.3:
                    velocity = [
                        (a - b) / previous_dt
                        for a, b in zip(self.last["center"], self.previous["center"])
                    ]
                    predicted = tuple(
                        c
                        + max(-3, min(3, v / self.last["scale"]))
                        * self.last["scale"]
                        * min(dt, 0.25)
                        for c, v in zip(predicted, velocity)
                    )
            scored = []
            for pose, d in candidates:
                ratio = d["scale"] / self.last["scale"]
                distance = math.dist(d["center"], predicted) / self.last["scale"]
                if 0.65 <= ratio <= 1.55 and distance <= min(2, 0.7 + 3 * dt):
                    scored.append((distance + abs(math.log(ratio)), pose, d))
            reason = "continuity"
        else:
            cropped = self.crop["width"] < 0.98 or self.crop["height"] < 0.98
            if self.foreground and not cropped:
                candidates = [
                    (pose, d) for pose, d in candidates if d["center"][1] >= self.height * 0.55
                ]
                if not candidates:
                    return None, {**metadata, "reason": "foreground_athlete_unresolved"}
            if self.hint and not cropped:
                if self.hint == "second_from_left":
                    candidates.sort(key=lambda item: item[1]["center"][0])
                    if len(candidates) < 2:
                        return None, {**metadata, "reason": "selected_athlete_unresolved"}
                    candidates = [candidates[1]]
                else:
                    candidates = [
                        (pose, d)
                        for pose, d in candidates
                        if (
                            d["center"][0] <= self.width * 0.55
                            if self.hint == "left"
                            else d["center"][0] >= self.width * 0.45
                        )
                    ]
                    if not candidates:
                        return None, {**metadata, "reason": "selected_athlete_unresolved"}
            if len(candidates) > 1 and not cropped and not self.hint:
                return None, {**metadata, "reason": "ambiguous_initial_athlete"}
            cx = (self.crop["x"] + self.crop["width"] / 2) * self.width
            if not cropped and self.hint in {"left", "right"}:
                cx = self.width * (0.25 if self.hint == "left" else 0.75)
            cy = (self.crop["y"] + self.crop["height"] / 2) * self.height
            scored = [
                (math.dist(d["center"], (cx, cy)) / d["scale"], pose, d) for pose, d in candidates
            ]
            reason = "crop_anchor" if len(candidates) > 1 else "single_pose_acquisition"
            if self.hint and not cropped:
                reason = "declared_athlete_location"
        scored.sort(key=lambda item: item[0])
        if not scored:
            return None, {**metadata, "reason": "identity_discontinuity"}
        if len(scored) > 1 and scored[1][0] - scored[0][0] < 0.45:
            return None, {**metadata, "reason": "ambiguous_athlete_match"}
        _, selected, d = scored[0]
        if not self.last:
            self.epoch += 1
        self.previous, self.last = self.last, {**d, "time_ms": timestamp}
        return selected, {
            **metadata,
            "epoch": self.epoch,
            "reason": reason,
            "selected_from_multiple": len(poses) > 1,
        }
