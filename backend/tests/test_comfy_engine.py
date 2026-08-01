from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from backend.app.core.config import Settings
from backend.app.services.comfy.engine import (
    ComfyEngineError,
    ComfyEngineManager,
    async_comfy_prompt_submission_guard,
    comfy_prompt_submission_guard,
)


def engine_settings(tmp_path: Path) -> Settings:
    root = tmp_path / "BlokeyUI"
    python = root / "python_embeded" / "python.exe"
    main = root / "ComfyUI" / "main.py"
    custom_nodes = root / "ComfyUI" / "custom_nodes"
    bootstrap = tmp_path / "scripts" / "run_blokeyui_engine.py"
    config = tmp_path / "ComfyUI" / "sineforge_engine_paths.yaml"
    custom_nodes.mkdir(parents=True)
    for path in (python, main, bootstrap, config):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return Settings(
        _env_file=None,
        storage_root=tmp_path / "storage",
        comfyui_autostart=True,
        comfyui_backend_managed=True,
        comfyui_base_url="http://127.0.0.1:8190",
        comfyui_working_dir=root,
        comfyui_python_executable=python,
        comfyui_main_path=main,
        comfyui_bootstrap_path=bootstrap,
        comfyui_custom_nodes_dir=custom_nodes,
        comfyui_sineforge_paths_config=config,
        comfyui_input_dir=tmp_path / "storage" / "inputs",
        comfyui_output_dir=tmp_path / "storage" / "outputs",
        comfyui_temp_dir=tmp_path / "storage" / "runtime" / "comfyui" / "temp",
        comfyui_user_dir=tmp_path / "storage" / "runtime" / "comfyui" / "user",
        comfyui_startup_timeout_sec=10,
    )


