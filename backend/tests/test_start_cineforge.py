from __future__ import annotations

from io import BytesIO
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


def test_wait_until_ready_never_accepts_a_dead_child_from_a_foreign_listener(tmp_path):
    candidate = service(tmp_path)
    process = SimpleNamespace(poll=lambda: 7, returncode=7)
    owned = SimpleNamespace(service=candidate, process=process)

    with pytest.raises(RuntimeError, match="exited with code 7"):
        start_cineforge.wait_until_ready(owned, lambda _url: True)


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
    owned = start_cineforge.OwnedProcess(
        service=candidate,
        process=SimpleNamespace(pid=1234),
        stdout=BytesIO(),
        stderr=BytesIO(),
    )
    owned.process.poll = lambda: None

    start_cineforge.write_state([owned], [candidate])
    payload = start_cineforge.json.loads(start_cineforge.STATE_PATH.read_text())

    assert payload["services"][0]["owned"] is True
    assert payload["services"][0]["pid"] == 1234
    assert payload["services"][1]["owned"] is False
    assert payload["services"][1]["pid"] is None


def test_recovery_replaces_only_the_failed_service(tmp_path, monkeypatch):
    backend = service(tmp_path)
    backend = start_cineforge.Service(**{**backend.__dict__, "name": "backend"})
    frontend = service(tmp_path)
    frontend = start_cineforge.Service(**{**frontend.__dict__, "name": "frontend"})
    failed = start_cineforge.OwnedProcess(
        service=backend,
        process=SimpleNamespace(pid=100, poll=lambda: 9, returncode=9),
        stdout=BytesIO(),
        stderr=BytesIO(),
        status="ready",
    )
    replacement = start_cineforge.OwnedProcess(
        service=backend,
        process=SimpleNamespace(pid=200, poll=lambda: None, returncode=None),
        stdout=BytesIO(),
        stderr=BytesIO(),
    )
    untouched = start_cineforge.OwnedProcess(
        service=frontend,
        process=SimpleNamespace(pid=300, poll=lambda: None, returncode=None),
        stdout=BytesIO(),
        stderr=BytesIO(),
        status="ready",
    )
    owned = [failed, untouched]

    monkeypatch.setattr(start_cineforge, "write_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(start_cineforge, "stop_owned", lambda _items: None)
    monkeypatch.setattr(start_cineforge, "_service_liveness_ready", lambda _service: False)
    monkeypatch.setattr(start_cineforge, "launch", lambda _service: replacement)
    monkeypatch.setattr(start_cineforge, "wait_until_ready", lambda _item: None)
    monkeypatch.setattr(start_cineforge, "_verify_backend_generation", lambda _item: None)
    monkeypatch.setattr(start_cineforge.time, "sleep", lambda _seconds: None)

    recovered = start_cineforge.recover_owned_service(
        owned,
        0,
        [],
        reason="backend exited",
    )

    assert recovered is replacement
    assert owned == [replacement, untouched]
    assert replacement.status == "ready"
    assert replacement.restart_count == 1


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


def test_primary_defaults_select_the_bundled_blokeyui_engine(monkeypatch):
    for key in (
        "CINEFORGE_COMFYUI_AUTOSTART",
        "CINEFORGE_COMFYUI_BACKEND_MANAGED",
        "CINEFORGE_COMFYUI_BASE_URL",
        "CINEFORGE_COMFYUI_WORKING_DIR",
        "CINEFORGE_COMFYUI_PYTHON_EXECUTABLE",
        "CINEFORGE_COMFYUI_MAIN_PATH",
        "CINEFORGE_COMFYUI_BOOTSTRAP_PATH",
        "CINEFORGE_COMFYUI_CUSTOM_NODES_DIR",
        "CINEFORGE_COMFYUI_SINEFORGE_PATHS_CONFIG",
        "CINEFORGE_PLANNING_MODEL_PRELOAD",
    ):
        monkeypatch.delenv(key, raising=False)

    start_cineforge.apply_primary_workstation_defaults()

    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_AUTOSTART"] == "true"
    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_BACKEND_MANAGED"] == "true"
    assert start_cineforge.os.environ["CINEFORGE_COMFYUI_BASE_URL"] == (
        "http://127.0.0.1:8190"
    )
    bundled_root = start_cineforge.REPO_ROOT / "BlokeyUI"
    assert Path(start_cineforge.os.environ["CINEFORGE_COMFYUI_WORKING_DIR"]) == bundled_root
    assert Path(start_cineforge.os.environ["CINEFORGE_COMFYUI_PYTHON_EXECUTABLE"]) == Path(
        r"C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe"
    )
    assert Path(start_cineforge.os.environ["CINEFORGE_COMFYUI_MAIN_PATH"]) == (
        bundled_root / "ComfyUI" / "main.py"
    )
    assert Path(start_cineforge.os.environ["CINEFORGE_COMFYUI_CUSTOM_NODES_DIR"]) == Path(
        r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes"
    )
    assert (
        start_cineforge.os.environ["CINEFORGE_PLANNING_MODEL_PRELOAD"]
        == "false"
    )


def test_engine_configuration_validation_covers_separate_blokeyui_tree(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "BlokeyUI"
    python = tmp_path / "runtime" / "python.exe"
    main = root / "ComfyUI" / "main.py"
    bootstrap = tmp_path / "scripts" / "run_blokeyui_engine.py"
    path_config = tmp_path / "ComfyUI" / "sineforge_engine_paths.yaml"
    custom_nodes = tmp_path / "curated-nodes"
    for path in (python, main, bootstrap, path_config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    custom_nodes.mkdir()
    monkeypatch.setenv("CINEFORGE_COMFYUI_WORKING_DIR", str(root))
    monkeypatch.setenv("CINEFORGE_COMFYUI_PYTHON_EXECUTABLE", str(python))
    monkeypatch.setenv("CINEFORGE_COMFYUI_MAIN_PATH", str(main))
    monkeypatch.setenv("CINEFORGE_COMFYUI_BOOTSTRAP_PATH", str(bootstrap))
    monkeypatch.setenv("CINEFORGE_COMFYUI_SINEFORGE_PATHS_CONFIG", str(path_config))
    monkeypatch.setenv("CINEFORGE_COMFYUI_CUSTOM_NODES_DIR", str(custom_nodes))

    start_cineforge.validate_bundled_engine_configuration()

    main.unlink()
    with pytest.raises(FileNotFoundError, match="BlokeyUI main.py"):
        start_cineforge.validate_bundled_engine_configuration()


def test_supervisor_leaves_comfyui_lifecycle_to_the_backend(tmp_path, monkeypatch):
    python = tmp_path / "python.exe"
    python.touch()
    npm = tmp_path / "npm.cmd"
    npm.touch()
    command_processor = tmp_path / "cmd.exe"
    command_processor.touch()

    monkeypatch.setenv("CINEFORGE_COMFYUI_AUTOSTART", "true")
    monkeypatch.setenv("CINEFORGE_COMFYUI_BACKEND_MANAGED", "true")
    monkeypatch.setenv("CINEFORGE_PYTHON_EXECUTABLE", str(python))
    monkeypatch.setenv("COMSPEC", str(command_processor))
    monkeypatch.setattr(start_cineforge, "_npm_executable", lambda: npm)

    services = start_cineforge.build_services()

    assert [service.name for service in services] == [
        "sulphur",
        "backend",
        "frontend",
    ]


def test_supervisor_service_topology_is_stable_when_engine_autostart_is_disabled(tmp_path, monkeypatch):
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
    monkeypatch.setattr(start_cineforge, "STATE_PATH", runtime_root / "state.json")
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: False)

    start_cineforge.acquire_lock()

    payload = start_cineforge.json.loads(lock_path.read_text(encoding="ascii"))
    assert payload["pid"] == start_cineforge.os.getpid()
    start_cineforge.release_lock()
    assert not lock_path.exists()


def test_lock_refuses_second_live_supervisor(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    lock_path = runtime_root / "supervisor.lock"
    runtime_root.mkdir()
    lock_path.write_text("1234", encoding="ascii")
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "LOCK_PATH", lock_path)
    monkeypatch.setattr(start_cineforge, "STATE_PATH", runtime_root / "state.json")
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: True)

    with pytest.raises(RuntimeError, match="already running with PID 1234"):
        start_cineforge.acquire_lock()


def test_legacy_lock_recovers_after_windows_reuses_pid(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    lock_path = runtime_root / "supervisor.lock"
    state_path = runtime_root / "state.json"
    runtime_root.mkdir()
    lock_path.write_text("2704", encoding="ascii")
    state_path.write_text(
        start_cineforge.json.dumps(
            {"supervisor_pid": 2704, "started_at_epoch": 100.0}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "LOCK_PATH", lock_path)
    monkeypatch.setattr(start_cineforge, "STATE_PATH", state_path)
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(
        start_cineforge,
        "_process_started_at_epoch",
        lambda pid: 200.0 if pid == 2704 else 300.0,
    )

    start_cineforge.acquire_lock()

    payload = start_cineforge.json.loads(lock_path.read_text(encoding="ascii"))
    assert payload["pid"] == start_cineforge.os.getpid()
    start_cineforge.release_lock()


def test_json_lock_refuses_same_process_instance(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    lock_path = runtime_root / "supervisor.lock"
    runtime_root.mkdir()
    lock_path.write_text(
        start_cineforge.json.dumps(
            {"pid": 1234, "process_started_at_epoch": 100.0}
        ),
        encoding="ascii",
    )
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "LOCK_PATH", lock_path)
    monkeypatch.setattr(start_cineforge, "STATE_PATH", runtime_root / "state.json")
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(
        start_cineforge,
        "_process_started_at_epoch",
        lambda _pid: 100.5,
    )

    with pytest.raises(RuntimeError, match="already running with PID 1234"):
        start_cineforge.acquire_lock()


def test_lock_recovers_when_reused_pid_belongs_to_non_python_process(
    tmp_path,
    monkeypatch,
):
    runtime_root = tmp_path / "runtime"
    lock_path = runtime_root / "supervisor.lock"
    runtime_root.mkdir()
    lock_path.write_text("2704", encoding="ascii")
    monkeypatch.setattr(start_cineforge, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(start_cineforge, "LOCK_PATH", lock_path)
    monkeypatch.setattr(start_cineforge, "STATE_PATH", runtime_root / "state.json")
    monkeypatch.setattr(start_cineforge, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(
        start_cineforge,
        "_process_started_at_epoch",
        lambda _pid: None,
    )
    monkeypatch.setattr(
        start_cineforge,
        "_process_executable_name",
        lambda _pid: "svchost.exe",
    )

    start_cineforge.acquire_lock()

    payload = start_cineforge.json.loads(lock_path.read_text(encoding="ascii"))
    assert payload["pid"] == start_cineforge.os.getpid()
    start_cineforge.release_lock()
