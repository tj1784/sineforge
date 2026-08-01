from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_sulphur.py"
)
SPEC = importlib.util.spec_from_file_location(
    "sineforge_bootstrap_sulphur_test_module",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_on_demand_bootstrap_empties_lm_studio_without_loading(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    lms = tmp_path / "lms.exe"
    lms.touch()
    model = tmp_path / "qwen.gguf"
    model.touch()
    calls: list[tuple[str, ...]] = []

    monkeypatch.setenv("CINEFORGE_PLANNING_MODEL_PRELOAD", "false")
    monkeypatch.setattr(
        bootstrap,
        "_configured_path",
        lambda name, default: lms,
    )
    monkeypatch.setattr(
        bootstrap,
        "_selected_model",
        lambda: (model, "qwen-key", "qwen-id"),
    )
    monkeypatch.setattr(
        bootstrap,
        "_loaded_models",
        lambda executable: [
            {"identifier": "qwen-id"},
            {"identifier": "other-local-model"},
        ],
    )

    def fake_run(executable, *args, **kwargs):
        calls.append(tuple(args))
        return subprocess.CompletedProcess([str(executable), *args], 0)

    monkeypatch.setattr(bootstrap, "_run", fake_run)

    assert bootstrap.main() == 0
    assert ("server", "start", "--port", "1234", "--bind", "127.0.0.1") in calls
    assert ("unload", "qwen-id") in calls
    assert ("unload", "other-local-model") in calls
    assert not any(call and call[0] == "load" for call in calls)
    assert "selected for on-demand use" in capsys.readouterr().out


def test_planning_preload_flag_rejects_unknown_values(monkeypatch) -> None:
    monkeypatch.setenv("CINEFORGE_PLANNING_MODEL_PRELOAD", "sometimes")

    try:
        bootstrap._configured_bool("CINEFORGE_PLANNING_MODEL_PRELOAD", True)
    except ValueError as exc:
        assert "must be a boolean" in str(exc)
    else:
        raise AssertionError("Invalid preload flag unexpectedly succeeded.")
