"""Lifecycle owner for the repository-bundled BlokeyUI ComfyUI engine."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, BinaryIO
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from backend.app.core.config import Settings
from scripts.headless_orchestrator.windows_job import WindowsJob


logger = logging.getLogger(__name__)

_PROCESS_COMFY_SUBMISSION_GATE = threading.Lock()


@contextmanager
def comfy_prompt_submission_guard():
    """Exclude synchronous prompt acceptance while the engine is draining."""

    _PROCESS_COMFY_SUBMISSION_GATE.acquire()
    try:
        yield
    finally:
        _PROCESS_COMFY_SUBMISSION_GATE.release()


@asynccontextmanager
async def async_comfy_prompt_submission_guard() -> AsyncIterator[None]:
    """Async view of the process-wide prompt/drain exclusion gate."""

    acquired = False
    try:
        while not acquired:
            acquired = _PROCESS_COMFY_SUBMISSION_GATE.acquire(blocking=False)
            if not acquired:
                await asyncio.sleep(0.01)
        yield
    finally:
        if acquired:
            _PROCESS_COMFY_SUBMISSION_GATE.release()

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0
MAX_LOG_BYTES = 10 * 1024 * 1024
RECOVERY_INITIAL_DELAY_SECONDS = 1.0
RECOVERY_MAX_DELAY_SECONDS = 30.0
_CUSTOM_NODE_EXCLUSIONS = {
    ".git",
    "__pycache__",
    "comfyui-manager",
    "sineforge-workflow-bridge",
}
_PINNED_CUSTOM_NODE_NAMES = (
    "10S_Nodes",
    "cg-use-everywhere",
    "comfy-mtb",
    "ComfyMath",
    "comfyui_controlnet_aux",
    "ComfyUI_Custom_Switch",
    "comfyui_essentials",
    "comfyui_essentials_mb",
    "comfyui_fill-nodes",
    "comfyui_ipadapter_plus",
    "comfyui_layerstyle",
    "comfyui_memory_cleanup",
    "comfyui_nvidia_rtx_nodes",
    "comfyui_tinyterranodes",
    "comfyui-art-venture",
    "ComfyUI-Conditioning-Rebalance",
    "ComfyUI-CrossViewWarp",
    "comfyui-custom-scripts",
    "ComfyUI-DepthAnythingV2",
    "comfyui-easy-use",
    "ComfyUI-Flux2-INT8",
    "comfyui-frame-interpolation",
    "ComfyUI-GGUF",
    "comfyui-image-saver",
    "comfyui-impact-pack",
    "comfyui-int-and-float",
    "comfyui-kjnodes",
    "ComfyUI-Krea2T-Enhancer",
    "ComfyUI-ltx-int8-loader",
    "ComfyUI-LTXVideo",
    "ComfyUI-MediaMixer",
    "comfyui-mmaudio",
    "comfyui-mxtoolkit",
    "ComfyUI-Pixaroma",
    "comfyui-promptchain",
    "ComfyUI-PromptRelay",
    "Comfyui-Resolution-Master",
    "ComfyUI-S3-IO",
    "comfyui-show-text",
    "comfyui_starnodes",
    "comfyui-various",
    "ComfyUI-VFI",
    "ComfyUI-Video-Depth-Anything",
    "comfyui-videohelpersuite",
    "comfyui-vrgamedevgirl",
    "ComfyUI-WanMoeKSampler",
    "controlaltai-nodes",
    "deno-custom-nodes",
    "koolook",
    "LTX2-Master-Loader",
    "masquerade-nodes-comfyui",
    "mikey_nodes",
    "pulid_comfyui",
    "RES4LYF",
    "reservedvram",
    "rgthree-comfy",
    "was-ns",
    "WhatDreamsCost-ComfyUI",
)


class ComfyEngineError(RuntimeError):
    """Raised when the bundled engine cannot complete a lifecycle action."""


class EngineInstanceLock:
    """Hold an OS-backed, cross-process lock for the single GPU engine."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: BinaryIO | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise ComfyEngineError(
                "Another Sineforge backend already owns the bundled ComfyUI engine."
            ) from exc
        self.handle = handle

    def close(self) -> None:
        handle = self.handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            logger.warning("Could not explicitly release the ComfyUI owner lock")
        finally:
            handle.close()
            self.handle = None


