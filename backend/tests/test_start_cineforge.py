from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import start_cineforge


def service(tmp_path: Path, *, urls: tuple[str, ...] = ("http://one", "http://two")):
    executable = tmp_path / "runtime.exe"
    executable.touch()
    return start_cineforge.Service(
        name="test",
        cwd=tmp_path,
        executable=executable,
        args=(),
        readiness_urls=urls,
        timeout_seconds=0.01,
    )


def test_ready_requires_every_readiness_endpoint(tmp_path):
    candidate = service(tmp_path)
    calls = []

    def fake_probe(url):
        calls.append(url)
        return url == "http://one"

    assert start_cineforge.is_ready(candidate, fake_probe) is False
    assert calls == ["http://one", "http://two"]


def test_validate_service_rejects_missing_executable(tmp_path):
    candidate = service(tmp_path)
    candidate.executable.unlink()

    with pytest.raises(FileNotFoundError, match="executable does not exist"):
        start_cineforge.validate_service(candidate)


def test_wait_until_ready_fails_if_child_exits(tmp_path):
    candidate = service(tmp_path)
    process = SimpleNamespace(poll=lambda: 7, returncode=7)
    owned = SimpleNamespace(service=candidate, process=process)

    with pytest.raises(RuntimeError, match="exited with code 7"):
        start_cineforge.wait_until_ready(owned, lambda _url: False)


def test_wait_until_ready_accepts_successful_nonpersistent_bootstrap(tmp_path):
    candidate = service(tmp_path)
    candidate = start_cineforge.Service(
        **{
            **candidate.__dict__,
            "persistent": False,
            "always_start": True,
        }
    )
    process = SimpleNamespace(poll=lambda: 0, returncode=0)
    owned = SimpleNamespace(service=candidate, process=process)

    start_cineforge.wait_until_ready(owned, lambda _url: True)


def test_state_distinguishes_owned_and_reused(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "STATE_PATH", runtime_root / "state.json")
    candidate = service(tmp_path)
    owned = SimpleNamespace(
        service=candidate,
        process=SimpleNamespace(pid=1234),
    )

    start_cineforge.write_state([owned], [candidate])
    payload = start_cineforge.json.loads(start_cineforge.STATE_PATH.read_text())

    assert payload["services"][0]["owned"] is True
    assert payload["services"][0]["pid"] == 1234
    assert payload["services"][1]["owned"] is False
    assert payload["services"][1]["pid"] is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("https://127.0.0.1:8188", "http loopback"),
        ("http://example.com:8188", "non-loopback"),
        ("http://user:pass@127.0.0.1:8188", "credentials"),
        ("http://127.0.0.1:8188/path", "without a path"),
    ],
)
def test_comfyui_url_rejects_unsafe_targets(monkeypatch, value, message):
    monkeypatch.setenv("CINEFORGE_COMFYUI_BASE_URL", value)

    with pytest.raises(ValueError, match=message):
        start_cineforge._loopback_base_url(
            "CINEFORGE_COMFYUI_BASE_URL",
            "http://127.0.0.1:8188",
        )


@pytest.mark.parametrize("value", ["0", "65536", "8010&calc", "-1"])
def test_port_rejects_invalid_or_injectable_values(monkeypatch, value):
    monkeypatch.setenv("CINEFORGE_BACKEND_PORT", value)

    with pytest.raises(ValueError, match="CINEFORGE_BACKEND_PORT"):
        start_cineforge._port("CINEFORGE_BACKEND_PORT", 8010)


def test_command_path_rejects_shell_metacharacters(monkeypatch):
    monkeypatch.setenv("CINEFORGE_PYTHON_EXECUTABLE", r"C:\safe&unexpected\python.exe")

    with pytest.raises(ValueError, match="shell metacharacters"):
        start_cineforge._env_path(
            "CINEFORGE_PYTHON_EXECUTABLE",
            Path(r"C:\safe\python.exe"),
        )


