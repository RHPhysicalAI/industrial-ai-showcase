from pathlib import Path

from vla_training.fine_tune import (
    TRAINING_STATE_FILES,
    _latest_checkpoint_dir,
    _validate_deployable_model_dir,
)


def _write_complete_checkpoint(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text("{}")
    (path / "processor_config.json").write_text("{}")
    (path / "model.safetensors.index.json").write_text(
        '{"weight_map": {"layer.weight": "model-00001-of-00003.safetensors"}}'
    )
    (path / "model-00001-of-00003.safetensors").write_bytes(b"weights")


def test_latest_checkpoint_is_selected_by_numeric_step(tmp_path: Path) -> None:
    _write_complete_checkpoint(tmp_path / "checkpoint-2")
    _write_complete_checkpoint(tmp_path / "checkpoint-10")
    (tmp_path / "checkpoint-final").mkdir()

    assert _latest_checkpoint_dir(tmp_path).name == "checkpoint-10"


def test_deployable_checkpoint_requires_weights(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint-10"
    checkpoint.mkdir()
    (checkpoint / "config.json").write_text("{}")
    (checkpoint / "processor_config.json").write_text("{}")

    try:
        _validate_deployable_model_dir(checkpoint)
    except RuntimeError as exc:
        assert "model weights" in str(exc)
    else:
        raise AssertionError("incomplete checkpoint was accepted")


def test_training_state_files_are_not_deployable_files() -> None:
    assert "optimizer.pt" in TRAINING_STATE_FILES
    assert "trainer_state.json" in TRAINING_STATE_FILES
