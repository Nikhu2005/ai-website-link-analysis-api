"""Domain errors mapped to HTTP status codes in main.py."""


class AnalysisError(Exception):
    status_code = 500
    code = "analysis_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidURLError(AnalysisError):
    status_code = 400
    code = "invalid_url"


class WebsiteFetchError(AnalysisError):
    """Site unreachable, blocked, timed out, or not HTML."""

    status_code = 422
    code = "website_unreachable"


class LLMError(AnalysisError):
    status_code = 502
    code = "llm_error"


class LLMConfigError(AnalysisError):
    status_code = 503
    code = "llm_not_configured"
