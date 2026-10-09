"""Reusable compact session evidence, computed after video processing."""


def prepare_evidence(result):
    return {
        "schema": "session-evidence-v1",
        "pipeline_version": result.get("pipeline_version"),
        "quality_gate": result.get("quality_gate"),
        "capture_profile": result.get("capture_profile", {}),
        "repetitions": [
            {
                "rep_number": c.get("rep_number", i + 1),
                "onset_ms": c.get("onset_ms"),
                "peak_ms": c["start_ms"],
                "recovery_end_ms": c["end_ms"],
                "classification": c.get("classification"),
                "measurements": c.get("measurements", []),
            }
            for i, c in enumerate(result.get("candidates", []))
        ],
        "fleche_beta": result.get("fleche_events", []),
        "movement_timeline": result.get("movement_timeline", {}),
        "measurement_limit": "Image-plane evidence; no direct balance, blade contact, or tactical intent.",
    }
