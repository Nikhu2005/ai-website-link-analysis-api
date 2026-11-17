"""Application settings, loaded from environment variables (.env supported)."""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- LLM ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()  # gemini | openai | anthropic
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")  # empty -> provider default below
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

    # --- Website fetching ---
    FETCH_TIMEOUT_SECONDS: float = float(os.getenv("FETCH_TIMEOUT_SECONDS", "15"))
    MAX_DOWNLOAD_BYTES: int = int(os.getenv("MAX_DOWNLOAD_BYTES", str(2 * 1024 * 1024)))
    MAX_REDIRECTS: int = int(os.getenv("MAX_REDIRECTS", "5"))
    # Cap on text sent to the LLM (characters). Controls token cost.
    MAX_CONTENT_CHARS: int = int(os.getenv("MAX_CONTENT_CHARS", "12000"))
    USER_AGENT: str = os.getenv(
        "USER_AGENT", "Mozilla/5.0 (compatible; LinkAnalysisBot/1.0; +https://example.com/bot)"
    )

    # --- Cache ---
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

    DEFAULT_MODELS = {
        "gemini": "gemini-3.5-flash-lite",
        "openai": "gpt-5-mini",
        "anthropic": "claude-haiku-5-5",
    }

    @property
    def model(self) -> str:
        return self.LLM_MODEL or self.DEFAULT_MODELS.get(self.LLM_PROVIDER, "")

    @property
    def api_key(self) -> str:
        return {
            "gemini": self.GEMINI_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "anthropic": self.ANTHROPIC_API_KEY,
        }.get(self.LLM_PROVIDER, "")


settings = Settings()
