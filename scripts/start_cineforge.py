"""Supervise the local CineForge development stack.

This is the trusted bootstrap boundary for local executables. It never accepts
commands from prompts or API requests; paths come only from administrator-owned
environment variables, the local `.env` file, or conservative local defaults.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable

try:
    # Package import used by tests and other Sineforge modules.
    from scripts.headless_orchestrator.windows_job import WindowsJob
except ModuleNotFoundError:
    # Direct `python scripts/start_cineforge.py` execution used by the .cmd launcher.
    from headless_orchestrator.windows_job import WindowsJob


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "storage" / "runtime" / "supervisor"
LOG_ROOT = RUNTIME_ROOT / "logs"
STATE_PATH = RUNTIME_ROOT / "cineforge-services.json"
LOCK_PATH = RUNTIME_ROOT / "cineforge-supervisor.lock"
MAX_LOG_BYTES = 10 * 1024 * 1024
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0
FORBIDDEN_COMMAND_PATH_CHARS = set("\r\n&|<>^`\"%'!()")
MONITOR_INTERVAL_SECONDS = 5.0
LIVENESS_FAILURE_THRESHOLD = 3
RESTART_INITIAL_DELAY_SECONDS = 1.0
RESTART_MAX_DELAY_SECONDS = 30.0
_SUPERVISOR_STARTED_AT_EPOCH: float | None = None


def apply_primary_workstation_defaults() -> None:
    """Enable the approved local runtimes when no local override was supplied."""

    defaults = {
        "CINEFORGE_COMFYUI_AUTOSTART": "true",
        "CINEFORGE_COMFYUI_BACKEND_MANAGED": "true",
        "CINEFORGE_COMFYUI_BASE_URL": "http://127.0.0.1:8190",
        "CINEFORGE_COMFYUI_WORKING_DIR": str(REPO_ROOT / "BlokeyUI"),
        "CINEFORGE_COMFYUI_PYTHON_EXECUTABLE": str(
            Path(r"C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe")
        ),
        "CINEFORGE_COMFYUI_MAIN_PATH": str(
            REPO_ROOT / "BlokeyUI" / "ComfyUI" / "main.py"
        ),
        "CINEFORGE_COMFYUI_BOOTSTRAP_PATH": str(
            REPO_ROOT / "scripts" / "run_blokeyui_engine.py"
        ),
        "CINEFORGE_COMFYUI_CUSTOM_NODES_DIR": str(
            Path(r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes")
        ),
        "CINEFORGE_COMFYUI_SINEFORGE_PATHS_CONFIG": str(
            REPO_ROOT / "ComfyUI" / "sineforge_engine_paths.yaml"
        ),
        "CINEFORGE_LMS_EXECUTABLE": (
            str(Path.home() / ".lmstudio" / "bin" / "lms.exe")
        ),
        "CINEFORGE_SULPHUR_PLANNING_ENABLED": "true",
        "CINEFORGE_SULPHUR_PHASE_ONE_ENABLED": "true",
        "CINEFORGE_SULPHUR_BASE_URL": "http://127.0.0.1:1234/v1",
        "CINEFORGE_SULPHUR_MODEL_ID": "sulphur-2-base",
        "CINEFORGE_SULPHUR_MODEL_KEY": "sulphur-2-base",
        "CINEFORGE_SULPHUR_MODEL_PATH": str(
            Path.home()
            / ".lmstudio"
            / "models"
            / "SulphurAI"
            / "Sulphur-2-base"
            / "sulphur_prompt_enhancer_model-q8_0.gguf"
        ),
        "CINEFORGE_QWEN_MODEL_ID": (
            "qwen3.6-40b-claude-4.6-opus-deckard-heretic-uncensored-thinking-"
            "neo-code-di-imatrix-max"
        ),
        "CINEFORGE_QWEN_MODEL_PATH": str(
            Path.home()
            / ".lmstudio"
            / "models"
            / "DavidAU"
            / "Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF"
            / "Qwen3.6-40B-Deck-Opus-NEO-CODE-HERE-2T-OT-Q4_K_S.gguf"
        ),
        # The 40B planner and LTX cannot coexist on the 24GB workstation GPU.
        # Keep the selected model persisted, but let the planning request load it
        # on demand and unload it before ComfyUI rendering starts.
        "CINEFORGE_PLANNING_MODEL_PRELOAD": "false",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def load_local_env(path: Path = REPO_ROOT / ".env") -> None:
    """Load simple local CINEFORGE_* defaults without shell expansion."""

    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("CINEFORGE_") or key in os.environ:
            continue
        cleaned = value.strip().strip('"').strip("'")
        os.environ[key] = cleaned


@dataclass(frozen=True)
class Service:
    name: str
    cwd: Path
    executable: Path
    args: tuple[str, ...]
    readiness_urls: tuple[str, ...]
    timeout_seconds: float
    persistent: bool = True
    always_start: bool = False


@dataclass
class OwnedProcess:
    service: Service
    process: subprocess.Popen[bytes]
    stdout: IO[bytes]
    stderr: IO[bytes]
    job: WindowsJob | None = None
    status: str = "starting"
    restart_count: int = 0
    consecutive_failures: int = 0
    last_exit_code: int | None = None
    last_exit_at_epoch: float | None = None
    last_error: str | None = None
    next_restart_at_epoch: float | None = None
    ready_since_epoch: float | None = None
    process_started_at_epoch: float | None = None


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    raw = value if value else str(default)
    if any(character in raw for character in FORBIDDEN_COMMAND_PATH_CHARS):
        raise ValueError(f"{name} contains shell metacharacters")
    return Path(raw).expanduser().resolve()


def _port(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f"{name} must be a decimal TCP port")
    value = int(raw)
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _timeout(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not 1 <= value <= 600:
        raise ValueError(f"{name} must be between 1 and 600 seconds")
    return value


def _loopback_base_url(
    name: str,
    default: str,
    *,
    allowed_paths: frozenset[str] = frozenset({"", "/"}),
) -> str:
    value = os.environ.get(name, default).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError(f"{name} must be an http loopback URL")
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname.lower() == "localhost"
    if not loopback or parsed.username or parsed.password:
        raise ValueError(f"{name} must not target a non-loopback host or contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in allowed_paths:
        raise ValueError(f"{name} must be an origin URL without a path, query, or fragment")
    return value


def _npm_executable() -> Path:
    configured = os.environ.get("CINEFORGE_NPM_EXECUTABLE")
    found = configured or shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not found:
        raise FileNotFoundError("npm was not found; install Node.js or set CINEFORGE_NPM_EXECUTABLE")
    return Path(found).resolve()


def validate_bundled_engine_configuration() -> None:
    """Fail early when the unified BlokeyUI engine dependency set is missing."""

    root = _env_path("CINEFORGE_COMFYUI_WORKING_DIR", REPO_ROOT / "BlokeyUI")
    required_files = {
        "compatibility Python": _env_path(
            "CINEFORGE_COMFYUI_PYTHON_EXECUTABLE",
            Path(r"C:\ComfyUI\LTX\ComfyUI\python_embeded\python.exe"),
        ),
        "BlokeyUI main.py": _env_path(
            "CINEFORGE_COMFYUI_MAIN_PATH", root / "ComfyUI" / "main.py"
        ),
        "source bootstrap": _env_path(
            "CINEFORGE_COMFYUI_BOOTSTRAP_PATH",
            REPO_ROOT / "scripts" / "run_blokeyui_engine.py",
        ),
        "Sineforge path config": _env_path(
            "CINEFORGE_COMFYUI_SINEFORGE_PATHS_CONFIG",
            REPO_ROOT / "ComfyUI" / "sineforge_engine_paths.yaml",
        ),
    }
    if not root.is_dir():
        raise FileNotFoundError(f"BlokeyUI root does not exist: {root}")
    for label, path in required_files.items():
        if not path.is_file():
            raise FileNotFoundError(f"{label} does not exist: {path}")
    custom_nodes = _env_path(
        "CINEFORGE_COMFYUI_CUSTOM_NODES_DIR",
        Path(r"C:\ComfyUI\LTX\ComfyUI\ComfyUI\custom_nodes"),
    )
    if not custom_nodes.is_dir():
        raise FileNotFoundError(f"curated custom-node root does not exist: {custom_nodes}")


def unified_engine_owner_ready(backend_origin: str) -> tuple[bool, str]:
    """Verify that an existing backend owns the identity-checked engine."""

    url = backend_origin.rstrip("/") + "/runtime/engine"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read(1_048_576))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return False, str(exc)
    if not isinstance(payload, dict):
        return False, "engine status was not a JSON object"
    expected = (
        payload.get("schema") == "sineforge.comfy-engine/v1"
        and payload.get("distribution") == "BlokeyUI"
        and payload.get("managed") is True
        and payload.get("ready") is True
        and isinstance(payload.get("pid"), int)
    )
    return bool(expected), str(payload.get("last_error") or payload.get("status") or "unknown")


def build_services() -> list[Service]:
    python = _env_path(
        "CINEFORGE_PYTHON_EXECUTABLE",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    )
    npm = _npm_executable()
    command_processor = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
    sulphur_base_url = _loopback_base_url(
        "CINEFORGE_SULPHUR_BASE_URL",
        "http://127.0.0.1:1234/v1",
        allowed_paths=frozenset({"", "/", "/v1"}),
    )
    sulphur_parts = urllib.parse.urlsplit(sulphur_base_url)
    sulphur_origin = urllib.parse.urlunsplit(
        (sulphur_parts.scheme, sulphur_parts.netloc, "", "", "")
    )
    backend_port = _port("CINEFORGE_BACKEND_PORT", 8010)
    frontend_port = _port("CINEFORGE_FRONTEND_PORT", 5174)
    engine_required = _env_bool("CINEFORGE_COMFYUI_AUTOSTART", True) and _env_bool(
        "CINEFORGE_COMFYUI_BACKEND_MANAGED", True
    )
    backend_origin = f"http://127.0.0.1:{backend_port}"
    backend_readiness = [backend_origin + "/health"]
    if engine_required:
        backend_readiness.append(backend_origin + "/health/engine/ready")

    services = [
        Service(
            name="sulphur",
            cwd=REPO_ROOT,
            executable=python,
            args=(str(REPO_ROOT / "scripts" / "bootstrap_sulphur.py"),),
            readiness_urls=(sulphur_origin + "/api/v1/models",),
            timeout_seconds=_timeout("CINEFORGE_SULPHUR_STARTUP_TIMEOUT_SEC", 600),
            persistent=False,
            always_start=True,
        ),
    ]
    services.extend(
        [
        Service(
            name="backend",
            cwd=REPO_ROOT,
            executable=python,
            args=(
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(backend_port),
            ),
            readiness_urls=tuple(backend_readiness),
            timeout_seconds=_timeout(
                "CINEFORGE_BACKEND_STARTUP_TIMEOUT_SEC",
                360 if engine_required else 60,
            ),
        ),
        Service(
            name="frontend",
            cwd=REPO_ROOT / "frontend",
            executable=command_processor if npm.suffix.lower() in {".bat", ".cmd"} else npm,
            args=(
                *((("/d", "/c", str(npm))) if npm.suffix.lower() in {".bat", ".cmd"} else ()),
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend_port),
                "--strictPort",
            ),
            readiness_urls=(
                f"http://127.0.0.1:{frontend_port}/",
            ),
            timeout_seconds=_timeout("CINEFORGE_FRONTEND_STARTUP_TIMEOUT_SEC", 60),
        ),
        ]
    )
    return services


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def probe(url: str, timeout: float = 3.0) -> bool:
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        request = urllib.request.Request(url, method="GET")
        with opener.open(request, timeout=timeout) as response:
            return 200 <= response.status < 400
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def is_ready(service: Service, probe_fn: Callable[[str], bool] = probe) -> bool:
    return all(probe_fn(url) for url in service.readiness_urls)


def validate_service(service: Service) -> None:
    if not service.cwd.is_dir():
        raise FileNotFoundError(f"{service.name}: working directory does not exist: {service.cwd}")
    if not service.executable.is_file():
        raise FileNotFoundError(f"{service.name}: executable does not exist: {service.executable}")
    if service.name in {"comfyui", "comfy_api_runner"} and service.args:
        launcher = Path(service.args[-1])
        if not launcher.is_file():
            raise FileNotFoundError(
                f"{service.name}: launcher does not exist: {launcher}"
            )
    if service.name == "sulphur":
        bootstrap = Path(service.args[0])
        if not bootstrap.is_file():
            raise FileNotFoundError(f"sulphur: bootstrap does not exist: {bootstrap}")


def _rotate_log(path: Path) -> None:
    if not path.exists() or path.stat().st_size < MAX_LOG_BYTES:
        return
    previous = path.with_suffix(path.suffix + ".1")
    previous.unlink(missing_ok=True)
    path.replace(previous)


def launch(service: Service) -> OwnedProcess:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_path = LOG_ROOT / f"{service.name}.out.log"
    stderr_path = LOG_ROOT / f"{service.name}.err.log"
    _rotate_log(stdout_path)
    _rotate_log(stderr_path)
    stdout = stdout_path.open("ab", buffering=0)
    stderr = stderr_path.open("ab", buffering=0)
    # A new process group lets the supervisor deliver a targeted Ctrl+Break for
    # graceful shutdown. A Job Object is the guaranteed tree-cleanup fallback.
    flags = CREATE_NEW_PROCESS_GROUP
    job = WindowsJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [str(service.executable), *service.args],
            cwd=service.cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
        )
        if os.name == "nt":
            job.assign(process._handle)  # type: ignore[attr-defined]
    except Exception:
        if process is not None and process.poll() is None:
            process.kill()
        job.close()
        stdout.close()
        stderr.close()
        raise
    return OwnedProcess(
        service=service,
        process=process,
        stdout=stdout,
        stderr=stderr,
        job=job,
        process_started_at_epoch=_process_started_at_epoch(process.pid),
    )


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return ctypes.windll.kernel32.GetLastError() == 5  # Access denied proves it exists.
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _process_started_at_epoch(pid: int) -> float | None:
    """Return the Windows process creation time used to detect PID reuse."""

    if pid <= 0 or os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return None
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        windows_ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return windows_ticks / 10_000_000 - 11_644_473_600
    finally:
        kernel32.CloseHandle(handle)


def _process_executable_name(pid: int) -> str | None:
    """Read a Windows process name even when opening the process is denied."""

    if pid <= 0 or os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("process_id", wintypes.DWORD),
            ("default_heap_id", ctypes.c_size_t),
            ("module_id", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent_process_id", wintypes.DWORD),
            ("priority_base", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("executable", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return None
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(ProcessEntry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return None
        while True:
            if entry.process_id == pid:
                return entry.executable
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(snapshot)


def _read_lock_owner() -> tuple[int, float | None]:
    """Read both legacy PID-only locks and PID-reuse-safe JSON locks."""

    try:
        payload = json.loads(LOCK_PATH.read_text(encoding="ascii"))
    except (OSError, ValueError, TypeError):
        return -1, None
    if isinstance(payload, int):
        return payload, None
    if not isinstance(payload, dict):
        return -1, None
    pid = payload.get("pid")
    started_at = payload.get("process_started_at_epoch")
    if not isinstance(pid, int):
        return -1, None
    if not isinstance(started_at, (int, float)):
        started_at = None
    return pid, float(started_at) if started_at is not None else None


def _legacy_lock_started_at(owner: int) -> float | None:
    """Use legacy supervisor state to validate an old PID-only lock."""

    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("supervisor_pid") != owner:
        return None
    started_at = payload.get("started_at_epoch")
    return float(started_at) if isinstance(started_at, (int, float)) else None


def _lock_owner_is_active(owner: int, expected_started_at: float | None) -> bool:
    if not _pid_exists(owner):
        return False
    actual_started_at = _process_started_at_epoch(owner)
    if expected_started_at is None:
        expected_started_at = _legacy_lock_started_at(owner)
    if actual_started_at is not None and expected_started_at is not None:
        return abs(actual_started_at - expected_started_at) <= 2.0
    executable_name = _process_executable_name(owner)
    if executable_name and not executable_name.casefold().startswith("python"):
        return False
    if actual_started_at is None or expected_started_at is None:
        # Stay conservative when the process still looks like Python but the
        # platform cannot prove whether its PID was reused.
        return True
    return False


def acquire_lock() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    for _attempt in range(2):
        try:
            descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            owner, expected_started_at = _read_lock_owner()
            if _lock_owner_is_active(owner, expected_started_at):
                raise RuntimeError(f"CineForge supervisor is already running with PID {owner}")
            LOCK_PATH.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            payload: dict[str, int | float] = {"pid": os.getpid()}
            started_at = _process_started_at_epoch(os.getpid())
            if started_at is not None:
                payload["process_started_at_epoch"] = started_at
            json.dump(payload, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        return
    raise RuntimeError("could not acquire the CineForge supervisor lock")


def release_lock() -> None:
    owner, _started_at = _read_lock_owner()
    if owner == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)


def wait_until_ready(
    owned: OwnedProcess,
    probe_fn: Callable[[str], bool] = probe,
) -> None:
    deadline = time.monotonic() + owned.service.timeout_seconds
    while time.monotonic() < deadline:
        exit_code = owned.process.poll()
        if exit_code is not None:
            if exit_code != 0 or owned.service.persistent:
                raise RuntimeError(
                    f"{owned.service.name} exited with code {owned.process.returncode}; "
                    f"see {LOG_ROOT}"
                )
            if is_ready(owned.service, probe_fn):
                owned.status = "completed"
                return
        if owned.service.persistent and is_ready(owned.service, probe_fn):
            # A foreign or orphaned listener must not make a dead generation
            # look ready after its own bind attempt failed.
            exit_code = owned.process.poll()
            if exit_code is not None:
                raise RuntimeError(
                    f"{owned.service.name} exited with code {owned.process.returncode}; "
                    f"see {LOG_ROOT}"
                )
            owned.status = "ready"
            owned.ready_since_epoch = time.time()
            owned.consecutive_failures = 0
            return
        time.sleep(1)
    raise TimeoutError(
        f"{owned.service.name} did not become ready within "
        f"{owned.service.timeout_seconds:g}s; see {LOG_ROOT}"
    )


def _supervisor_started_at_epoch() -> float:
    global _SUPERVISOR_STARTED_AT_EPOCH
    if _SUPERVISOR_STARTED_AT_EPOCH is None:
        _SUPERVISOR_STARTED_AT_EPOCH = (
            _process_started_at_epoch(os.getpid()) or time.time()
        )
    return _SUPERVISOR_STARTED_AT_EPOCH


def write_state(
    owned: list[OwnedProcess],
    reused: list[Service],
    *,
    shutdown_requested: bool = False,
) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    started_at_epoch = _supervisor_started_at_epoch()
    state = {
        "supervisor_pid": os.getpid(),
        # Keep the legacy field stable for PID-reuse-safe legacy lock recovery.
        "started_at_epoch": started_at_epoch,
        "supervisor_started_at_epoch": started_at_epoch,
        "updated_at_epoch": time.time(),
        "shutdown_requested": shutdown_requested,
        "services": [
            {
                "name": item.service.name,
                "pid": item.process.pid if item.process.poll() is None else None,
                "owned": True,
                "status": item.status,
                "persistent": item.service.persistent,
                "always_start": item.service.always_start,
                "process_started_at_epoch": item.process_started_at_epoch,
                "restart_count": item.restart_count,
                "consecutive_failures": item.consecutive_failures,
                "last_exit_code": item.last_exit_code,
                "last_exit_at_epoch": item.last_exit_at_epoch,
                "last_error": item.last_error,
                "next_restart_at_epoch": item.next_restart_at_epoch,
                "ready_since_epoch": item.ready_since_epoch,
                "readiness_urls": item.service.readiness_urls,
                "liveness_urls": item.service.readiness_urls[:1],
            }
            for item in owned
        ]
        + [
            {
                "name": service.name,
                "pid": None,
                "owned": False,
                "status": "reused",
                "persistent": service.persistent,
                "always_start": service.always_start,
                "readiness_urls": service.readiness_urls,
                "liveness_urls": service.readiness_urls[:1],
            }
            for service in reused
        ],
    }
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(STATE_PATH)


def stop_owned(owned: list[OwnedProcess]) -> None:
    for item in reversed(owned):
        item.status = "stopping"
        try:
            if item.process.poll() is None:
                try:
                    if os.name == "nt":
                        item.process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        item.process.terminate()
                    item.process.wait(timeout=30 if item.service.name == "backend" else 10)
                except (OSError, subprocess.TimeoutExpired):
                    job = getattr(item, "job", None)
                    if job is not None:
                        job.close()
                    if item.process.poll() is None:
                        item.process.kill()
                    try:
                        item.process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        print(
                            f"[warn] {item.service.name} did not confirm exit after forced cleanup",
                            file=sys.stderr,
                            flush=True,
                        )
            item.last_exit_code = item.process.poll()
            item.last_exit_at_epoch = time.time()
            item.status = "stopped"
        except Exception as exc:
            item.last_error = str(exc)
            item.status = "stop-failed"
            print(
                f"[warn] could not fully stop {item.service.name}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            job = getattr(item, "job", None)
            if job is not None:
                job.close()
            try:
                item.stdout.close()
            finally:
                item.stderr.close()


def _verify_backend_generation(item: OwnedProcess) -> None:
    if item.service.name != "backend" or len(item.service.readiness_urls) <= 1:
        return
    owner_ready, reason = unified_engine_owner_ready(
        item.service.readiness_urls[0].rsplit("/", 1)[0]
    )
    if item.process.poll() is not None:
        raise RuntimeError(
            f"backend exited with code {item.process.returncode}; see {LOG_ROOT}"
        )
    if not owner_ready:
        raise RuntimeError(f"Backend engine ownership check failed: {reason}")


def _service_liveness_ready(service: Service) -> bool:
    return bool(service.readiness_urls and probe(service.readiness_urls[0]))


def recover_owned_service(
    owned: list[OwnedProcess],
    index: int,
    reused: list[Service],
    *,
    reason: str,
) -> OwnedProcess:
    """Replace one failed or unhealthy owned service until it is ready again."""

    failed = owned[index]
    service = failed.service
    restart_count = failed.restart_count
    failed.last_exit_code = failed.process.poll()
    failed.last_exit_at_epoch = time.time()
    failed.last_error = reason
    failed.status = "stopping"
    write_state(owned, reused)
    stop_owned([failed])

    delay = RESTART_INITIAL_DELAY_SECONDS
    while True:
        restart_count += 1
        failed.status = "backoff"
        failed.next_restart_at_epoch = time.time() + delay
        failed.restart_count = restart_count
        write_state(owned, reused)
        print(
            f"[recover] {service.name}: {reason}; retry {restart_count} in {delay:g}s",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(delay)

        candidate: OwnedProcess | None = None
        try:
            if _service_liveness_ready(service):
                raise RuntimeError(
                    f"{service.name} still has a responder on its liveness URL after "
                    "the owned process tree stopped"
                )
            candidate = launch(service)
            candidate.restart_count = restart_count
            candidate.status = "starting"
            owned[index] = candidate
            write_state(owned, reused)
            wait_until_ready(candidate)
            _verify_backend_generation(candidate)
            if candidate.process.poll() is not None:
                raise RuntimeError(
                    f"{service.name} exited with code {candidate.process.returncode} "
                    "after readiness verification"
                )
        except Exception as exc:
            reason = str(exc)
            if candidate is not None:
                candidate.last_error = reason
                candidate.last_exit_code = candidate.process.poll()
                candidate.last_exit_at_epoch = time.time()
                stop_owned([candidate])
                failed = candidate
            else:
                failed.last_error = reason
            owned[index] = failed
            delay = min(delay * 2, RESTART_MAX_DELAY_SECONDS)
            continue

        candidate.status = "ready"
        candidate.ready_since_epoch = time.time()
        candidate.next_restart_at_epoch = None
        candidate.last_error = None
        candidate.consecutive_failures = 0
        write_state(owned, reused)
        print(
            f"[ready] {service.name}: recovered as pid {candidate.process.pid}",
            flush=True,
        )
        return candidate


def run(*, open_browser: bool = True) -> int:
    services = build_services()
    owned: list[OwnedProcess] = []
    reused: list[Service] = []
    locked = False
    try:
        validate_bundled_engine_configuration()
        acquire_lock()
        locked = True
        for service in services:
            validate_service(service)
            if service.name == "backend" and probe(service.readiness_urls[0]) and not is_ready(service):
                raise RuntimeError(
                    "A backend already owns the configured port but does not expose a ready, "
                    "Sineforge-owned BlokeyUI engine. Stop that backend before launching."
                )
            if not service.always_start and is_ready(service):
                if service.name == "backend" and len(service.readiness_urls) > 1:
                    owner_ready, reason = unified_engine_owner_ready(
                        service.readiness_urls[0].rsplit("/", 1)[0]
                    )
                    if not owner_ready:
                        raise RuntimeError(f"Existing backend does not own the bundled engine: {reason}")
                reused.append(service)
                print(f"[ready] {service.name}: reusing existing healthy service", flush=True)
                continue
            print(f"[start] {service.name}", flush=True)
            item = launch(service)
            owned.append(item)
            try:
                wait_until_ready(item)
                _verify_backend_generation(item)
            except Exception as exc:
                if not service.persistent:
                    raise
                item = recover_owned_service(
                    owned,
                    len(owned) - 1,
                    reused,
                    reason=str(exc),
                )
            print(f"[ready] {service.name}: pid {item.process.pid}", flush=True)
            write_state(owned, reused)

        write_state(owned, reused)
        frontend_url = services[-1].readiness_urls[0].rstrip("/") + "/projects"
        print(f"CineForge is ready: {frontend_url}")
        print(f"Logs: {LOG_ROOT}")
        print("Press Ctrl+C to stop only services started by this supervisor.")
        if open_browser:
            webbrowser.open(frontend_url, new=2)
        while True:
            for index, item in enumerate(list(owned)):
                if not item.service.persistent:
                    continue
                exit_code = item.process.poll()
                if exit_code is not None:
                    recover_owned_service(
                        owned,
                        index,
                        reused,
                        reason=f"owned process exited with code {exit_code}",
                    )
                    continue
                if _service_liveness_ready(item.service):
                    if item.consecutive_failures:
                        item.consecutive_failures = 0
                        item.last_error = None
                        item.status = "ready"
                        write_state(owned, reused)
                    continue
                item.consecutive_failures += 1
                item.status = "unhealthy"
                item.last_error = (
                    f"liveness probe failed {item.consecutive_failures} consecutive times"
                )
                write_state(owned, reused)
                if item.consecutive_failures >= LIVENESS_FAILURE_THRESHOLD:
                    recover_owned_service(
                        owned,
                        index,
                        reused,
                        reason=item.last_error,
                    )
            time.sleep(MONITOR_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping CineForge-owned services...")
        if locked:
            write_state(owned, reused, shutdown_requested=True)
        return 0
    except Exception as exc:
        if (
            isinstance(exc, RuntimeError)
            and "supervisor is already running" in str(exc)
            and all(is_ready(service) for service in services if service.persistent)
            and unified_engine_owner_ready(
                next(
                    service.readiness_urls[0].rsplit("/", 1)[0]
                    for service in services
                    if service.name == "backend"
                )
            )[0]
        ):
            frontend_url = services[-1].readiness_urls[0].rstrip("/") + "/projects"
            print(f"CineForge is already running: {frontend_url}")
            if open_browser:
                webbrowser.open(frontend_url, new=2)
            return 0
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        stop_owned(owned)
        if locked:
            STATE_PATH.unlink(missing_ok=True)
            release_lock()


def main() -> int:
    load_local_env()
    apply_primary_workstation_defaults()
    parser = argparse.ArgumentParser(description="Start and supervise the CineForge local stack")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate configuration and report readiness without starting anything",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="start the stack without opening the CineForge browser tab",
    )
    args = parser.parse_args()
    if args.check:
        failed = False
        try:
            validate_bundled_engine_configuration()
            print("blokeyui-engine: configured")
        except Exception as exc:
            failed = True
            print(f"blokeyui-engine: invalid: {exc}", file=sys.stderr)
        for service in build_services():
            try:
                validate_service(service)
                ready = is_ready(service)
                print(f"{service.name}: {'ready' if ready else 'offline'}")
            except Exception as exc:
                failed = True
                print(f"{service.name}: invalid: {exc}", file=sys.stderr)
        return 1 if failed else 0
    return run(open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
