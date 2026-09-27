"""Service configuration loaded from environment variables.

All settings have safe development defaults.  No credentials are hard-coded:
API keys and URLs must be supplied to the process by the shell, the service
manager, or the container runtime.

A ``.env`` file is **not** loaded: ``python-dotenv`` is not a dependency and
only ``os.getenv`` is used below.  ``apps/ai-engine/.env.example`` is a
reference/template listing these variables, not a runtime input.

Usage::

    from app.config import settings
    print(settings.provider)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration.

    Attributes
    ----------
    host:
        Network interface to bind (default: ``0.0.0.0``).
    port:
        TCP port to listen on (default: ``8000``).
    provider:
        LLM provider to use: ``"ollama"`` or ``"openai"`` (default: ``"ollama"``).
    model:
        Model name forwarded to the provider (default: ``"llama3"``).
    provider_base_url:
        Base URL for self-hosted providers such as Ollama
        (default: ``"http://localhost:11434"``).
    request_timeout:
        Seconds to wait for a provider response before raising a timeout
        (default: ``60``).
    api_key:
        API key for cloud providers (e.g. OpenAI).  ``None`` when not set.
        Never logged or serialised.
    log_level:
        Threshold for this service's own log records, e.g. ``"DEBUG"`` or
        ``"INFO"`` (default: ``"INFO"``).  Consumed by ``app.observability``;
        it does not affect the web server's own loggers.
    """

    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    provider: str = field(default_factory=lambda: os.getenv("PROVIDER", "ollama"))
    model: str = field(default_factory=lambda: os.getenv("MODEL", "llama3"))
    provider_base_url: str = field(
        default_factory=lambda: os.getenv("PROVIDER_BASE_URL", "http://localhost:11434")
    )
    request_timeout: int = field(
        default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "60"))
    )
    api_key: str | None = field(
        default_factory=lambda: os.getenv("PROVIDER_API_KEY") or None
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def is_configured(self) -> bool:
        """Return ``True`` when the service has the minimum required config.

        Currently the service can operate with Ollama (no API key required)
        so the only requirement is a non-empty provider name.  Cloud providers
        that require an API key should add additional checks here.
        """
        if not self.provider:
            return False
        if self.provider in ("openai", "anthropic") and not self.api_key:
            return False
        return True


# Module-level singleton — imported by other modules.
settings = Settings()
