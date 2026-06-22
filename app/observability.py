from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

"""
Standard LogRecord attributes, everything else else on a record came from
`extra=` and should be merged into the JSON payload
"""
_RESERVED = set(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    """
    point the logger at stdout with the JsonFormatter
    safe to call on every `create_app` (including per-test)
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger()
    logger.handlers[:] = [handler]
    logger.setLevel(level)
    logger.propagate = False  # don't double-emit through root logger
