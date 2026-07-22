from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env_file(path: Path) -> None:
    """Load a small dotenv subset without ever logging values."""
    if not path.exists() or path.is_symlink():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(PROJECT_ROOT / ".env.local")
load_env_file(PROJECT_ROOT / ".env")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float, minimum: float = 1.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _bound_multiplier(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class ProviderConfig:
    participant: str
    base_url: str
    model: str
    api_style: str
    api_key_env: str
    reasoning_effort: str
    connect_timeout: float = 10.0
    first_token_timeout: float = 45.0
    stream_idle_timeout: float = 45.0
    total_timeout: float = 180.0

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    uploads_dir: Path
    db_path: Path
    host: str
    port: int
    digest_provider: str
    digest_interval: int
    recent_round_count: int
    host_checkpoint_interval: int
    live_max_output_tokens: int
    conversation_digest_max_output_tokens: int
    topic_digest_max_output_tokens: int
    source_digest_max_output_tokens: int
    momo: ProviderConfig
    bobby: ProviderConfig
    final_summary_max_output_tokens: int = 6000
    digest_section_timeout: float = 300.0
    digest_job_timeout: float = 900.0
    momo_live_max_output_tokens: int = 800
    bobby_live_max_output_tokens: int = 1400
    live_turn_token_multiplier: float = 1.5
    live_turn_timeout_multiplier: float = 1.5
    source_single_doc_token_multiplier: float = 1.5
    source_multi_doc_token_multiplier: float = 2.0
    source_single_doc_timeout_multiplier: float = 1.5
    source_multi_doc_timeout_multiplier: float = 2.0
    # Research profiles are deliberately separate from the provider defaults so
    # a session can opt into deeper models without changing the fast baseline.
    research_momo_model: str = "gpt-5.6-sol"
    research_bobby_model: str = "gemini-3.1-pro-preview"
    research_momo_reasoning_effort: str = "medium"
    research_bobby_reasoning_effort: str = "medium"
    verification_momo_model: str = "gpt-5.6-sol"
    verification_bobby_model: str = "gemini-3.1-pro-preview"
    verification_momo_reasoning_effort: str = "high"
    verification_bobby_reasoning_effort: str = "high"
    research_live_token_multiplier: float = 2.0
    research_live_timeout_multiplier: float = 2.0
    verification_live_token_multiplier: float = 2.0
    verification_live_timeout_multiplier: float = 2.5


def provider_from_env(name: str, default_model: str) -> ProviderConfig:
    prefix = name.upper()
    return ProviderConfig(
        participant=name.capitalize(),
        base_url=os.getenv(f"{prefix}_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        model=os.getenv(f"{prefix}_MODEL", default_model),
        api_style=os.getenv(f"{prefix}_API_STYLE", "responses").lower(),
        api_key_env=os.getenv(f"{prefix}_API_KEY_ENV", "OPENAI_API_KEY"),
        reasoning_effort=os.getenv(f"{prefix}_REASONING_EFFORT", "low"),
        connect_timeout=env_float(f"{prefix}_CONNECT_TIMEOUT_SECONDS", 10.0),
        first_token_timeout=env_float(f"{prefix}_FIRST_TOKEN_TIMEOUT_SECONDS", 45.0),
        stream_idle_timeout=env_float(f"{prefix}_STREAM_IDLE_TIMEOUT_SECONDS", 45.0),
        total_timeout=env_float(f"{prefix}_TOTAL_TIMEOUT_SECONDS", 180.0),
    )


def get_settings() -> Settings:
    raw_data_dir = Path(os.getenv("ROUNDTABLE_DATA_DIR", "./data"))
    data_dir = raw_data_dir if raw_data_dir.is_absolute() else PROJECT_ROOT / raw_data_dir
    live_default = max(250, env_int("LIVE_MAX_OUTPUT_TOKENS", 800))
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=data_dir,
        uploads_dir=data_dir / "uploads",
        db_path=data_dir / "roundtable.sqlite3",
        host=os.getenv("ROUNDTABLE_HOST", "127.0.0.1"),
        port=env_int("ROUNDTABLE_PORT", 8765),
        digest_provider=os.getenv("DIGEST_PROVIDER", "momo").lower(),
        digest_interval=max(5, min(6, env_int("ROUND_DIGEST_INTERVAL", 6))),
        recent_round_count=max(5, env_int("RECENT_ROUND_COUNT", 5)),
        host_checkpoint_interval=max(2, min(4, env_int("HOST_CHECKPOINT_INTERVAL", 3))),
        live_max_output_tokens=live_default,
        live_turn_token_multiplier=env_float("LIVE_TURN_TOKEN_BUDGET_MULTIPLIER", 1.5),
        live_turn_timeout_multiplier=env_float("LIVE_TURN_TIMEOUT_BUDGET_MULTIPLIER", 1.5),
        conversation_digest_max_output_tokens=max(
            2000, env_int("CONVERSATION_DIGEST_MAX_OUTPUT_TOKENS", 4000)
        ),
        final_summary_max_output_tokens=max(
            3000, env_int("FINAL_SUMMARY_MAX_OUTPUT_TOKENS", 6000)
        ),
        topic_digest_max_output_tokens=max(
            3000, env_int("TOPIC_DIGEST_MAX_OUTPUT_TOKENS", 6000)
        ),
        source_digest_max_output_tokens=max(
            4000, env_int("SOURCE_DIGEST_MAX_OUTPUT_TOKENS", 8000)
        ),
        source_single_doc_token_multiplier=_bound_multiplier(
            env_float("SOURCE_SINGLE_DOC_TOKEN_MULTIPLIER", 1.5), 1.25, 2.0
        ),
        source_multi_doc_token_multiplier=_bound_multiplier(
            env_float("SOURCE_MULTI_DOC_TOKEN_MULTIPLIER", 2.0), 1.5, 3.0
        ),
        source_single_doc_timeout_multiplier=_bound_multiplier(
            env_float("SOURCE_SINGLE_DOC_TIMEOUT_MULTIPLIER", 1.5), 1.25, 2.0
        ),
        source_multi_doc_timeout_multiplier=_bound_multiplier(
            env_float("SOURCE_MULTI_DOC_TIMEOUT_MULTIPLIER", 2.0), 1.5, 3.0
        ),
        momo=provider_from_env("momo", "gpt-5.6-luna"),
        bobby=provider_from_env("bobby", "gpt-5.6-terra"),
        digest_section_timeout=env_float("DIGEST_SECTION_TIMEOUT_SECONDS", 300.0),
        digest_job_timeout=env_float("DIGEST_JOB_TIMEOUT_SECONDS", 900.0),
        momo_live_max_output_tokens=max(
            250, env_int("MOMO_LIVE_MAX_OUTPUT_TOKENS", 800)
        ),
        bobby_live_max_output_tokens=max(
            250, env_int("BOBBY_LIVE_MAX_OUTPUT_TOKENS", 1400)
        ),
        research_momo_model=os.getenv("RESEARCH_MOMO_MODEL", "gpt-5.6-sol"),
        research_bobby_model=os.getenv("RESEARCH_BOBBY_MODEL", "gemini-3.1-pro-preview"),
        research_momo_reasoning_effort=os.getenv("RESEARCH_MOMO_REASONING_EFFORT", "medium"),
        research_bobby_reasoning_effort=os.getenv("RESEARCH_BOBBY_REASONING_EFFORT", "medium"),
        verification_momo_model=os.getenv("VERIFICATION_MOMO_MODEL", "gpt-5.6-sol"),
        verification_bobby_model=os.getenv("VERIFICATION_BOBBY_MODEL", "gemini-3.1-pro-preview"),
        verification_momo_reasoning_effort=os.getenv("VERIFICATION_MOMO_REASONING_EFFORT", "high"),
        verification_bobby_reasoning_effort=os.getenv("VERIFICATION_BOBBY_REASONING_EFFORT", "high"),
        research_live_token_multiplier=_bound_multiplier(
            env_float("RESEARCH_LIVE_TOKEN_MULTIPLIER", 2.0), 1.0, 3.0
        ),
        research_live_timeout_multiplier=_bound_multiplier(
            env_float("RESEARCH_LIVE_TIMEOUT_MULTIPLIER", 2.0), 1.0, 4.0
        ),
        verification_live_token_multiplier=_bound_multiplier(
            env_float("VERIFICATION_LIVE_TOKEN_MULTIPLIER", 2.0), 1.0, 3.0
        ),
        verification_live_timeout_multiplier=_bound_multiplier(
            env_float("VERIFICATION_LIVE_TIMEOUT_MULTIPLIER", 2.5), 1.0, 5.0
        ),
    )