def test_primary_defaults_select_the_ltx_comfyui_runtime(monkeypatch):
    for key in (
        "CINEFORGE_COMFYUI_AUTOSTART",
        "CINEFORGE_COMFYUI_BASE_URL",
        "CINEFORGE_COMFYUI_WORKING_DIR",
        "CINEFORGE_COMFYUI_LAUNCHER",
        "CINEFORGE_PLANNING_MODEL_PRELOAD",
    ):
        monkeypatch.delenv(key, raising=False)

    start_cineforge.apply_primary_workstation_defaults()

    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_AUTOSTART"] == "false"
    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_BASE_URL"] == (
        "http://127.0.0.1:8888"
    )
    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_WORKING_DIR"] == (
        r"C:\ComfyUI\LTX\ComfyUI"
    )
    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_LAUNCHER"] == (
        r"C:\ComfyUI\LTX\ComfyUI\run_cineforge_ltx.bat"
    )
    assert (
        start_cineforge.os.environ["CINEFORGE_PLANNING_MODEL_PRELOAD"]
        == "false"
    )


def test_supervisor_does_not_launch_the_legacy_external_runner(tmp_path, monkeypatch):
    comfy_root = tmp_path / "ltx"
    comfy_root.mkdir()
    launcher = comfy_root / "run_cineforge_ltx.bat"
    launcher.touch()
    python = tmp_path / "python.exe"
    python.touch()
    npm = tmp_path / "npm.cmd"
    npm.touch()
    command_processor = tmp_path / "cmd.exe"
    command_processor.touch()

    monkeypatch.setenv("CINEFORGE_COMFYUI_WORKING_DIR", str(comfy_root))
    monkeypatch.setenv("CINEFORGE_COMFYUI_LAUNCHER", str(launcher))
    monkeypatch.setenv("CINEFORGE_COMFYUI_AUTOSTART", "true")
    monkeypatch.setenv("CINEFORGE_PYTHON_EXECUTABLE", str(python))
    monkeypatch.setenv("COMSPEC", str(command_processor))
    monkeypatch.setattr(start_cineforge, "_npm_executable", lambda: npm)

    services = start_cineforge.build_services()

    assert [service.name for service in services] == [
        "sulphur",
        "comfyui",
        "backend",
        "frontend",
    ]


def test_supervisor_skips_comfyui_when_autostart_is_disabled(tmp_path, monkeypatch):
    python = tmp_path / "python.exe"
    python.touch()
    npm = tmp_path / "npm.cmd"
    npm.touch()
    command_processor = tmp_path / "cmd.exe"
    command_processor.touch()

    monkeypatch.setenv("CINEFORGE_COMFYUI_AUTOSTART", "false")
    monkeypatch.setenv("CINEFORGE_PYTHON_EXECUTABLE", str(python))
    monkeypatch.setenv("COMSPEC", str(command_processor))
    monkeypatch.setattr(start_cineforge, "_npm_executable", lambda: npm)

    services = start_cineforge.build_services()

    assert [service.name for service in services] == [
        "sulphur",
        "backend",
        "frontend",
    ]


def test_lock_recovers_when_recorded_owner_is_stale(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    lock_path = runtime_root / "supervisor.lock"
    runtime_root.mkdir()
    lock_path.write_text("99999999", encoding="ascii")
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "LOCK_PATH", lock_path)
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: False)

    start_cineforge.acquire_lock()

    assert lock_path.read_text(encoding="ascii") == str(start_cineforge.os.getpid())
    start_cineforge.release_lock()
    assert not lock_path.exists()


def test_lock_refuses_second_live_supervisor(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    lock_path = runtime_root / "supervisor.lock"
    runtime_root.mkdir()
    lock_path.write_text("1234", encoding="ascii")
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "LOCK_PATH", lock_path)
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: True)

    with pytest.raises(RuntimeError, match="already running with PID 1234"):
        start_cineforge.acquire_lock()
