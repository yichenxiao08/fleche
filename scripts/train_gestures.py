"""Train a gesture or activity classifier from human-reviewed pose windows.

The trainer writes its readiness report first and stops before fitting unless
all versioned data, diversity, integrity, and athlete-held-out split gates pass.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score, log_loss
from sklearn.preprocessing import StandardScaler

from fencecoach.footwork import VERSION
from fencecoach.gestures import FEATURES
from fencecoach.training_data import collect_corpus, readiness


def calibration_error(probabilities, truth, bins=10):
    confidence = probabilities.max(axis=1)
    prediction = probabilities.argmax(axis=1)
    correct = prediction == truth
    error = 0.0
    for lower in np.linspace(0, 1, bins, endpoint=False):
        selected = (confidence >= lower) & (confidence < lower + 1 / bins)
        if selected.any():
            error += selected.mean() * abs(correct[selected].mean() - confidence[selected].mean())
    return float(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("gesture", "activity"), default="gesture")
    parser.add_argument("--data", type=Path, default=Path("data/training"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument(
        "--classes", help="Optional comma-separated class set; every class must pass."
    )
    parser.add_argument("--promote", action="store_true")
    parser.add_argument("--window-ms", type=int, choices=(500, 750, 1000, 1500), default=750)
    args = parser.parse_args()

    classes = (
        [label.strip() for label in args.classes.split(",") if label.strip()]
        if args.classes
        else None
    )
    report_path = args.readiness_report or args.data / f"readiness-{args.task}.json"
    try:
        corpus = collect_corpus(args.data, args.task, classes, args.window_ms)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    report, split = readiness(corpus)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["training_ready"] or split is None:
        blocked = sum(not check["passed"] for check in report["checks"])
        raise SystemExit(
            f"Training stopped before model fitting: {blocked} readiness checks are blocked. "
            f"See {report_path} for per-class counts and collection gaps."
        )

    rows, sources = corpus["rows"], corpus["sources"]
    x = np.asarray([row["features"] for row in rows])
    y = np.asarray([row["label"] for row in rows])
    groups = np.asarray([row["group"] for row in rows])
    train, held_out = split
    scaler = StandardScaler().fit(x[train])
    classifier = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=740).fit(
        scaler.transform(x[train]), y[train]
    )
    held_x = scaler.transform(x[held_out])
    predictions = classifier.predict(held_x)
    probabilities = classifier.predict_proba(held_x)
    majority = DummyClassifier(strategy="most_frequent").fit(x[train], y[train])
    majority_predictions = majority.predict(x[held_out])
    class_report = classification_report(
        y[held_out], predictions, output_dict=True, zero_division=0
    )
    recalls = {label: class_report.get(label, {}).get("recall", 0.0) for label in corpus["classes"]}
    macro_f1 = float(f1_score(y[held_out], predictions, average="macro"))
    baseline_f1 = float(f1_score(y[held_out], majority_predictions, average="macro"))
    ece = calibration_error(probabilities, classifier.classes_.searchsorted(y[held_out]))
    confidence = probabilities.max(axis=1)
    accepted = confidence >= 0.65
    accepted_accuracy = (
        float((predictions[accepted] == y[held_out][accepted]).mean()) if accepted.any() else 0.0
    )
    evaluation = {
        "macro_f1": macro_f1,
        "majority_baseline_macro_f1": baseline_f1,
        "beats_majority_baseline": macro_f1 > baseline_f1,
        "accuracy": float(accuracy_score(y[held_out], predictions)),
        "per_class_recall": recalls,
        "classification_report": class_report,
        "held_out_log_loss": float(
            log_loss(y[held_out], probabilities, labels=classifier.classes_)
        ),
        "expected_calibration_error_10_bins": ece,
        "confidence_at_least_0_65_coverage": float(accepted.mean()),
        "confidence_at_least_0_65_accuracy": accepted_accuracy,
        "train_athletes": sorted({sources[rows[i]["source_index"]]["athlete_id"] for i in train}),
        "held_out_athletes": sorted(
            {sources[rows[i]["source_index"]]["athlete_id"] for i in held_out}
        ),
        "train_groups": sorted(set(groups[train])),
        "held_out_groups": sorted(set(groups[held_out])),
        "train_windows": len(train),
        "held_out_windows": len(held_out),
        "split": "athlete-disjoint, connected source/session/cohort groups",
    }
    promotion_checks = {
        "macro_f1_at_least_0_75": macro_f1 >= 0.75,
        "beats_majority_baseline": macro_f1 > baseline_f1,
        "every_class_recall_at_least_0_60": all(value >= 0.60 for value in recalls.values()),
        "expected_calibration_error_at_most_0_15": ece <= 0.15,
    }
    promoted = bool(args.promote and all(promotion_checks.values()))
    output_path = args.output or Path(
        "models/gestures.json" if args.task == "gesture" else "models/activity.json"
    )
    model = {
        "schema": "fencecoach-linear-v2",
        "task": args.task,
        "feature_version": VERSION,
        "version": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "promoted": promoted,
        "features": list(FEATURES),
        "window_ms": args.window_ms,
        "stride_ms": args.window_ms // 2,
        "classes": classifier.classes_.tolist(),
        "weights": classifier.coef_.tolist(),
        "intercept": classifier.intercept_.tolist(),
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "evaluation": evaluation,
        "promotion_checks": promotion_checks,
        "class_windows": dict(Counter(y)),
        "sources": sources,
        "limitations": [
            "Labels are human-reviewed but may still contain errors.",
            "Readiness thresholds are collection targets, not fencing technique standards.",
            "Evaluation uses held-out athletes but does not replace prospective testing.",
            "The logistic model probabilities are not formally calibrated beyond the reported check.",
            "2D pose classification depends on matching capture conditions.",
        ],
    }
    destination = (
        output_path if promoted else output_path.with_name(output_path.stem + "-candidate.json")
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(destination), "promoted": promoted, "evaluation": evaluation}))
    if args.promote and not promoted:
        raise SystemExit(f"Promotion refused: {promotion_checks}. Existing active model preserved.")


if __name__ == "__main__":
    main()
