"""Structured logging system for XSD2JSON converter."""

import json
import logging
import sys
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class LogLevel(str, Enum):
    """Supported log levels."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname.lower(),
            "component": getattr(record, "component", "xsd2json"),
            "message": record.getMessage(),
        }

        # Add optional fields if present
        optional_fields = ["schema", "operationId", "sourceURI", "line", "col", "errorCode"]
        for field in optional_fields:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        # Add extra fields from record
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_entry.update(record.extra)

        return json.dumps(log_entry, default=str)


class XSDLogger:
    """Centralized logging system with structured output."""

    def __init__(self, level: LogLevel = LogLevel.INFO, component: str = "xsd2json"):
        self.component = component
        self.operation_id = str(uuid4())

        # Setup logger
        self.logger = logging.getLogger(f"xsd2json.{component}")
        self.logger.setLevel(getattr(logging, level.upper()))

        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Add structured handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(handler)

        # Prevent propagation to root logger
        self.logger.propagate = False

    def _log(self, level: str, message: str, **kwargs) -> None:
        """Internal logging method with structured fields."""
        extra = {
            "component": self.component,
            "operationId": self.operation_id,
            **kwargs
        }

        # Create LogRecord with extra fields
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=getattr(logging, level.upper()),
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
            extra=extra
        )

        self.logger.handle(record)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._log("debug", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._log("info", message, **kwargs)

    def warn(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._log("warning", message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self._log("error", message, **kwargs)

    def schema_event(self, event: str, schema_uri: str, **kwargs) -> None:
        """Log schema-related events."""
        self.info(f"Schema {event}", schema=schema_uri, **kwargs)

    def parsing_progress(self, message: str, elements_processed: int = 0, **kwargs) -> None:
        """Log parsing progress."""
        self.info(message, elementsProcessed=elements_processed, **kwargs)

    def mapping_decision(self, decision: str, xsd_construct: str, json_output: str, **kwargs) -> None:
        """Log mapping decisions for debugging."""
        self.debug(
            f"Mapping decision: {decision}",
            xsdConstruct=xsd_construct,
            jsonOutput=json_output,
            **kwargs
        )

    def performance_metric(self, metric_name: str, value: Any, unit: str = "", **kwargs) -> None:
        """Log performance metrics."""
        self.info(
            f"Performance: {metric_name}",
            metricName=metric_name,
            value=value,
            unit=unit,
            **kwargs
        )


def create_logger(level: LogLevel = LogLevel.INFO, component: str = "xsd2json") -> XSDLogger:
    """Create a configured logger instance."""
    return XSDLogger(level=level, component=component)


# Global logger instance
logger = create_logger()