"""Download pinned MFAD skeletons and fit a separate research action classifier.

This artifact cannot be promoted into the MediaPipe video classifier. Published
whole-action labels are not frame-level activity or movement-phase annotations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

COMMIT = "153c5a630230805a1d469bd9fb46cde2fc128eda"
BASE = f"https://raw.githubusercontent.com/EMRGSZU/MFAD/{COMMIT}/"
CLASSES = {"a1": "lunge", "a2": "advance_lunge", "a3": "fleche_author_label"}


def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(url, timeout=45) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def features(array):
    # Observed source layout is T,V,C, unlike the generic README example.
    if array.ndim != 3 or array.shape[1:] != (18, 3) or len(array) < 8:
        raise ValueError(f"Unsupported skeleton shape: {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError("Nonfinite skeleton coordinates")
    # Missing joints must not masquerade as motion through the origin.
    if np.any(np.all(array == 0, axis=2)):
        raise ValueError("Zero-valued missing joint")
    center = array.mean(axis=1, keepdims=True)
    pose = array - center
    scale = np.median(np.linalg.norm(pose, axis=2))
    if scale <= 1e-8:
        raise ValueError("Degenerate body scale")
    pose /= scale
    travel = (center[:, 0, :] - center[0, 0, :]) / scale
    signal = np.concatenate((pose.reshape(len(array), -1), travel), axis=1)
    # Use normalized action progress; no assumed frame rate or m/s claims.
    times = np.linspace(0, 1, len(array))
    sampled = np.stack([np.interp(np.linspace(0, 1, 24), times, s) for s in signal.T], axis=1)
    return sampled.ravel()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data", type=Path, default=Path("data/research/mfad"))
    parser.add_argument("--index", type=Path, default=Path("tmp/mfad-tree.json"))
    parser.add_argument("--output", type=Path, default=Path("models/mfad-research-candidate.json"))
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    if not args.index.exists():
        args.index.parent.mkdir(parents=True, exist_ok=True)
        args.index.write_bytes(
            fetch(f"https://api.github.com/repos/EMRGSZU/MFAD/git/trees/{COMMIT}?recursive=1")
        )
    tree = json.loads(args.index.read_text(encoding="utf-8-sig"))
    if tree["sha"] != COMMIT or tree.get("truncated"):
        raise ValueError("Dataset index must match the complete pinned commit")
    entries = [
        e for e in tree["tree"] if re.fullmatch(r"skeleton/[123]_p\d+_a[123]_\d+\.npy", e["path"])
    ]

    def acquire(entry):
        path = args.data / entry["path"]
        if not path.exists():
            if not args.download:
                raise FileNotFoundError(f"Missing {path}; run with --download")
            content = fetch(BASE + entry["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            content = path.read_bytes()
        git_sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if git_sha != entry["sha"]:
            raise ValueError(f"Source hash mismatch: {path}")
        if not path.exists():
            path.write_bytes(content)
        return {
            "path": entry["path"],
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }

    manifest = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for record in pool.map(acquire, entries):
            manifest.append(record)
            if len(manifest) % 100 == 0:
                print(f"Acquired {len(manifest)}/{len(entries)} skeleton sequences", flush=True)
    (args.data / "manifest.json").write_text(
        json.dumps(
            {
                "source": "https://github.com/EMRGSZU/MFAD",
                "commit": COMMIT,
                "label_provenance": "dataset_author",
                "files": manifest,
                "license": "No explicit license file found in pinned repository; redistribution not enabled.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    x, y, groups, records, rejected = [], [], [], [], []
    for record in manifest:
        path = args.data / record["path"]
        level, person, action, repetition = path.stem.split("_")
        try:
            vector = features(np.load(path, allow_pickle=False))
        except ValueError as exc:
            rejected.append({"path": record["path"], "reason": str(exc)})
            continue
        x.append(vector)
        y.append(CLASSES[action])
        # Conservatively keep the same participant number together even across levels.
        groups.append(person)
        records.append(record)
    x, y, groups = np.asarray(x), np.asarray(y), np.asarray(groups)
    train, held = next(
        GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=740).split(x, y, groups)
    )
    if set(y[train]) != set(CLASSES.values()) or set(y[held]) != set(CLASSES.values()):
        raise ValueError(
            "Prespecified subject split lacks a class; do not tune using holdout scores"
        )
    # Fit preprocessing and classifier on training athletes only.
    scaler = StandardScaler().fit(x[train])
    model = LogisticRegression(C=0.1, max_iter=3000, class_weight="balanced", random_state=740)
    model.fit(scaler.transform(x[train]), y[train])
    predicted = model.predict(scaler.transform(x[held]))
    evaluation = dict(
        accuracy=float(accuracy_score(y[held], predicted)),
        macro_f1=float(f1_score(y[held], predicted, average="macro")),
        report=classification_report(y[held], predicted, output_dict=True, zero_division=0),
        confusion_matrix=confusion_matrix(y[held], predicted, labels=model.classes_).tolist(),
        confusion_matrix_labels=model.classes_.tolist(),
        train_subjects=sorted(set(groups[train])),
        held_out_subjects=sorted(set(groups[held])),
        train_sequences=len(train),
        held_out_sequences=len(held),
        train_counts=dict(Counter(y[train])),
        held_out_counts=dict(Counter(y[held])),
        split="prespecified subject-disjoint 70/30, seed 740",
        baseline_accuracy=float(np.mean(y[held] == Counter(y[train]).most_common(1)[0][0])),
    )
    artifact = dict(
        schema="fencecoach-mfad-whole-action-research-v1",
        promoted=False,
        source_commit=COMMIT,
        features="24 progress samples of centered scale-normalized 18-joint XYZ plus centroid travel",
        classes=model.classes_.tolist(),
        weights=model.coef_.tolist(),
        intercept=model.intercept_.tolist(),
        mean=scaler.mean_.tolist(),
        scale=scaler.scale_.tolist(),
        evaluation=evaluation,
        limitations=[
            "Depth-camera whole-action classification, not MediaPipe frame-level recognition.",
            "No walking, en-garde, retreat, recovery or background negatives; closed-set only.",
            "No phase boundary labels or technique quality labels.",
            "README inconsistently calls class a3 jumps/fleche; preserved as fleche_author_label.",
            "Subject-disjoint split does not establish cross-camera, cross-site or phone-video accuracy.",
            "No explicit source license; redistribution and production use need clarification.",
        ],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact), encoding="utf-8")
    report = dict(
        source_commit=COMMIT,
        acquired=len(manifest),
        usable=len(x),
        subjects=len(set(groups)),
        classes=dict(Counter(y)),
        rejected=rejected,
        evaluation=evaluation,
        limitations=artifact["limitations"],
        split_files={
            "train": [records[i]["path"] for i in train],
            "held_out": [records[i]["path"] for i in held],
        },
    )
    (args.data / "training-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "model": str(args.output),
                "acquired": len(manifest),
                "usable": len(x),
                "subjects": len(set(groups)),
                "evaluation": evaluation,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
