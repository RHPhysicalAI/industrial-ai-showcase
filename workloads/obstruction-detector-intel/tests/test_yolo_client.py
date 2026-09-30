# This project was developed with assistance from AI tools.
"""Unit tests for YOLOv8 detection parsing.

Several of these encode findings from the Task 4.1 validation
(docs/13-intel-task4-validation-report.md) as regressions, so that the
closed-vocabulary behaviour is asserted rather than rediscovered.
"""

import numpy as np

from obstruction_detector_intel.yolo_client import (
    COCO_CLASSES,
    OBSTRUCTION_CLASSES,
    YoloClient,
)

PERSON = COCO_CLASSES.index("person")
CHAIR = COCO_CLASSES.index("chair")
BEAR = COCO_CLASSES.index("bear")


def make_response(detections):
    """Build a KServe v2 response with one candidate per (class_id, confidence).

    Real YOLOv8m emits [1, 84, 8400]; the parser reads the shape off the
    response, so a narrower N keeps the fixtures readable.
    """
    n = max(len(detections), 1)
    grid = np.zeros((84, n), dtype=np.float32)
    for i, (class_id, conf) in enumerate(detections):
        grid[0:4, i] = [10.0, 20.0, 30.0, 40.0]  # bbox x, y, w, h
        grid[4 + class_id, i] = conf
    return {"outputs": [{"shape": [1, 84, n], "data": grid.flatten().tolist()}]}


def parse(detections):
    client = YoloClient.__new__(YoloClient)  # no HTTP client needed
    return client._parse_detections(make_response(detections))


def test_empty_outputs_returns_zero_confidence():
    client = YoloClient.__new__(YoloClient)
    verdict = client._parse_detections({"outputs": []})
    assert verdict.obstruction is False
    assert verdict.confidence == 0.0


def test_person_above_threshold_is_an_obstruction():
    verdict = parse([(PERSON, 0.93)])
    assert verdict.obstruction is True
    assert verdict.label == "person"
    assert verdict.confidence == np.float32(0.93)


def test_bear_is_detected_but_is_not_an_obstruction():
    """A high-confidence COCO class outside OBSTRUCTION_CLASSES reads clear.

    This is the warehouse_1.jpg case from the validation report: the model
    detects a bear at 0.958 and the detector correctly reports clear.
    """
    assert "bear" not in OBSTRUCTION_CLASSES
    verdict = parse([(BEAR, 0.958)])
    assert verdict.obstruction is False
    assert verdict.label == "clear"


def test_detection_below_confidence_threshold_is_ignored():
    verdict = parse([(PERSON, 0.49)])
    assert verdict.obstruction is False
    assert verdict.label == "clear"


def test_highest_confidence_obstruction_wins():
    verdict = parse([(PERSON, 0.62), (CHAIR, 0.88)])
    assert verdict.obstruction is True
    assert verdict.label == "chair"


def test_obstruction_wins_over_higher_confidence_non_obstruction():
    """A more confident non-obstruction class must not mask a real obstruction."""
    verdict = parse([(BEAR, 0.99), (PERSON, 0.55)])
    assert verdict.obstruction is True
    assert verdict.label == "person"


def test_no_coco_class_means_clear_which_is_the_pallet_false_negative():
    """The decisive Task 4.1 counterexample, in miniature.

    A pallet is not in COCO-80, so nothing clears the threshold and the
    detector reports clear on a genuinely obstructed aisle. This test asserts
    the *current* behaviour so the limitation is visible in the suite rather
    than surfacing in the field; it is the reason Task 4.1 is a NO-GO.
    """
    verdict = parse([])
    assert verdict.obstruction is False
    assert verdict.label == "clear"


def test_clear_verdict_confidence_is_hardcoded_not_measured():
    """Documents a known wart: the clear branch returns 1.0 regardless.

    It is not a model confidence. Logs showing `confidence: 1.0` on clear
    frames are therefore meaningless and must not be read as certainty.
    """
    assert parse([]).confidence == 1.0
    assert parse([(BEAR, 0.51)]).confidence == 1.0
