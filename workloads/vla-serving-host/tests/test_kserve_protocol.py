from openvla_server.kserve_protocol import KServePredictRequest


def test_kserve_instance_defaults_trace_id() -> None:
    request = KServePredictRequest(
        instances=[{"image": "", "instruction": "move to dock-b"}]
    )

    assert request.instances[0].trace_id.startswith("kserve-")


def test_kserve_request_rejects_empty_batch() -> None:
    try:
        KServePredictRequest(instances=[])
    except ValueError as exc:
        assert "at least 1 item" in str(exc)
    else:
        raise AssertionError("an empty KServe batch must be rejected")