class ComfyEngineManager:
    """Own one loopback-only ComfyUI subprocess for the FastAPI application."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.process: subprocess.Popen[bytes] | None = None
        self._stdout: BinaryIO | None = None
        self._stderr: BinaryIO | None = None
        self._job: WindowsJob | None = None
        self._instance_lock: EngineInstanceLock | None = None
        self._lock = asyncio.Lock()
        self._restart_operation_lock = asyncio.Lock()
        self._phase = "stopped"
        self._started_at_epoch: float | None = None
        self._stopped_at_epoch: float | None = None
        self._last_exit_code: int | None = None
        self._last_error: str | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._recovery_task: asyncio.Task[None] | None = None
        self._desired_running = False
        self._closing = False
        self._recovery_attempt = 0
        self._next_recovery_at_epoch: float | None = None
        self._restart_tasks: dict[str, asyncio.Task[None]] = {}
        self._restart_records: dict[str, dict[str, Any]] = {}

    @property
    def managed(self) -> bool:
        return bool(self.settings.comfyui_backend_managed)

    @property
    def runtime_root(self) -> Path:
        return self.settings.storage_root / "runtime" / "comfyui"

    @property
    def log_root(self) -> Path:
        return self.runtime_root / "logs"

    @property
    def runtime_paths_config(self) -> Path:
        return self.runtime_root / "custom_node_paths.json"

    @property
    def engine_base_directory(self) -> Path:
        """Writable ComfyUI base state kept outside the BlokeyUI source tree."""

        return self.runtime_root / "base"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.runtime_root / 'comfyui.db').resolve().as_posix()}"

    def _uses_external_custom_nodes(self) -> bool:
        runtime_built_in = self.engine_base_directory / "custom_nodes"
        return self.settings.comfyui_custom_nodes_dir.resolve() != runtime_built_in.resolve()

    def _custom_node_names(self) -> tuple[str, ...]:
        names = {"sineforge_workflow_bridge"}
        root = self.settings.comfyui_custom_nodes_dir
        if root.is_dir():
            names.update(
                name
                for name in _PINNED_CUSTOM_NODE_NAMES
                if (root / name).is_dir()
                and name.casefold() not in _CUSTOM_NODE_EXCLUSIONS
            )
        return tuple(sorted(names, key=str.casefold))

    @property
    def command(self) -> tuple[str, ...]:
        parsed = urlsplit(str(self.settings.comfyui_base_url))
        host = parsed.hostname or "127.0.0.1"
        if host.casefold() == "localhost":
            host = "127.0.0.1"
        if parsed.port is None:
            raise ComfyEngineError("The ComfyUI engine URL must include an explicit port.")
        path_configs = [str(self.settings.comfyui_sineforge_paths_config)]
        if self._uses_external_custom_nodes():
            path_configs.append(str(self.runtime_paths_config))
        return (
            str(self.settings.comfyui_python_executable),
            "-s",
            str(self.settings.comfyui_bootstrap_path),
            str(self.settings.comfyui_main_path),
            "--listen",
            host,
            "--port",
            str(parsed.port),
            "--disable-auto-launch",
            "--disable-api-nodes",
            "--base-directory",
            str(self.engine_base_directory),
            "--input-directory",
            str(self.settings.comfyui_input_dir),
            "--output-directory",
            str(self.settings.comfyui_output_dir),
            "--temp-directory",
            str(self.settings.comfyui_temp_dir),
            "--user-directory",
            str(self.settings.comfyui_user_dir),
            "--database-url",
            self.database_url,
            "--extra-model-paths-config",
            *path_configs,
            "--disable-all-custom-nodes",
            "--whitelist-custom-nodes",
            *self._custom_node_names(),
        )

    def validate(self) -> None:
        root = self.settings.comfyui_working_dir.resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Bundled BlokeyUI directory is missing: {root}")
        required_files = {
            "compatibility Python": self.settings.comfyui_python_executable.resolve(),
            "engine bootstrap": self.settings.comfyui_bootstrap_path.resolve(),
            "ComfyUI main.py": self.settings.comfyui_main_path.resolve(),
            "Sineforge engine path config": self.settings.comfyui_sineforge_paths_config.resolve(),
        }
        for label, path in required_files.items():
            if not path.is_file():
                raise FileNotFoundError(f"Bundled {label} is missing: {path}")
        try:
            self.settings.comfyui_main_path.resolve().relative_to(root)
        except ValueError:
            raise ValueError(f"BlokeyUI main.py must remain inside {root}") from None
        for label, path in (
            ("engine bootstrap", self.settings.comfyui_bootstrap_path),
            ("Sineforge engine path config", self.settings.comfyui_sineforge_paths_config),
        ):
            try:
                path.resolve().relative_to(root.parent)
            except ValueError:
                raise ValueError(f"{label} must remain inside {root.parent}") from None
        storage_root = self.settings.storage_root.resolve()
        for label, path in (
            ("input", self.settings.comfyui_input_dir),
            ("output", self.settings.comfyui_output_dir),
            ("temporary", self.settings.comfyui_temp_dir),
            ("user", self.settings.comfyui_user_dir),
        ):
            try:
                path.resolve().relative_to(storage_root)
            except ValueError:
                raise ValueError(
                    f"The Sineforge-managed ComfyUI {label} directory must remain inside {storage_root}"
                ) from None
        if not self.settings.comfyui_custom_nodes_dir.is_dir():
            raise FileNotFoundError(
                "The configured ComfyUI custom-node directory is missing: "
                f"{self.settings.comfyui_custom_nodes_dir}"
            )

    def _write_runtime_paths_config(self) -> None:
        if not self._uses_external_custom_nodes():
            return
        node_root = self.settings.comfyui_custom_nodes_dir.resolve()
        payload = {
            "sineforge_engine_custom_nodes": {
                "base_path": node_root.parent.as_posix(),
                "custom_nodes": node_root.name,
            }
        }
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.runtime_paths_config.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def start_in_background(self, *, force: bool = False) -> None:
        if not self.managed:
            if force:
                raise ComfyEngineError(
                    "The backend is not the configured owner of the ComfyUI engine. "
                    "Start Sineforge with start-cineforge.cmd."
                )
            return
        if not force and not self.settings.comfyui_autostart:
            return
        self._desired_running = True
        self._closing = False
        if self._startup_task is not None and not self._startup_task.done():
            return
        if self._recovery_task is not None and not self._recovery_task.done():
            return
        self._startup_task = asyncio.create_task(
            self.start(),
            name="sineforge-comfyui-autostart",
        )
        self._startup_task.add_done_callback(self._consume_startup_result)

    def _consume_startup_result(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except (FileNotFoundError, ValueError):
            # A deterministic configuration error will not improve by looping.
            logger.exception("The bundled ComfyUI engine configuration is invalid")
        except Exception:
            logger.exception("The bundled ComfyUI engine failed to start; scheduling recovery")
            self._schedule_recovery()
        else:
            self._recovery_attempt = 0
            self._next_recovery_at_epoch = None

    @staticmethod
    def _consume_background_result(task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("The bundled ComfyUI engine lifecycle action failed")

    def _schedule_recovery(self) -> None:
        if (
            not self.managed
            or not self._desired_running
            or self._closing
            or (self._recovery_task is not None and not self._recovery_task.done())
        ):
            return
        self._recovery_task = asyncio.create_task(
            self._recover_until_running(),
            name="sineforge-comfyui-recovery",
        )
        self._recovery_task.add_done_callback(self._consume_background_result)

    async def _recover_until_running(self) -> None:
        delay = RECOVERY_INITIAL_DELAY_SECONDS
        try:
            while self._desired_running and not self._closing:
                self._recovery_attempt += 1
                self._phase = "recovering"
                self._next_recovery_at_epoch = time.time() + delay
                logger.warning(
                    "Recovering bundled ComfyUI after %.1fs (attempt %s)",
                    delay,
                    self._recovery_attempt,
                )
                await asyncio.sleep(delay)
                if not self._desired_running or self._closing:
                    return
                try:
                    async with self._lock:
                        if not self._desired_running or self._closing:
                            return
                        await self._start_locked()
                except (FileNotFoundError, ValueError):
                    logger.exception(
                        "Bundled ComfyUI recovery stopped because its configuration is invalid"
                    )
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Bundled ComfyUI recovery attempt %s failed",
                        self._recovery_attempt,
                    )
                    delay = min(delay * 2, RECOVERY_MAX_DELAY_SECONDS)
                    continue
                self._recovery_attempt = 0
                self._next_recovery_at_epoch = None
                return
        finally:
            self._next_recovery_at_epoch = None

    async def _probe(self, *, timeout: float = 2.0) -> dict[str, Any]:
        base_url = str(self.settings.comfyui_base_url).rstrip("/")
        checks = {"system_stats": False, "sineforge_bridge": False, "required_nodes": False}
        errors: list[str] = []
        missing_required: list[str] = list(self.settings.comfyui_required_nodes)

        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            system_call = client.get("/api/system_stats")
            bridge_call = client.get(
                "/sineforge/workflow-transfer/status",
                params=[("required", name) for name in self.settings.comfyui_required_nodes],
            )
            system_result, bridge_result = await asyncio.gather(
                system_call,
                bridge_call,
                return_exceptions=True,
            )

        if isinstance(system_result, httpx.Response):
            try:
                system_result.raise_for_status()
                checks["system_stats"] = True
            except httpx.HTTPError as exc:
                errors.append(f"system_stats: {exc}")
        else:
            errors.append(f"system_stats: {system_result}")

        if isinstance(bridge_result, httpx.Response):
            try:
                bridge_result.raise_for_status()
                payload = bridge_result.json()
                checks["sineforge_bridge"] = bool(
                    isinstance(payload, dict)
                    and payload.get("ok") is True
                    and payload.get("bridge") == "sineforge-workflow-bridge"
                    and payload.get("version") == 2
                )
                availability = payload.get("required_nodes", {}) if isinstance(payload, dict) else {}
                missing_required = [
                    name
                    for name in self.settings.comfyui_required_nodes
                    if not isinstance(availability, dict) or availability.get(name) is not True
                ]
                checks["required_nodes"] = not missing_required
                if not checks["sineforge_bridge"]:
                    errors.append("sineforge_bridge: identity response did not match")
                if missing_required:
                    errors.append("required_nodes: missing " + ", ".join(missing_required))
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"sineforge_bridge: {exc}")
        else:
            errors.append(f"sineforge_bridge: {bridge_result}")

        return {
            "reachable": all(checks.values()),
            "checks": checks,
            "missing_required_nodes": missing_required,
            "error": "; ".join(errors) or None,
        }

    async def probe(self) -> dict[str, Any]:
        """Return bounded, identity-aware readiness without mutating the engine."""

        try:
            return await self._probe()
        except Exception as exc:
            return {
                "reachable": False,
                "checks": {
                    "system_stats": False,
                    "sineforge_bridge": False,
                    "required_nodes": False,
                },
                "missing_required_nodes": list(self.settings.comfyui_required_nodes),
                "error": str(exc),
            }

    async def _queue_summary(self) -> dict[str, int]:
        base_url = str(self.settings.comfyui_base_url).rstrip("/")
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=3.0) as client:
                response = await client.get("/api/queue")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ComfyEngineError(
                "Sineforge could not confirm that the ComfyUI queue is idle. "
                "Retry, or use the explicit force control if interruption is intended."
            ) from exc
        if not isinstance(payload, dict):
            raise ComfyEngineError("ComfyUI returned an invalid queue status response.")
        running = payload.get("queue_running")
        pending = payload.get("queue_pending")
        if not isinstance(running, list) or not isinstance(pending, list):
            raise ComfyEngineError(
                "ComfyUI returned an invalid queue status response; Sineforge will not "
                "assume the engine is idle."
            )
        return {
            "running": len(running),
            "pending": len(pending),
        }

    async def _ensure_idle(self, *, force: bool) -> None:
        if force or self.process is None or self.process.poll() is not None:
            return
        summary = await self._queue_summary()
        if summary["running"] or summary["pending"]:
            raise ComfyEngineError(
                "ComfyUI is rendering or has queued work "
                f"({summary['running']} running, {summary['pending']} pending). "
                "Wait for it to finish or explicitly force the lifecycle action."
            )

    def _rotate_log(self, path: Path) -> None:
        if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
            return
        previous = path.with_suffix(path.suffix + ".1")
        previous.unlink(missing_ok=True)
        path.replace(previous)

    def _open_logs(self) -> tuple[BinaryIO, BinaryIO]:
        self.log_root.mkdir(parents=True, exist_ok=True)
        stdout_path = self.log_root / "engine.out.log"
        stderr_path = self.log_root / "engine.err.log"
        self._rotate_log(stdout_path)
        self._rotate_log(stderr_path)
        return (
            stdout_path.open("ab", buffering=0),
            stderr_path.open("ab", buffering=0),
        )

    def _close_logs(self) -> None:
        for handle_name in ("_stdout", "_stderr"):
            handle = getattr(self, handle_name)
            if handle is not None:
                handle.close()
                setattr(self, handle_name, None)

    def _release_process_ownership(self) -> None:
        if self._job is not None:
            self._job.close()
            self._job = None
        if self._instance_lock is not None:
            self._instance_lock.close()
            self._instance_lock = None
        self._close_logs()

    async def start(self) -> None:
        if not self.managed:
            raise ComfyEngineError(
                "The backend is not the configured owner of the ComfyUI engine. "
                "Start Sineforge with start-cineforge.cmd."
            )
        self._desired_running = True
        self._closing = False
        async with self._lock:
            await self._start_locked()

    @asynccontextmanager
    async def submission_guard(self) -> AsyncIterator[None]:
        """Serialize prompt acceptance against stop/restart drain operations."""

        async with async_comfy_prompt_submission_guard():
            if self.managed:
                process = self.process
                if (
                    self._phase != "running"
                    or process is None
                    or process.poll() is not None
                ):
                    raise ComfyEngineError(
                        "The bundled ComfyUI engine is not ready to accept a workflow."
                    )
            yield

    async def _start_locked(self) -> None:
        if self.process is not None and self.process.poll() is None:
            if (await self._probe()).get("reachable"):
                self._phase = "running"
                return
            raise ComfyEngineError("The bundled engine process is running but its API is not ready.")

        if self.process is not None:
            self._last_exit_code = self.process.poll()
            self.process = None
            self._release_process_ownership()

        self._phase = "starting"
        self._last_error = None
        self._last_exit_code = None
        try:
            self.validate()
            self._write_runtime_paths_config()
            self._instance_lock = EngineInstanceLock(self.runtime_root / "engine-owner.lock")
            self._instance_lock.acquire()
            if (await self._probe()).get("reachable"):
                raise ComfyEngineError(
                    f"Another ComfyUI process already owns {self.settings.comfyui_base_url}. "
                    "Stop it before starting the bundled Sineforge engine."
                )

            for directory in (
                self.engine_base_directory,
                self.engine_base_directory / "custom_nodes",
                self.settings.comfyui_input_dir,
                self.settings.comfyui_output_dir,
                self.settings.comfyui_temp_dir,
                self.settings.comfyui_user_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)

            self._stdout, self._stderr = self._open_logs()
            environment = os.environ.copy()
            job_handshake_path = self.runtime_root / "engine-job-assigned.ready"
            job_handshake_path.unlink(missing_ok=True)
            environment.update(
                CINEFORGE_MANAGED_COMFYUI="1",
                PYTHONNOUSERSITE="1",
                PYTHONUTF8="1",
                PYTHONIOENCODING="utf-8",
                PYTHONDONTWRITEBYTECODE="1",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                HF_HUB_DISABLE_TELEMETRY="1",
                DO_NOT_TRACK="1",
                PIP_NO_INDEX="1",
                PIP_DISABLE_PIP_VERSION_CHECK="1",
            )
            if os.name == "nt":
                environment["CINEFORGE_ENGINE_JOB_HANDSHAKE"] = str(job_handshake_path)
            self._job = WindowsJob()
            self.process = subprocess.Popen(
                list(self.command),
                cwd=self.settings.comfyui_main_path.parent,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=self._stdout,
                stderr=self._stderr,
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
            )
            if os.name == "nt":
                self._job.assign(self.process._handle)  # type: ignore[attr-defined]
                job_handshake_path.write_text(str(self.process.pid), encoding="ascii")

            deadline = time.monotonic() + self.settings.comfyui_startup_timeout_sec
            while time.monotonic() < deadline:
                exit_code = self.process.poll()
                if exit_code is not None:
                    self._last_exit_code = exit_code
                    raise ComfyEngineError(
                        f"Bundled ComfyUI exited with code {exit_code}; see {self.log_root}."
                    )
                if (await self._probe(timeout=3.0)).get("reachable"):
                    self._phase = "running"
                    self._started_at_epoch = time.time()
                    self._stopped_at_epoch = None
                    process = self.process
                    self._monitor_task = asyncio.create_task(
                        self._monitor_process(process),
                        name=f"sineforge-comfyui-monitor-{process.pid}",
                    )
                    return
                await asyncio.sleep(1)
            raise ComfyEngineError(
                "Bundled ComfyUI did not become ready within "
                f"{self.settings.comfyui_startup_timeout_sec:g} seconds; see {self.log_root}."
            )
        except asyncio.CancelledError:
            await self._stop_locked(force=True)
            raise
        except Exception as exc:
            self._last_error = str(exc)
            self._phase = "failed"
            await self._stop_locked(force=True, preserve_phase=True)
            raise

    async def _monitor_process(self, process: subprocess.Popen[bytes]) -> None:
        should_recover = False
        try:
            exit_code = await asyncio.to_thread(process.wait)
            async with self._lock:
                if self.process is not process:
                    return
                self._last_exit_code = exit_code
                self._last_error = f"Bundled ComfyUI exited unexpectedly with code {exit_code}."
                self._phase = "failed"
                self.process = None
                self._stopped_at_epoch = time.time()
                self._release_process_ownership()
                should_recover = self._desired_running and not self._closing
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed while monitoring the bundled ComfyUI process")
            async with self._lock:
                if self.process is process and process.poll() is not None:
                    self._last_exit_code = process.poll()
                    self._last_error = "Bundled ComfyUI monitoring failed after the process exited."
                    self._phase = "failed"
                    self.process = None
                    self._stopped_at_epoch = time.time()
                    self._release_process_ownership()
                    should_recover = self._desired_running and not self._closing
        if should_recover:
            self._schedule_recovery()

    async def _wait_for_exit(self, process: subprocess.Popen[bytes], timeout: float) -> None:
        await asyncio.to_thread(process.wait, timeout=timeout)

    async def _stop_locked(self, *, force: bool, preserve_phase: bool = False) -> None:
        process = self.process
        if process is None:
            if not preserve_phase:
                self._phase = "stopped"
            self._release_process_ownership()
            return
        await self._ensure_idle(force=force)
        if not preserve_phase:
            self._phase = "stopping"
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                await self._wait_for_exit(process, 15)
            except (OSError, subprocess.TimeoutExpired):
                # Closing the Job handle terminates the entire process tree.
                if self._job is not None:
                    self._job.close()
                    self._job = None
                if process.poll() is None:
                    process.kill()
                try:
                    await self._wait_for_exit(process, 5)
                except subprocess.TimeoutExpired:
                    logger.error("Bundled ComfyUI did not exit after its Job was terminated")
        self._last_exit_code = process.poll()
        self.process = None
        self._stopped_at_epoch = time.time()
        if not preserve_phase:
            self._phase = "stopped"
        self._release_process_ownership()

    async def _cancel_background_start(self) -> None:
        task = self._startup_task
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _cancel_recovery(self) -> None:
        task = self._recovery_task
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _cancel_monitor(self) -> None:
        task = self._monitor_task
        if task is None or task.done() or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Bundled engine startup failed while it was being stopped")

    async def stop(self, *, force: bool = False) -> None:
        if not self.managed:
            raise ComfyEngineError("This FastAPI process does not own the ComfyUI engine.")
        self._desired_running = False
        await self._cancel_background_start()
        await self._cancel_recovery()
        async with self._lock:
            async with async_comfy_prompt_submission_guard():
                await self._stop_locked(force=force)

    async def restart(self, *, force: bool = False) -> None:
        if not self.managed:
            raise ComfyEngineError("This FastAPI process does not own the ComfyUI engine.")
        self._desired_running = True
        self._closing = False
        await self._cancel_recovery()
        async with self._lock:
            async with async_comfy_prompt_submission_guard():
                await self._ensure_idle(force=force)
                self._phase = "restarting"
                await self._stop_locked(force=True, preserve_phase=True)
                await self._start_locked()

    async def schedule_restart(self, *, force: bool = False) -> dict[str, Any]:
        if not self.managed:
            raise ComfyEngineError(
                "The bundled engine is not managed by this process. "
                "Start Sineforge with start-cineforge.cmd."
            )
        async with self._restart_operation_lock:
            if any(not task.done() for task in self._restart_tasks.values()):
                raise ComfyEngineError("A bundled engine restart is already in progress.")
            await self._ensure_idle(force=force)
            restart_id = uuid4().hex
            record = {
                "restart_id": restart_id,
                "status": "scheduled",
                "message": "Sineforge scheduled a restart of its bundled ComfyUI engine.",
                "complete": False,
                "failed": False,
            }
            self._restart_records[restart_id] = record
            task = asyncio.create_task(
                self._run_scheduled_restart(restart_id, force=force),
                name=f"sineforge-comfyui-restart-{restart_id}",
            )
            self._restart_tasks[restart_id] = task
            task.add_done_callback(self._consume_background_result)
            return dict(record)

    async def _run_scheduled_restart(self, restart_id: str, *, force: bool) -> None:
        record = self._restart_records[restart_id]
        record.update(
            status="restarting",
            message="Sineforge is restarting the bundled ComfyUI engine.",
        )
        try:
            await self.restart(force=force)
        except Exception as exc:
            record.update(status="error", message=str(exc), complete=False, failed=True)
            raise
        else:
            record.update(
                status="complete",
                message="The bundled ComfyUI engine is ready.",
                complete=True,
                failed=False,
            )
        finally:
            self._restart_tasks.pop(restart_id, None)
            while len(self._restart_records) > 32:
                self._restart_records.pop(next(iter(self._restart_records)))

    def restart_status(self, restart_id: str) -> dict[str, Any] | None:
        record = self._restart_records.get(restart_id)
        return dict(record) if record is not None else None

    async def status(self) -> dict[str, Any]:
        process = self.process
        exit_code = process.poll() if process is not None else self._last_exit_code
        owned_alive = process is not None and exit_code is None
        readiness = await self.probe()

        if process is not None and exit_code is not None and self._phase == "running":
            self._phase = "failed"
            self._last_exit_code = exit_code
            self._last_error = f"Bundled ComfyUI exited unexpectedly with code {exit_code}."
            owned_alive = False

        reported_status = self._phase
        last_error = self._last_error or readiness.get("error")
        if self.managed:
            if owned_alive and readiness["reachable"] and reported_status not in {
                "starting",
                "restarting",
                "stopping",
            }:
                reported_status = "running"
            elif not owned_alive and readiness["reachable"]:
                reported_status = "conflict"
                last_error = (
                    "A compatible ComfyUI responder is reachable, but this Sineforge "
                    "backend does not own its process."
                )
        elif readiness["reachable"]:
            reported_status = "external"

        ready = bool(readiness["reachable"] and (owned_alive or not self.managed))
        return {
            "schema": "sineforge.comfy-engine/v1",
            "distribution": "BlokeyUI",
            "engine": "ComfyUI",
            "mode": "bundled" if self.managed else "external",
            "managed": self.managed,
            "autostart": bool(self.settings.comfyui_autostart),
            "status": reported_status,
            "ready": ready,
            "reachable": bool(readiness["reachable"]),
            "checks": readiness["checks"],
            "missing_required_nodes": readiness.get("missing_required_nodes", []),
            "pid": process.pid if owned_alive else None,
            "started_at_epoch": self._started_at_epoch,
            "stopped_at_epoch": self._stopped_at_epoch,
            "last_exit_code": self._last_exit_code,
            "last_error": last_error,
            "desired_running": self._desired_running,
            "recovering": bool(
                self._recovery_task is not None and not self._recovery_task.done()
            ),
            "recovery_attempt": self._recovery_attempt,
            "next_recovery_at_epoch": self._next_recovery_at_epoch,
            "api_base_url": str(self.settings.comfyui_base_url).rstrip("/"),
            "input_root": str(self.settings.comfyui_input_dir),
            "output_root": str(self.settings.comfyui_output_dir),
            "log_root": str(self.log_root),
            "source_root": str(self.settings.comfyui_main_path.parent),
            "python_runtime": str(self.settings.comfyui_python_executable),
            "custom_nodes_root": str(self.settings.comfyui_custom_nodes_dir),
            "launch_preset": "blokeyui-source-ltx-compatibility-runtime",
        }

    async def shutdown(self) -> None:
        self._closing = True
        self._desired_running = False
        await self._cancel_background_start()
        await self._cancel_recovery()
        await self._cancel_monitor()
        tasks = list(self._restart_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.managed:
            async with self._lock:
                async with async_comfy_prompt_submission_guard():
                    await self._stop_locked(force=True)


def engine_status_json(status: dict[str, Any]) -> str:
    """Stable compact representation useful in diagnostic logs and tests."""

    return json.dumps(status, separators=(",", ":"), sort_keys=True)
