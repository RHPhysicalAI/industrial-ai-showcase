from pathlib import Path

from openvla_server.s3_loader import _artifact_is_complete, parse_s3_uri


def _write_gr00t_metadata(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text("{}")
    (path / "processor_config.json").write_text("{}")


def test_parse_s3_uri_rejects_non_s3() -> None:
    try:
        parse_s3_uri("https://example.invalid/model")
    except ValueError as exc:
        assert "Not an S3 URI" in str(exc)
    else:
        raise AssertionError("non-S3 URI was accepted")


def test_partial_gr00t_cache_is_not_complete(tmp_path: Path) -> None:
    cache = tmp_path / "partial"
    _write_gr00t_metadata(cache)

    assert not _artifact_is_complete(cache)


def test_complete_sharded_gr00t_cache_is_complete(tmp_path: Path) -> None:
    cache = tmp_path / "gr00t"
    _write_gr00t_metadata(cache)
    (cache / "model.safetensors.index.json").write_text(
        '{"weight_map": {"layer.weight": "model-00001-of-00002.safetensors"}}'
    )
    (cache / "model-00001-of-00002.safetensors").write_bytes(b"weights")

    assert _artifact_is_complete(cache)


def test_onnx_cache_is_complete_without_huggingface_metadata(tmp_path: Path) -> None:
    cache = tmp_path / "onnx"
    cache.mkdir()
    (cache / "model.onnx").write_bytes(b"onnx")

    assert _artifact_is_complete(cache)