def test_bundled_engine_command_uses_sineforge_owned_data_directories(tmp_path):
    settings = engine_settings(tmp_path)
    manager = ComfyEngineManager(settings)

    manager.validate()
    command = manager.command

    assert command[0] == str(settings.comfyui_python_executable)
    assert command[1:4] == (
        "-s",
        str(settings.comfyui_bootstrap_path),
        str(settings.comfyui_main_path),
    )
    assert command[command.index("--listen") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "8190"
    assert command[command.index("--base-directory") + 1] == str(
        manager.engine_base_directory
    )
    assert command[command.index("--input-directory") + 1] == str(
        settings.comfyui_input_dir
    )
    assert command[command.index("--output-directory") + 1] == str(
        settings.comfyui_output_dir
    )


def test_bundled_engine_validation_rejects_missing_runtime(tmp_path):
    settings = engine_settings(tmp_path)
    settings.comfyui_python_executable.unlink()

    with pytest.raises(FileNotFoundError, match="compatibility Python"):
        ComfyEngineManager(settings).validate()


def test_external_custom_nodes_are_mounted_from_a_pinned_allowlist(tmp_path):
    settings = engine_settings(tmp_path)
    external = tmp_path / "curated-nodes"
    for name in (
        "ComfyUI-LTXVideo",
        "comfyui-videohelpersuite",
        "comfyui_starnodes",
        "ComfyUI-Manager",
        "new-unreviewed-pack",
    ):
        (external / name).mkdir(parents=True)
    settings.comfyui_custom_nodes_dir = external
    manager = ComfyEngineManager(settings)

    manager.validate()
    manager._write_runtime_paths_config()
    command = manager.command

    assert manager.runtime_paths_config.is_file()
    assert "ComfyUI-LTXVideo" in command
    assert "comfyui-videohelpersuite" in command
    assert "comfyui_starnodes" in command
    assert "sineforge_workflow_bridge" in command
    assert "ComfyUI-Manager" not in command
    assert "new-unreviewed-pack" not in command


@pytest.mark.asyncio
async def test_stop_refuses_busy_queue_without_explicit_force(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    manager.process = SimpleNamespace(poll=lambda: None)

    async def busy_queue():
        return {"running": 1, "pending": 2}

    monkeypatch.setattr(manager, "_queue_summary", busy_queue)

    with pytest.raises(ComfyEngineError, match="1 running, 2 pending"):
        await manager.stop()

    assert manager.process is not None
    manager.process = None


@pytest.mark.asyncio
async def test_queue_summary_fails_closed_for_malformed_payload(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"queue_running": None, "queue_pending": []}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _path):
            return FakeResponse()

    monkeypatch.setattr(
        "backend.app.services.comfy.engine.httpx.AsyncClient", FakeAsyncClient
    )

    with pytest.raises(ComfyEngineError, match="will not assume the engine is idle"):
        await manager._queue_summary()


@pytest.mark.asyncio
async def test_stop_waits_for_in_flight_native_submission(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    manager._phase = "running"
    manager.process = SimpleNamespace(poll=lambda: None)
    stopped = asyncio.Event()

    async def stop_locked(*, force, preserve_phase=False):
        del force, preserve_phase
        stopped.set()
        manager.process = None

    monkeypatch.setattr(manager, "_stop_locked", stop_locked)

    async with manager.submission_guard():
        stopping = asyncio.create_task(manager.stop(force=True))
        await asyncio.sleep(0)
        assert stopping.done() is False
        assert stopped.is_set() is False

    await stopping
    assert stopped.is_set() is True


@pytest.mark.asyncio
async def test_sync_and_async_prompt_producers_share_the_drain_gate(tmp_path):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    manager._phase = "running"
    manager.process = SimpleNamespace(poll=lambda: None)
    sync_entered = threading.Event()

    def sync_submit():
        with comfy_prompt_submission_guard():
            sync_entered.set()

    async with manager.submission_guard():
        submitting = asyncio.create_task(asyncio.to_thread(sync_submit))
        await asyncio.sleep(0.05)
        assert sync_entered.is_set() is False

    await submitting
    assert sync_entered.is_set() is True


@pytest.mark.asyncio
async def test_cancelled_async_gate_waiter_never_strands_process_gate():
    holder_entered = threading.Event()
    release_holder = threading.Event()

    def hold_sync_gate():
        with comfy_prompt_submission_guard():
            holder_entered.set()
            release_holder.wait(timeout=5)

    holder = asyncio.create_task(asyncio.to_thread(hold_sync_gate))
    await asyncio.to_thread(holder_entered.wait, 5)

    async def wait_for_gate():
        async with async_comfy_prompt_submission_guard():
            return None

    waiter = asyncio.create_task(wait_for_gate())
    await asyncio.sleep(0.02)
    waiter.cancel()
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release_holder.set()
    await holder
    async with async_comfy_prompt_submission_guard():
        pass


@pytest.mark.asyncio
async def test_status_never_claims_ownership_of_a_foreign_responder(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))

    async def ready_probe():
        return {
            "reachable": True,
            "checks": {
                "system_stats": True,
                "sineforge_bridge": True,
                "required_nodes": True,
            },
            "missing_required_nodes": [],
            "error": None,
        }

    monkeypatch.setattr(manager, "probe", ready_probe)

    payload = await manager.status()

    assert payload["status"] == "conflict"
    assert payload["ready"] is False
    assert payload["pid"] is None


@pytest.mark.asyncio
async def test_restart_holds_lifecycle_lock_across_stop_and_start(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    entered_start = asyncio.Event()
    release_start = asyncio.Event()
    events: list[str] = []

    async def idle(*, force):
        del force

    async def stop_locked(*, force, preserve_phase=False):
        del force
        events.append("restart-stop" if preserve_phase else "manual-stop")

    async def start_locked():
        events.append("restart-start")
        entered_start.set()
        await release_start.wait()

    monkeypatch.setattr(manager, "_ensure_idle", idle)
    monkeypatch.setattr(manager, "_stop_locked", stop_locked)
    monkeypatch.setattr(manager, "_start_locked", start_locked)

    restarting = asyncio.create_task(manager.restart())
    await entered_start.wait()
    stopping = asyncio.create_task(manager.stop(force=True))
    await asyncio.sleep(0)

    assert stopping.done() is False
    assert events == ["restart-stop", "restart-start"]

    release_start.set()
    await restarting
    await stopping
    assert events == ["restart-stop", "restart-start", "manual-stop"]


@pytest.mark.asyncio
async def test_engine_manager_owns_start_and_stop(tmp_path, monkeypatch):
    settings = engine_settings(tmp_path)
    manager = ComfyEngineManager(settings)
    probes = iter((False, True))
    popen_calls = []

    class FakeProcess:
        pid = 48190
        _handle = 1

        def __init__(self):
            self.exit_code = None
            self.signals = []
            self.exited = threading.Event()

        def poll(self):
            return self.exit_code

        def send_signal(self, value):
            self.signals.append(value)
            self.exit_code = 0
            self.exited.set()

        def terminate(self):
            self.exit_code = 0
            self.exited.set()

        def kill(self):
            self.exit_code = -9
            self.exited.set()

        def wait(self, timeout=None):
            if not self.exited.wait(timeout):
                raise TimeoutError
            return self.exit_code

    process = FakeProcess()

    async def fake_probe(*, timeout=2.0):
        del timeout
        reachable = next(probes)
        return {
            "reachable": reachable,
            "checks": {"system_stats": reachable, "object_info": reachable},
            "error": None,
        }

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return process

    class FakeJob:
        def assign(self, _handle):
            return None

        def close(self):
            return None

    monkeypatch.setattr(manager, "_probe", fake_probe)
    monkeypatch.setattr("backend.app.services.comfy.engine.subprocess.Popen", fake_popen)
    monkeypatch.setattr("backend.app.services.comfy.engine.WindowsJob", FakeJob)

    await manager.start()

    assert manager.process is process
    assert popen_calls[0][0] == list(manager.command)
    assert popen_calls[0][1]["cwd"] == settings.comfyui_main_path.parent

    await manager.stop(force=True)

    assert manager.process is None
    assert process.exit_code == 0


@pytest.mark.asyncio
async def test_unexpected_engine_exit_recovers_automatically(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    starts = 0

    class ExitedProcess:
        pid = 48191

        def poll(self):
            return 17

        def wait(self, timeout=None):
            del timeout
            return 17

    async def fake_start_locked():
        nonlocal starts
        starts += 1
        manager._phase = "running"

    process = ExitedProcess()
    manager.process = process
    manager._phase = "running"
    manager._desired_running = True
    monkeypatch.setattr(manager, "_start_locked", fake_start_locked)
    monkeypatch.setattr(
        "backend.app.services.comfy.engine.RECOVERY_INITIAL_DELAY_SECONDS",
        0,
    )

    await manager._monitor_process(process)
    assert manager._recovery_task is not None
    await manager._recovery_task

    assert starts == 1
    assert manager._phase == "running"
    assert manager._recovery_attempt == 0


@pytest.mark.asyncio
async def test_intentional_engine_stop_state_never_schedules_recovery(tmp_path):
    manager = ComfyEngineManager(engine_settings(tmp_path))

    class ExitedProcess:
        pid = 48192

        def poll(self):
            return 0

        def wait(self, timeout=None):
            del timeout
            return 0

    process = ExitedProcess()
    manager.process = process
    manager._phase = "stopping"
    manager._desired_running = False

    await manager._monitor_process(process)

    assert manager._recovery_task is None
    assert manager.process is None


@pytest.mark.asyncio
async def test_shutdown_during_engine_recovery_prevents_resurrection(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    starts = 0

    async def fake_start_locked():
        nonlocal starts
        starts += 1

    monkeypatch.setattr(manager, "_start_locked", fake_start_locked)
    monkeypatch.setattr(
        "backend.app.services.comfy.engine.RECOVERY_INITIAL_DELAY_SECONDS",
        60,
    )
    manager._desired_running = True
    manager._schedule_recovery()
    await asyncio.sleep(0)

    await manager.shutdown()

    assert starts == 0
    assert manager._desired_running is False
    assert manager._closing is True
    assert manager._recovery_task is not None
    assert manager._recovery_task.done()


@pytest.mark.asyncio
async def test_scheduled_restart_reports_completion(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))

    async def fake_restart(*, force=False):
        del force
        return None

    monkeypatch.setattr(manager, "restart", fake_restart)

    scheduled = await manager.schedule_restart()
    restart_id = scheduled["restart_id"]
    task = manager._restart_tasks[restart_id]
    await task

    status = manager.restart_status(restart_id)
    assert status is not None
    assert status["status"] == "complete"
    assert status["complete"] is True
    assert status["failed"] is False


@pytest.mark.asyncio
async def test_concurrent_restart_scheduling_reserves_one_operation(tmp_path, monkeypatch):
    manager = ComfyEngineManager(engine_settings(tmp_path))
    first_idle_check = asyncio.Event()
    release_idle_check = asyncio.Event()
    release_restart = asyncio.Event()
    idle_checks = 0

    async def fake_idle(*, force=False):
        nonlocal idle_checks
        del force
        idle_checks += 1
        first_idle_check.set()
        await release_idle_check.wait()

    async def fake_restart(*, force=False):
        del force
        await release_restart.wait()

    monkeypatch.setattr(manager, "_ensure_idle", fake_idle)
    monkeypatch.setattr(manager, "restart", fake_restart)

    first = asyncio.create_task(manager.schedule_restart())
    await first_idle_check.wait()
    second = asyncio.create_task(manager.schedule_restart())
    await asyncio.sleep(0)
    assert idle_checks == 1

    release_idle_check.set()
    scheduled = await first
    with pytest.raises(ComfyEngineError, match="already in progress"):
        await second

    release_restart.set()
    await manager._restart_tasks[scheduled["restart_id"]]
