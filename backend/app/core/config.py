import ipaddress
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]
_EMAIL_ADDRESS = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
_CONTACT_HINT = (
    "Enter an email address (it will be saved as mailto:), a mailto: email address, "
    "or an https:// contact page."
)


class Settings(BaseSettings):
    """Server-only settings. Public API responses use an explicit allowlist."""

    model_config = SettingsConfigDict(
        env_prefix="RF_",
        env_file=ROOT / ".env",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test"] = "development"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_url: SecretStr | None = None
    llm_provider: Literal["disabled", "mock", "openai", "ollama"] = "disabled"
    search_provider: Literal["disabled", "mock", "brave", "wikipedia"] = "disabled"
    openai_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None
    llm_model: Literal["gpt-4.1-mini", "gpt-4.1"] | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = Field(
        default="qwen3:8b", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:/-]+$"
    )
    ollama_context_tokens: int = Field(default=8192, ge=2048, le=16384)
    ollama_timeout_seconds: float = Field(default=90, ge=5, le=180)
    ollama_keep_alive: str = Field(default="5m", min_length=1, max_length=16)
    free_search_enabled: bool = False
    public_search_contact: str | None = Field(default=None, max_length=200)
    live_calls_approved: bool = False
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=1500, ge=256, le=3000)
    provider_timeout_seconds: float = Field(default=15, ge=1, le=30)
    provider_retries: int = Field(default=1, ge=0, le=2)
    max_external_retries: int = Field(default=0, ge=0, le=2)
    run_timeout_seconds: float = Field(default=120, ge=5, le=180)
    max_search_queries: int = Field(default=5, ge=1, le=5)
    max_sources: int = Field(default=5, ge=1, le=8)
    max_tool_calls: int = Field(default=18, ge=2, le=40)
    max_context_chars: int = Field(default=16000, ge=8000, le=32000)
    max_page_bytes: int = Field(default=512000, ge=1024, le=1000000)
    max_article_text_chars: int = Field(default=20000, ge=1000, le=50000)
    max_external_requests_per_run: int = Field(default=3, ge=1, le=20)
    max_external_search_requests: int = Field(default=1, ge=0, le=10)
    max_article_fetch_attempts: int = Field(default=2, ge=0, le=20)
    max_global_external_requests: int | None = Field(default=None, ge=1, le=100)
    max_verification_iterations: int = Field(default=1, ge=0, le=2)
    max_followup_searches: int = Field(default=1, ge=0, le=2)
    max_llm_calls: int = Field(default=16, ge=4, le=24)
    max_total_tokens: int = Field(default=24000, ge=1000, le=60000)
    max_estimated_cost_usd: float = Field(default=0.25, gt=0, le=5, allow_inf_nan=False)
    storage_root: Path = ROOT / "data/documents"
    embedding_provider: Literal["fake", "local"] = "local"
    embedding_model: Literal["BAAI/bge-small-en-v1.5"] = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = Field(default=8, ge=1, le=16)
    model_cache: Path = ROOT / "data/models"
    qdrant_url: Literal["http://127.0.0.1:6333"] = "http://127.0.0.1:6333"
    qdrant_namespace: str = Field(default="researchforge", pattern=r"^[a-z][a-z0-9_]{0,60}$")
    max_upload_bytes: int = Field(default=5_000_000, ge=1024, le=10_000_000)
    max_documents: int = Field(default=30, ge=1, le=100)
    chunk_chars: int = Field(default=1000, ge=300, le=1500)
    chunk_overlap: int = Field(default=150, ge=0, le=250)
    retrieval_k: int = Field(default=5, ge=1, le=10)
    input_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    search_usd_per_request: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_providers(self) -> "Settings":
        pair = (self.llm_provider, self.search_provider)
        if pair not in {
            ("disabled", "disabled"),
            ("mock", "mock"),
            ("openai", "brave"),
            ("ollama", "disabled"),
            ("ollama", "mock"),
            ("ollama", "wikipedia"),
        }:
            raise ValueError(
                "Use disabled/disabled, mock/mock, openai/brave, or ollama with local search"
            )
        if self.search_provider == "wikipedia" and not self.free_search_enabled:
            raise ValueError("Set RF_FREE_SEARCH_ENABLED=true to enable public Wikipedia search")
        if self.free_search_enabled and self.search_provider != "wikipedia":
            raise ValueError("Free public search approval applies only to the Wikipedia provider")
        if self.free_search_enabled and not self.public_search_contact:
            raise ValueError("Set RF_PUBLIC_SEARCH_CONTACT to a public contact URL or email")
        if self.ollama_context_tokens < self.max_context_chars // 4 + self.llm_max_output_tokens:
            raise ValueError(
                "Ollama context tokens must cover the configured prompt and output caps"
            )
        self._validate_ollama_url(self.ollama_url)
        if self.llm_provider == "openai" and (
            self.llm_model is None
            or any(
                key is None or len(key.get_secret_value().strip()) < 12
                for key in (self.openai_api_key, self.brave_api_key)
            )
        ):
            raise ValueError("Hosted providers require a supported model and both backend API keys")
        if self.execution_mode == "live" and any(
            value is None
            for value in (
                self.input_usd_per_million,
                self.output_usd_per_million,
                self.search_usd_per_request,
            )
        ):
            raise ValueError(
                "Live mode requires operator-confirmed LLM and search unit prices for cost controls"
            )
        return self

    @field_validator("public_search_contact")
    @classmethod
    def validate_public_search_contact(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError(f"Public search contact is invalid. {_CONTACT_HINT}")
        # A plain email is the easiest private input for most operators. Normalize it
        # before validating so every downstream User-Agent receives a mailto: value.
        if ":" not in value and _EMAIL_ADDRESS.fullmatch(value):
            value = f"mailto:{value}"
        try:
            parsed = urlsplit(value)
            if parsed.scheme == "https":
                if (
                    not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or any(character.isspace() for character in value)
                ):
                    raise ValueError
                _ = parsed.port  # Reject malformed ports during configuration, not on a request.
            elif parsed.scheme == "mailto":
                address = parsed.path
                if (
                    parsed.netloc
                    or parsed.query
                    or parsed.fragment
                    or not _EMAIL_ADDRESS.fullmatch(address)
                ):
                    raise ValueError
            else:
                raise ValueError
        except ValueError as exc:
            raise ValueError(f"Public search contact is invalid. {_CONTACT_HINT}") from exc
        return value

    @property
    def execution_mode(self) -> Literal["disabled", "mock", "local", "live"]:
        if self.llm_provider == "mock":
            return "mock"
        if self.llm_provider == "ollama":
            return "local"
        if self.llm_provider == "openai" and self.live_calls_approved:
            return "live"
        return "disabled"

    @staticmethod
    def _validate_ollama_url(value: str) -> str:
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            try:
                is_loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                is_loopback = host.lower() == "localhost"
            if (
                parsed.scheme != "http"
                or not is_loopback
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.port is None
            ):
                raise ValueError
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("Ollama must use an explicit HTTP loopback URL") from exc
        return value.rstrip("/")

    @field_validator("ollama_url")
    @classmethod
    def local_ollama_only(cls, value: str) -> str:
        return cls._validate_ollama_url(value)

    @field_validator("public_search_contact")
    @classmethod
    def validate_public_contact(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        parsed = urlsplit(candidate)
        valid_url = parsed.scheme == "https" and bool(parsed.hostname)
        valid_email = parsed.scheme == "mailto" and "@" in parsed.path
        if (
            not candidate
            or "\n" in candidate
            or "\r" in candidate
            or not (valid_url or valid_email)
        ):
            raise ValueError("Public search contact must be an HTTPS URL or mailto address")
        return candidate

    @field_validator("database_url")
    @classmethod
    def local_postgres_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            try:
                url = make_url(value.get_secret_value())
                valid = (
                    url.drivername == "postgresql+psycopg"
                    and url.host in {"localhost", "127.0.0.1", "::1"}
                    and bool(url.database)
                    and not url.query
                )
            except Exception:
                valid = False
            if not valid:
                raise ValueError(
                    "Use a local postgresql+psycopg database URL without query options"
                )
        return value

    @field_validator("cors_origins")
    @classmethod
    def local_origins_only(cls, values: list[str]) -> list[str]:
        for value in values:
            url = urlsplit(value)
            if (
                url.scheme != "http"
                or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or url.username is not None
                or url.password is not None
                or url.path
                or url.query
                or url.fragment
            ):
                raise ValueError("CORS origins must be exact local HTTP origins")
            # Accessing .port rejects malformed or out-of-range ports.
            _ = url.port
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()
