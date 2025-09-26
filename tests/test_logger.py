"""Tests for logging system."""

import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest

from src.xsd2json.logger import (
    LogLevel, StructuredFormatter, XSDLogger, create_logger, logger
)


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_level_values(self):
        """Test LogLevel enum values."""
        assert LogLevel.DEBUG == "debug"
        assert LogLevel.INFO == "info"
        assert LogLevel.WARN == "warn"
        assert LogLevel.ERROR == "error"


class TestStructuredFormatter:
    """Tests for StructuredFormatter class."""

    def test_basic_formatting(self):
        """Test basic log record formatting."""
        formatter = StructuredFormatter()

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None
        )

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data["level"] == "info"
        assert log_data["component"] == "xsd2json"
        assert log_data["message"] == "Test message"
        assert "timestamp" in log_data

    def test_formatting_with_component(self):
        """Test formatting with component attribute."""
        formatter = StructuredFormatter()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error message",
            args=(),
            exc_info=None
        )
        record.component = "parser"

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data["component"] == "parser"

    def test_formatting_with_optional_fields(self):
        """Test formatting with optional fields."""
        formatter = StructuredFormatter()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Debug message",
            args=(),
            exc_info=None
        )
        record.schema = "test.xsd"
        record.operationId = "12345"
        record.line = 42

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data["schema"] == "test.xsd"
        assert log_data["operationId"] == "12345"
        assert log_data["line"] == 42

    def test_formatting_with_extra_fields(self):
        """Test formatting with extra fields."""
        formatter = StructuredFormatter()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Info message",
            args=(),
            exc_info=None
        )
        record.extra = {"custom_field": "custom_value"}

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        assert log_data["custom_field"] == "custom_value"


class TestXSDLogger:
    """Tests for XSDLogger class."""

    def setUp(self):
        """Set up test logger with string stream."""
        self.stream = StringIO()
        self.logger = XSDLogger(level=LogLevel.DEBUG, component="test")

        # Replace the handler with our test handler
        for handler in self.logger.logger.handlers:
            self.logger.logger.removeHandler(handler)

        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(StructuredFormatter())
        self.logger.logger.addHandler(handler)

    def test_logger_creation(self):
        """Test logger creation with defaults."""
        logger = XSDLogger()

        assert logger.component == "xsd2json"
        assert logger.operation_id  # Should be generated
        assert logger.logger.level == logging.INFO

    def test_logger_creation_with_params(self):
        """Test logger creation with custom parameters."""
        logger = XSDLogger(level=LogLevel.DEBUG, component="parser")

        assert logger.component == "parser"
        assert logger.logger.level == logging.DEBUG

    def test_debug_logging(self):
        """Test debug level logging."""
        self.setUp()

        self.logger.debug("Debug message", extra_field="value")

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["level"] == "debug"
        assert log_data["message"] == "Debug message"
        assert log_data["component"] == "test"

    def test_info_logging(self):
        """Test info level logging."""
        self.setUp()

        self.logger.info("Info message")

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["level"] == "info"
        assert log_data["message"] == "Info message"

    def test_warn_logging(self):
        """Test warn level logging."""
        self.setUp()

        self.logger.warn("Warning message")

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["level"] == "warning"
        assert log_data["message"] == "Warning message"

    def test_error_logging(self):
        """Test error level logging."""
        self.setUp()

        self.logger.error("Error message")

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["level"] == "error"
        assert log_data["message"] == "Error message"

    def test_schema_event_logging(self):
        """Test schema event logging."""
        self.setUp()

        self.logger.schema_event("loaded", "test.xsd", duration=1.5)

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["message"] == "Schema loaded"
        assert log_data["schema"] == "test.xsd"
        assert log_data["duration"] == 1.5

    def test_parsing_progress_logging(self):
        """Test parsing progress logging."""
        self.setUp()

        self.logger.parsing_progress("Processing elements", elements_processed=10)

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["message"] == "Processing elements"
        assert log_data["elementsProcessed"] == 10

    def test_mapping_decision_logging(self):
        """Test mapping decision logging."""
        self.setUp()

        self.logger.mapping_decision("Convert to object", "complexType", "object")

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["level"] == "debug"
        assert "Convert to object" in log_data["message"]
        assert log_data["xsdConstruct"] == "complexType"
        assert log_data["jsonOutput"] == "object"

    def test_performance_metric_logging(self):
        """Test performance metric logging."""
        self.setUp()

        self.logger.performance_metric("parsing_time", 2.5, "seconds")

        output = self.stream.getvalue()
        log_data = json.loads(output)

        assert log_data["message"] == "Performance: parsing_time"
        assert log_data["metricName"] == "parsing_time"
        assert log_data["value"] == 2.5
        assert log_data["unit"] == "seconds"

    def test_operation_id_consistency(self):
        """Test that operation ID is consistent across logs."""
        self.setUp()

        self.logger.info("First message")
        self.logger.info("Second message")

        output = self.stream.getvalue()
        lines = output.strip().split('\n')

        log1 = json.loads(lines[0])
        log2 = json.loads(lines[1])

        assert log1["operationId"] == log2["operationId"]


class TestCreateLogger:
    """Tests for create_logger function."""

    def test_create_logger_default(self):
        """Test creating logger with defaults."""
        logger = create_logger()

        assert isinstance(logger, XSDLogger)
        assert logger.component == "xsd2json"

    def test_create_logger_with_params(self):
        """Test creating logger with parameters."""
        logger = create_logger(level=LogLevel.ERROR, component="converter")

        assert logger.component == "converter"
        assert logger.logger.level == logging.ERROR


class TestGlobalLogger:
    """Tests for global logger instance."""

    def test_global_logger_exists(self):
        """Test that global logger instance exists."""
        assert logger is not None
        assert isinstance(logger, XSDLogger)
        assert logger.component == "xsd2json"