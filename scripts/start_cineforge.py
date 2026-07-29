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


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "storage" / "runtime" / "supervisor"
LOG_ROOT = RUNTIME_ROOT / "logs"
STATE_PATH = RUNTIME_ROOT / "cineforge-services.json"
LOCK_PATH = RUNTIME_ROOT / "cineforge-supervisor.lock"
MAX_LOG_BYTES = 10 * 1024 * 1024
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0
FORBIDDEN_COMMAND_PATH_CHARS = set("\r\n&|<>^`\"%'!()")


def apply_primary_workstation_defaults() -> None:
    """Enable the approved local runtimes when no local override was supplied."""

    defaults = {
        "CINEFORGE_COMFYUI_BASE_URL": "http://127.0.0.1:8888",
        "CINEFORGE_COMFYUI_WORKING_DIR": r"C:\ComfyUI\BlokeyUI",
        "CINEFORGE_COMFYUI_LAUNCHER": r"C:\ComfyUI\BlokeyUI\run_blokeyui.bat",
        "CINEFORGE_COMFY_API_RUNNER_BASE_URL": "http://127.0.0.1:8022",
        "CINEFORGE_COMFY_API_RUNNER_WORKING_DIR": r"C:\ComfyUI\BlokeyUI",
        "CINEFORGE_COMFY_API_RUNNER_LAUNCHER": (
            r"C:\ComfyUI\BlokeyUI\run_comfy_api_runner.bat"
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


def build_services() -> list[Service]:
    comfy_root = _env_path(
        "CINEFORGE_COMFYUI_WORKING_DIR",
        Path(r"C:\ComfyUI\BlokeyUI"),
    )
    comfy_launcher = _env_path(
        "CINEFORGE_COMFYUI_LAUNCHER",
        comfy_root / "run_blokeyui.bat",
    )
    runner_root = _env_path(
        "CINEFORGE_COMFY_API_RUNNER_WORKING_DIR",
        Path(r"C:\ComfyUI\BlokeyUI"),
    )
    runner_launcher = _env_path(
        "CINEFORGE_COMFY_API_RUNNER_LAUNCHER",
        runner_root / "run_comfy_api_runner.bat",
    )
    python = _env_path(
        "CINEFORGE_PYTHON_EXECUTABLE",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    )
    npm = _npm_executable()
    command_processor = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
    comfy_base_url = _loopback_base_url(
        "CINEFORGE_COMFYUI_BASE_URL",
        "http://127.0.0.1:8888",
    )
    runner_base_url = _loopback_base_url(
        "CINEFORGE_COMFY_API_RUNNER_BASE_URL",
        "http://127.0.0.1:8022",
    )
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

    if comfy_launcher.suffix.lower() not in {".bat", ".cmd", ".exe"}:
        raise ValueError("ComfyUI launcher must be an administrator-configured .bat, .cmd, or .exe")
    try:
        comfy_launcher.relative_to(comfy_root)
    except ValueError as exc:
        raise ValueError("ComfyUI launcher must be located inside CINEFORGE_COMFYUI_WORKING_DIR") from exc

    if runner_launcher.suffix.lower() not in {".bat", ".cmd", ".exe"}:
        raise ValueError(
            "ComfyAPI Runner launcher must be an administrator-configured .bat, .cmd, or .exe"
        )
    try:
        runner_launcher.relative_to(runner_root)
    except ValueError as exc:
        raise ValueError(
            "ComfyAPI Runner launcher must be located inside "
            "CINEFORGE_COMFY_API_RUNNER_WORKING_DIR"
        ) from exc

    if comfy_launcher.suffix.lower() in {".bat", ".cmd"}:
        command = command_processor
        comfy_args = ("/d", "/c", str(comfy_launcher))
    else:
        command = comfy_launcher
        comfy_args = ()

    if runner_launcher.suffix.lower() in {".bat", ".cmd"}:
        runner_command = command_processor
        runner_args = ("/d", "/c", str(runner_launcher))
    else:
        runner_command = runner_launcher
        runner_args = ()

    return [
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
        Service(
            name="comfyui",
            cwd=comfy_root,
            executable=command,
            args=comfy_args,
            readiness_urls=(
                comfy_base_url + "/",
                comfy_base_url + "/object_info",
            ),
            timeout_seconds=_timeout("CINEFORGE_COMFYUI_STARTUP_TIMEOUT_SEC", 180),
        ),
        Service(
            name="comfy_api_runner",
            cwd=runner_root,
            executable=runner_command,
            args=runner_args,
            readiness_urls=(
                runner_base_url
                + "/api/health?url="
                + urllib.parse.quote(comfy_base_url, safe=""),
            ),
            timeout_seconds=_timeout(
                "CINEFORGE_COMFY_API_RUNNER_STARTUP_TIMEOUT_SEC",
                90,
            ),
        ),
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
            readiness_urls=(
                f"http://127.0.0.1:{backend_port}/health",
            ),
            timeout_seconds=_timeout("CINEFORGE_BACKEND_STARTUP_TIMEOUT_SEC", 60),
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
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    try:
        process = subprocess.Popen(
            [str(service.executable), *service.args],
            cwd=service.cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
        )
    except Exception:
        stdout.close()
        stderr.close()
        raise
    return OwnedProcess(service=service, process=process, stdout=stdout, stderr=stderr)


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


def acquire_lock() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    for _attempt in range(2):
        try:
            descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                owner = int(LOCK_PATH.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                owner = -1
            if _pid_exists(owner):
                raise RuntimeError(f"CineForge supervisor is already running with PID {owner}")
            LOCK_PATH.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
            handle.flush()
            os.fsync(handle.fileno())
        return
    raise RuntimeError("could not acquire the CineForge supervisor lock")


def release_lock() -> None:
    try:
        owner = int(LOCK_PATH.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return
    if owner == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)


def wait_until_ready(
    owned: OwnedProcess,
    probe_fn: Callable[[str], bool] = probe,
) -> None:
    deadline = time.monotonic() + owned.service.timeout_seconds
    while time.monotonic() < deadline:
        exit_code = owned.process.poll()
        if owned.service.persistent and is_ready(owned.service, probe_fn):
            return
        if exit_code is not None:
            if exit_code != 0 or owned.service.persistent:
                raise RuntimeError(
                    f"{owned.service.name} exited with code {owned.process.returncode}; "
                    f"see {LOG_ROOT}"
                )
            if is_ready(owned.service, probe_fn):
                return
        time.sleep(1)
    raise TimeoutError(
        f"{owned.service.name} did not become ready within "
        f"{owned.service.timeout_seconds:g}s; see {LOG_ROOT}"
    )


def write_state(owned: list[OwnedProcess], reused: list[Service]) -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    state = {
        "supervisor_pid": os.getpid(),
        "started_at_epoch": time.time(),
        "services": [
            {
                "name": item.service.name,
                "pid": item.process.pid,
                "owned": True,
                "persistent": item.service.persistent,
                "always_start": item.service.always_start,
                "readiness_urls": item.service.readiness_urls,
            }
            for item in owned
        ]
        + [
            {
                "name": service.name,
                "pid": None,
                "owned": False,
                "persistent": service.persistent,
                "always_start": service.always_start,
                "readiness_urls": service.readiness_urls,
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
        try:
            if item.process.poll() is None:
                try:
                    if os.name == "nt":
                        item.process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        item.process.terminate()
                    item.process.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    item.process.kill()
                    item.process.wait(timeout=5)
        finally:
            item.stdout.close()
            item.stderr.close()


def run(*, open_browser: bool = True) -> int:
    services = build_services()
    owned: list[OwnedProcess] = []
    reused: list[Service] = []
    locked = False
    try:
        acquire_lock()
        locked = True
        for service in services:
            validate_service(service)
            if not service.always_start and is_ready(service):
                reused.append(service)
                print(f"[ready] {service.name}: reusing existing healthy service", flush=True)
                continue
            print(f"[start] {service.name}", flush=True)
            item = launch(service)
            owned.append(item)
            wait_until_ready(item)
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
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping CineForge-owned services...")
        return 0
    except Exception as exc:
        if (
            isinstance(exc, RuntimeError)
            and "supervisor is already running" in str(exc)
            and is_ready(services[-1])
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
