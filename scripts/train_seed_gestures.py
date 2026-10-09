"""Fit an experimental model from reviewed clips without claiming deployment readiness.

Unknown capture metadata stays unknown. Label, source, crop and pose integrity
checks still apply. Related source footage stays together in diagnostic folds.
This script never promotes a model or changes accepted labels.
"""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.preprocessing import StandardScaler

from fencecoach.footwork import VERSION
from fencecoach.gestures import FEATURES, LABELS
from fencecoach.training_data import collect_corpus


def fit(x, y):
    scaler = StandardScaler().fit(x)
    classifier = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=740).fit(
        scaler.transform(x), y
    )
    return scaler, classifier


def train(corpus):
    if any(clip["status"] == "invalid_source" for clip in corpus["clips"]):
        raise ValueError("Resolve source or annotation integrity errors before fitting.")
    rows = corpus["rows"]
    counts = Counter(row["label"] for row in rows)
    if len(counts) < 2:
        raise ValueError("Need usable reviewed pose windows for at least two classes.")
    x = np.asarray([row["features"] for row in rows])
    y = np.asarray([row["label"] for row in rows])
    groups = np.asarray([row["group"] for row in rows])
    folds = []
    for group in sorted(set(groups)):
        held = groups == group
        train_mask = ~held
        if len(set(y[train_mask])) < 2:
            continue
        scaler, classifier = fit(x[train_mask], y[train_mask])
        prediction = classifier.predict(scaler.transform(x[held]))
        folds.append(
            {
                "held_out_group": group,
                "train_groups": sorted(set(groups[train_mask])),
                "train_windows": int(train_mask.sum()),
                "held_out_windows": int(held.sum()),
                "unseen_test_classes": sorted(set(y[held]) - set(y[train_mask])),
                "macro_f1": float(f1_score(y[held], prediction, average="macro")),
                "classification_report": classification_report(
                    y[held], prediction, output_dict=True, zero_division=0
                ),
            }
        )
    scaler, classifier = fit(x, y)
    return {
        "schema": "fencecoach-linear-v2",
        "task": "gesture",
        "feature_version": VERSION,
        "version": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "promoted": False,
        "development_only": True,
        "features": list(FEATURES),
        "window_ms": corpus["window_ms"],
        "stride_ms": corpus["window_ms"] // 2,
        "classes": classifier.classes_.tolist(),
        "weights": classifier.coef_.tolist(),
        "intercept": classifier.intercept_.tolist(),
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "class_windows": dict(counts),
        "sources": corpus["sources"],
        "evaluation": {
            "method": "leave-connected-source-group-out diagnostics",
            "folds": folds,
            "independent_groups": len(set(groups)),
            "generalization_validated": False,
            "note": "Final candidate uses all usable reviewed windows. No training accuracy is presented as validation.",
        },
        "promotion_checks": {"production_readiness": False},
        "limitations": [
            "Experimental candidate; unavailable to production gesture inference.",
            "Unknown camera metadata remains unknown; camera travel features are masked.",
            "Overlapping windows are correlated and do not count as independent examples.",
            "Pose quality and selected-athlete identity can limit usable reviewed intervals.",
            "No reliable technique score or athlete-generalization claim follows from this fit.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/training"))
    parser.add_argument("--output", type=Path, default=Path("models/gestures-seed-candidate.json"))
    parser.add_argument("--window-ms", type=int, choices=(500, 750, 1000, 1500), default=500)
    args = parser.parse_args()
    corpus = collect_corpus(args.data, classes=LABELS, window_ms=args.window_ms, development=True)
    model = train(corpus)
    model["clip_audit"] = corpus["clips"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "path": str(args.output),
                "class_windows": model["class_windows"],
                "sources": len(model["sources"]),
                "evaluation": model["evaluation"],
            }
        )
    )


if __name__ == "__main__":
    main()
