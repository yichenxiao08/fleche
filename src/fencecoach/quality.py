"""Versioned input-quality checks. A supported verdict is not technique validation."""

from statistics import mean

VERSION = "solo-quality-v1"


def assess_quality(result):
    frames = result.get("frames", [])
    valid = [f for f in frames if f.get("features")]
    profile = result.get("capture_profile", {})
    issues = []

    def issue(code, tip, reject=True):
        issues.append({"code": code, "tip": tip, "severity": "reject" if reject else "warning"})

    if min(result.get("width", 0), result.get("height", 0)) < 480:
        issue(
            "low_resolution",
            "Film at 720p or higher; the shorter image dimension must be at least 480 pixels.",
        )
    if profile.get("scene_type", "solo") != "solo":
        issue(
            "experimental_bout",
            "Use a solo practice clip for coaching. Bout analysis is experimental.",
        )
    coverage = len(valid) / max(1, len(frames))
    if coverage < 0.80:
        issue(
            "tracking_coverage",
            "Keep one fencer's whole body visible, use brighter lighting, and avoid occlusion.",
        )
    multi_fraction = (
        mean(f.get("tracking", {}).get("detected_poses", 1) > 1 for f in frames) if frames else 0
    )
    if multi_fraction > 0.10:
        issue(
            "multiple_people",
            "Film one fencer alone; move spectators and other bouts outside the frame.",
        )
    switches = len({f.get("track_epoch", 0) for f in valid}) - 1 if valid else 0
    if switches > 0:
        issue(
            "identity_break",
            "Keep the same fencer visible throughout; avoid camera cuts or leaving the frame.",
        )
    truncated = 0
    full_body_samples = 0
    for f in frames:
        p = f.get("landmarks", [])
        if len(p) != 33:
            continue
        ids = (0, 11, 12, 15, 16, 23, 24, 27, 28, 31, 32)
        full_body_samples += 1
        if any(
            min(p[i][3:5]) < 0.5 or not (0.02 <= p[i][0] <= 0.98 and 0.02 <= p[i][1] <= 0.98)
            for i in ids
        ):
            truncated += 1
    clipped_fraction = truncated / max(1, full_body_samples)
    if clipped_fraction > 0.10 or not full_body_samples:
        issue(
            "body_out_of_frame",
            "Move the camera farther back so head, feet, weapon hand, and the whole run-up stay in frame.",
        )
    camera = result.get("camera_evidence", {})
    if profile.get("camera_motion") == "moving" or camera.get("moving"):
        issue(
            "camera_motion",
            "Put the camera on a fixed support; do not pan, zoom, or cut during the drill.",
        )
    elif not camera.get("assessed"):
        issue(
            "camera_unverified",
            "Use a textured, well-lit background and a fixed camera; camera stability could not be checked.",
            False,
        )
    if profile.get("facing", "unknown") == "unknown":
        issue(
            "facing_unknown",
            "Set your facing direction to enable advance, retreat, and flèche direction measurements.",
            False,
        )
    if not result.get("candidates"):
        issue(
            "no_complete_reps",
            "Start in a steady guard, perform a deliberate movement, and return to guard. Flèche drills use the beta detector.",
            False,
        )
    unsupported = any(i["severity"] == "reject" for i in issues)
    verdict = "unsupported" if unsupported else "supported_with_warnings" if issues else "supported"
    return {
        "version": VERSION,
        "verdict": verdict,
        "coaching_allowed": not unsupported,
        "issues": issues,
        "measurements": {
            "tracking_coverage": round(coverage, 4),
            "multiple_person_fraction": round(multi_fraction, 4),
            "tracking_reacquisitions": max(0, switches),
            "body_clipped_or_low_visibility_fraction": round(clipped_fraction, 4),
        },
        "note": "QA gates are project thresholds, not calibrated recognition accuracy. Geometric reacquisitions are not verified identity switches.",
    }


class CameraCheck:
    """Background translation evidence from small thumbnails; fail visibly when texture is insufficient."""

    def __init__(self):
        self.previous = None
        self.checked = 0
        self.moved = 0

    def observe(self, rgb):
        import numpy as np

        gray = rgb.mean(axis=2).astype(float)
        h, w = gray.shape
        mask = np.ones((h, w), dtype=bool)
        mask[h // 5 : 4 * h // 5, w // 5 : 4 * w // 5] = False
        if self.previous is not None and np.std(gray[mask]) >= 10:
            a = self.previous - self.previous[mask].mean()
            b = gray - gray[mask].mean()
            zero = np.mean(np.abs(a[mask] - b[mask]))
            best, shift = zero, (0, 0)
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    if not dx and not dy:
                        continue
                    ys, xs = slice(3, h - 3), slice(3, w - 3)
                    use = mask[ys, xs]
                    error = np.mean(
                        np.abs(a[ys, xs][use] - b[3 + dy : h - 3 + dy, 3 + dx : w - 3 + dx][use])
                    )
                    if error < best:
                        best, shift = error, (dx, dy)
            self.checked += 1
            self.moved += bool(shift != (0, 0) and zero > 5 and best < zero * 0.65)
        self.previous = gray

    def summary(self):
        return {
            "method": "background_translation_v1",
            "assessed": self.checked >= 5,
            "checked_pairs": self.checked,
            "moving_pairs": self.moved,
            "moving": self.checked >= 5 and self.moved >= 3 and self.moved / self.checked > 0.20,
        }
