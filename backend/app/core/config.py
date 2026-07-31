import re
from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORAGE_ROOT = (REPO_ROOT / "storage").resolve()
DEFAULT_DATABASE_URL = f"sqlite:///{(DEFAULT_STORAGE_ROOT / 'cineforge_local.db').as_posix()}"
DEFAULT_SULPHUR_MODEL_PATH = (
    Path.home()
    / ".lmstudio"
    / "models"
    / "SulphurAI"
    / "Sulphur-2-base"
    / "sulphur_prompt_enhancer_model-q8_0.gguf"
)
DEFAULT_QWEN_MODEL_PATH = (
    Path.home()
    / ".lmstudio"
    / "models"
    / "DavidAU"
    / "Qwen3-4B-Hivemind-Instruct-Heretic-Abliterated-Uncensored-NEO-Imatrix-GGUF"
    / "Qwen3-4B-Hivemind-Inst-Hrtic-Ablit-Uncensored-Q4_K_M-imat.gguf"
)
DEFAULT_QWEN_MODEL_ID = (
    "qwen3-4b-hivemind-instruct-heretic-abliterated-uncensored-neo-imatrix"
)

_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$")
_FORBIDDEN_URL_CHARS = set(";|`$\n\r&<>")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_prefix="CINEFORGE_",
        extra="ignore",
    )

    env: str = "local"
    log_level: str = "INFO"
    database_url: str = DEFAULT_DATABASE_URL
    comfyui_base_url: AnyHttpUrl = "http://127.0.0.1:8888"
    comfy_api_runner_base_url: AnyHttpUrl = "http://127.0.0.1:8022"
    storage_root: Path = Field(default=DEFAULT_STORAGE_ROOT)
    allow_absolute_input_paths: bool = False
    queue_worker_enabled: bool = False
    autonomy_mode: str = "scaffold_only"
    cors_allowed_origins: list[str] = [
        "http://127.0.0.1:5180",
        "http://localhost:5180",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
    ]

    # ------------------------------------------------------------------
    # OpenAI planning provider (configuration only; no credential persistence)
    # ------------------------------------------------------------------
    # Logical Sol/Terra/Luna model identifiers map to hosted OpenAI model IDs.
    # These are control-plane settings only — never shell commands or paths.
    openai_planning_enabled: bool = False
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_sec: float = Field(default=60.0, ge=1.0, le=600.0)
    openai_wall_time_sec: float = Field(default=120.0, ge=1.0, le=1800.0)
    openai_transport_retries: int = Field(default=2, ge=0, le=5)
    openai_max_response_bytes: int = Field(default=524_288, ge=1024, le=8_388_608)
    openai_repair_instruction_limit: int = Field(default=12, ge=0, le=20)
    openai_logical_model_luna: str = "gpt-4o-mini"
    openai_logical_model_terra: str = "gpt-4o"
    openai_logical_model_sol: str = "gpt-4.1"

    # ------------------------------------------------------------------
    # Local Sulphur planning and prompt/script enhancement through LM Studio
    # ------------------------------------------------------------------
    # Disabled in library/test contexts. The trusted workstation launcher
    # enables these settings for the supervised local stack.
    sulphur_planning_enabled: bool = False
    sulphur_phase_one_enabled: bool = False
    sulphur_base_url: str = "http://127.0.0.1:1234/v1"
    sulphur_model_id: str = "sulphur-2-base"
    sulphur_model_path: Path = Field(default=DEFAULT_SULPHUR_MODEL_PATH)
    qwen_model_id: str = DEFAULT_QWEN_MODEL_ID
    qwen_model_path: Path = Field(default=DEFAULT_QWEN_MODEL_PATH)
    sulphur_timeout_sec: float = Field(default=300.0, ge=1.0, le=900.0)
    sulphur_wall_time_sec: float = Field(default=420.0, ge=1.0, le=1200.0)
    sulphur_transport_retries: int = Field(default=1, ge=0, le=3)
    sulphur_max_response_bytes: int = Field(default=1_048_576, ge=1024, le=8_388_608)
    sulphur_repair_instruction_limit: int = Field(default=12, ge=0, le=20)

    @field_validator("storage_root", mode="before")
    @classmethod
    def resolve_storage_root(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path.resolve()

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_sqlite_database_url(cls, value: str) -> str:
        cleaned = str(value).strip()
        prefix = "sqlite:///"
        if not cleaned.startswith(prefix):
            return cleaned
        raw_path = cleaned[len(prefix) :]
        if raw_path in {":memory:", ""} or raw_path.startswith("file:"):
            return cleaned
        database_path = Path(raw_path).expanduser()
        if not database_path.is_absolute():
            database_path = REPO_ROOT / database_path
        return f"{prefix}{database_path.resolve().as_posix()}"

    @field_validator("openai_base_url", "sulphur_base_url")
    @classmethod
    def validate_provider_base_url(cls, value: str) -> str:
        cleaned = (value or "").strip().rstrip("/")
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("provider base URL must be an http(s) URL")
        if any(ch in cleaned for ch in _FORBIDDEN_URL_CHARS):
            raise ValueError("provider base URL contains forbidden characters")
        # Reject shell/executable path shapes — HTTP endpoints only.
        if cleaned.lower().startswith(("file:", "ftp:")):
            raise ValueError("provider base URL must be an http(s) URL")
        return cleaned

    @field_validator("sulphur_base_url")
    @classmethod
    def validate_sulphur_loopback_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        try:
            is_loopback = ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            is_loopback = (parsed.hostname or "").lower() == "localhost"
        if (
            parsed.scheme != "http"
            or not is_loopback
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("sulphur_base_url must remain an HTTP loopback API URL")
        return value

    @field_validator(
        "openai_logical_model_luna",
        "openai_logical_model_terra",
        "openai_logical_model_sol",
        "sulphur_model_id",
        "qwen_model_id",
    )
    @classmethod
    def validate_logical_model_id(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned or not _MODEL_ID_RE.match(cleaned):
            raise ValueError(
                "logical model identifier must be a safe model id "
                "(letters, digits, . _ / : -); shell commands and paths are rejected"
            )
        lowered = cleaned.lower()
        if any(
            token in lowered
            for token in (
                ".exe",
                ".bat",
                ".cmd",
                ".ps1",
                ".sh",
                "powershell",
                "cmd.exe",
                "/bin/",
                "\\",
            )
        ):
            raise ValueError("logical model identifier must not look like an executable path")
        return cleaned

    @field_validator("sulphur_model_path", "qwen_model_path", mode="before")
    @classmethod
    def resolve_local_model_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser().resolve()

    @property
    def openai_configured(self) -> bool:
        """True when the OpenAI planning adapter may be constructed."""
        if not self.openai_planning_enabled:
            return False
        if self.openai_api_key is None:
            return False
        secret = self.openai_api_key.get_secret_value()
        return bool(secret and secret.strip())

    @property
    def sulphur_configured(self) -> bool:
        """True when the approved local Sulphur model may serve planning."""
        return (
            self.sulphur_planning_enabled
            and self.sulphur_model_path.is_file()
            and self.sulphur_model_path.suffix.casefold() == ".gguf"
        )

    @property
    def qwen_configured(self) -> bool:
        """True when the approved local Qwen model may serve planning."""
        return (
            self.sulphur_planning_enabled
            and self.qwen_model_path.is_file()
            and self.qwen_model_path.suffix.casefold() == ".gguf"
        )

    @property
    def workflow_template_root(self) -> Path:
        return self.storage_root / "workflow_templates"

    @property
    def workflow_snapshot_root(self) -> Path:
        return self.storage_root / "workflow_snapshots"

    @property
    def probes_root(self) -> Path:
        return self.storage_root / "probes"


@lru_cache
def get_settings() -> Settings:
    return Settings()
