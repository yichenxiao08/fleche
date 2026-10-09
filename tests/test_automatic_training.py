import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fencecoach.automatic_training import AutomaticTraining
from fencecoach.dataset_labels import DatasetAnnotations, training_track


class AutomaticTrainingTests(unittest.TestCase):
    def test_legacy_alias_requires_unique_track_and_crop(self):
        labels = DatasetAnnotations.model_validate(
            {
                "crop": {"x": 0.22, "y": 0.32, "width": 0.45, "height": 0.64},
                "segments": [
                    {
                        "start_ms": 0,
                        "end_ms": 1000,
                        "label": "lunge",
                        "layer": "footwork",
                        "track_id": "foreground-left-rigin",
                    }
                ],
            }
        )
        self.assertEqual(training_track(labels), "foreground-left-rigin")
        self.assertEqual(labels.primary_track_id, "primary")
        labels.crop = DatasetAnnotations().crop
        self.assertEqual(training_track(labels), "primary")

    def test_completed_fingerprint_skips_refitting(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            worker = AutomaticTraining(project / "data", project)
            model = {
                "class_windows": {"lunge": 4, "en_garde": 5},
                "version": "test",
                "evaluation": {"generalization_validated": False},
            }

            def command(script, *args):
                target = project / "models/gestures-seed-candidate.json"
                target.parent.mkdir(exist_ok=True)
                target.write_text(json.dumps(model))

            with (
                patch.object(worker, "command", side_effect=command) as fit,
                patch("fencecoach.automatic_training.collect_corpus", return_value={}),
                patch(
                    "fencecoach.automatic_training.readiness",
                    return_value=({"training_ready": False}, None),
                ),
            ):
                worker.run_once()
                worker.run_once()
                self.assertEqual(fit.call_count, 1)
                self.assertEqual(worker.status()["usable_windows"], 9)
                self.assertFalse(worker.status()["promoted"])
                source = worker.root / "commons/clip/source.json"
                source.parent.mkdir(parents=True)
                source.write_text("{}")
                worker.run_once()
                self.assertEqual(fit.call_count, 2)


if __name__ == "__main__":
    unittest.main()
