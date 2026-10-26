import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
                **{
                    key: getattr(record, key)
                    for key in (
                        "method",
                        "status_code",
                        "latency_ms",
                        "request_id",
                        "session_id",
                        "run_id",
                        "stage",
                        "provider_type",
                        "model_id",
                        "duration_ms",
                        "llm_requests",
                        "search_requests",
                        "tool_calls",
                        "token_usage",
                        "estimated_cost_usd",
                        "candidate_count",
                        "sufficiency_statuses",
                        "error_code",
                    )
                    if hasattr(record, key)
                },
            }
        )


def configure_logging() -> None:
    logger = logging.getLogger("researchforge")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
