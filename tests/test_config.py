"""Tests for configuration system."""

from pathlib import Path
import pytest

from src.xsd2json.config import (
    Config, OutputMode, AttributeStyle, ArrayPolicy,
    LLMOptimizations, LoggingConfig, SerializerConfig
)
from src.xsd2json.logger import LogLevel


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()

        assert config.input_file is None
        assert config.output_dir is None
        assert config.output_mode == OutputMode.SINGLE
        assert config.attr_style == AttributeStyle.PREFIX
        assert config.array_policy == ArrayPolicy.ANY_MAX
        assert not config.flatten_singletons
        assert config.preserve_qnames
        assert config.resolve_refs == "reference"
        assert config.namespace_handling == "preserve"
        assert not config.llm_optimized
        assert config.max_recursion_depth == 50
        assert config.cache_schemas
        assert config.parallel_processing

    def test_config_validation_missing_input(self):
        """Test validation with missing input file."""
        config = Config()
        errors = config.validate()

        assert len(errors) == 0  # input_file can be None initially

    def test_config_validation_nonexistent_input(self, temp_dir):
        """Test validation with non-existent input file."""
        config = Config()
        config.input_file = temp_dir / "nonexistent.xsd"
        errors = config.validate()

        assert len(errors) == 1
        assert "does not exist" in errors[0]

    def test_config_validation_wrong_extension(self, temp_dir):
        """Test validation with wrong file extension."""
        wrong_file = temp_dir / "test.txt"
        wrong_file.touch()

        config = Config()
        config.input_file = wrong_file
        errors = config.validate()

        assert len(errors) == 1
        assert "extension" in errors[0].lower()

    def test_config_validation_invalid_recursion_depth(self):
        """Test validation with invalid recursion depth."""
        config = Config()
        config.max_recursion_depth = 0
        errors = config.validate()

        assert len(errors) == 1
        assert "max_recursion_depth" in errors[0]

    def test_config_validation_nonexistent_output_parent(self, temp_dir):
        """Test validation with non-existent output parent directory."""
        config = Config()
        config.output_dir = temp_dir / "nonexistent" / "output"
        errors = config.validate()

        assert len(errors) == 1
        assert "parent does not exist" in errors[0]

    def test_config_validation_valid(self, simple_xsd_file, temp_dir):
        """Test validation with valid configuration."""
        config = Config()
        config.input_file = simple_xsd_file
        config.output_dir = temp_dir / "output"
        errors = config.validate()

        assert len(errors) == 0

    def test_enable_all_llm_optimizations(self):
        """Test enabling all LLM optimizations."""
        config = Config()
        assert not config.llm_optimized
        assert not config.llm.simplify

        config.enable_all_llm_optimizations()

        assert config.llm_optimized
        assert config.llm.simplify
        assert config.llm.add_metadata
        assert config.llm.flatten
        assert config.llm.natural_naming
        assert config.llm.embed_docs

    def test_from_cli_args_basic(self):
        """Test creating config from CLI arguments."""
        config = Config.from_cli_args(
            input_file=Path("test.xsd"),
            output_mode=OutputMode.MULTI,
            log_level="debug"
        )

        assert config.input_file == Path("test.xsd")
        assert config.output_mode == OutputMode.MULTI
        assert config.logging.level == LogLevel.DEBUG

    def test_from_cli_args_llm_flags(self):
        """Test creating config with LLM optimization flags."""
        config = Config.from_cli_args(
            simplify=True,
            add_metadata=True,
            natural_naming=True
        )

        assert config.llm_optimized
        assert config.llm.simplify
        assert config.llm.add_metadata
        assert config.llm.natural_naming
        assert not config.llm.flatten  # Not specified
        assert not config.llm.embed_docs  # Not specified

    def test_from_cli_args_no_llm_flags(self):
        """Test creating config without LLM optimization flags."""
        config = Config.from_cli_args(
            input_file=Path("test.xsd")
        )

        assert not config.llm_optimized
        assert not config.llm.simplify


class TestLLMOptimizations:
    """Tests for LLMOptimizations class."""

    def test_default_llm_optimizations(self):
        """Test default LLM optimization values."""
        llm = LLMOptimizations()

        assert not llm.simplify
        assert not llm.add_metadata
        assert not llm.flatten
        assert not llm.natural_naming
        assert not llm.embed_docs

    def test_llm_optimizations_all_enabled(self):
        """Test LLM optimizations with all enabled."""
        llm = LLMOptimizations(
            simplify=True,
            add_metadata=True,
            flatten=True,
            natural_naming=True,
            embed_docs=True
        )

        assert llm.simplify
        assert llm.add_metadata
        assert llm.flatten
        assert llm.natural_naming
        assert llm.embed_docs


class TestLoggingConfig:
    """Tests for LoggingConfig class."""

    def test_default_logging_config(self):
        """Test default logging configuration."""
        logging_config = LoggingConfig()

        assert logging_config.level == LogLevel.INFO
        assert logging_config.format == "json"
        assert logging_config.destination == "stdout"

    def test_custom_logging_config(self):
        """Test custom logging configuration."""
        logging_config = LoggingConfig(
            level=LogLevel.DEBUG,
            format="text",
            destination="file.log"
        )

        assert logging_config.level == LogLevel.DEBUG
        assert logging_config.format == "text"
        assert logging_config.destination == "file.log"


class TestSerializerConfig:
    """Tests for SerializerConfig class."""

    def test_default_serializer_config(self):
        """Test default serializer configuration."""
        serializer_config = SerializerConfig()

        assert serializer_config.format == "json"
        assert serializer_config.pretty
        assert not serializer_config.split_by_namespace

    def test_custom_serializer_config(self):
        """Test custom serializer configuration."""
        serializer_config = SerializerConfig(
            format="yaml",
            pretty=False,
            split_by_namespace=True
        )

        assert serializer_config.format == "yaml"
        assert not serializer_config.pretty
        assert serializer_config.split_by_namespace


class TestEnums:
    """Tests for enum classes."""

    def test_output_mode_enum(self):
        """Test OutputMode enum."""
        assert OutputMode.SINGLE == "single"
        assert OutputMode.MULTI == "multi"

    def test_attribute_style_enum(self):
        """Test AttributeStyle enum."""
        assert AttributeStyle.PREFIX == "prefix"
        assert AttributeStyle.GROUP == "group"

    def test_array_policy_enum(self):
        """Test ArrayPolicy enum."""
        assert ArrayPolicy.ANY_MAX == "anyMax"
        assert ArrayPolicy.MIN_MAX == "minMax"
        assert ArrayPolicy.EXPLICIT == "explicit"