class ResearchFailure(Exception):
    """Safe public error code. Never include provider exceptions or retrieved text."""


class TransientProviderError(ResearchFailure):
    pass


class ProviderHTTPError(TransientProviderError):
    """A safe HTTP-status category for a provider response without its body."""

    def __init__(self, status_code: int) -> None:
        super().__init__("provider_http_error")
        self.status_code = status_code


class InvalidProviderOutput(TransientProviderError):
    """A local model response can receive one bounded schema-repair retry."""


MESSAGES = {
    "verification_failed": (
        "Mandatory evidence verification failed; no completed assessment is claimed."
    ),
    "no_evidence": "No usable evidence was collected. No report was generated.",
    "invalid_output": "The model returned invalid structured output or unknown citation IDs.",
    "provider_error": "A provider rejected the request. Check server-side configuration.",
    "model_unavailable": (
        "The local Ollama service or configured model is unavailable. "
        "Start Ollama and verify the model is installed."
    ),
    "provider_connection_failed": (
        "Could not connect to the local Ollama service. Check that it is running."
    ),
    "provider_timeout": "A provider timed out after bounded retries.",
    "provider_http_error": (
        "The local model service returned an HTTP error after bounded retries. "
        "Check the Ollama service logs."
    ),
    "provider_transient": "A provider remained temporarily unavailable after bounded retries.",
    "budget_exceeded": "The research resource budget was exhausted.",
    "request_budget_exceeded": (
        "The external request limit was reached. No further public requests were made."
    ),
    "run_timeout": "The research run exceeded its time limit.",
    "interrupted": "Execution was interrupted. It was not automatically replayed.",
    "internal_error": "Research could not finish. Partial evidence may be available.",
}
