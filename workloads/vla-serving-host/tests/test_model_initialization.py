import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

from openvla_server.model import GR00TAdapter


def test_gr00t_initialization_is_serialized(monkeypatch) -> None:
    policy_calls = 0
    register_calls = 0

    class FakePolicy:
        def __init__(self, *, embodiment_tag: str, model_path: str, device: str) -> None:
            nonlocal policy_calls
            policy_calls += 1
            time.sleep(0.02)

    gr00t = types.ModuleType("gr00t")
    gr00t.__path__ = []
    policy = types.ModuleType("gr00t.policy")
    policy.__path__ = []
    gr00t_policy = types.ModuleType("gr00t.policy.gr00t_policy")
    gr00t_policy.Gr00tPolicy = FakePolicy
    monkeypatch.setitem(sys.modules, "gr00t", gr00t)
    monkeypatch.setitem(sys.modules, "gr00t.policy", policy)
    monkeypatch.setitem(sys.modules, "gr00t.policy.gr00t_policy", gr00t_policy)

    adapter = GR00TAdapter("/model", embodiment_tag="NEW_EMBODIMENT")

    def register_once() -> None:
        nonlocal register_calls
        register_calls += 1

    monkeypatch.setattr(adapter, "_register_custom_embodiment", register_once)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: adapter._ensure_loaded(), range(2)))

    assert register_calls == 1
    assert policy_calls == 1
    assert adapter._policy is not None
