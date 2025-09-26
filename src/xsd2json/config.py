"""Configuration management for XSD2JSON converter."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .logger import LogLevel


class OutputMode(str, Enum):
    """Output mode options."""
    SINGLE = "single"
    MULTI = "multi"


class AttributeStyle(str, Enum):
    """Attribute representation styles."""
    PREFIX = "prefix"  # @attribute
    GROUP = "group"    # _attributes: {...}


class ArrayPolicy(str, Enum):
    """Array detection policies."""
    ANY_MAX = "anyMax"      # maxOccurs > 1 or unbounded
    MIN_MAX = "minMax"      # Consider both min and max
    EXPLICIT = "explicit"   # Only when explicitly defined


@dataclass
class LLMOptimizations:
    """LLM-specific optimization settings."""
    simplify: bool = False          # Reduce complexity, flatten unnecessary nesting
    add_metadata: bool = False      # Include semantic hints and examples
    flatten: bool = False           # Minimize hierarchy depth
    natural_naming: bool = False    # Convert technical names to natural language
    embed_docs: bool = False        # Include inline documentation


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: LogLevel = LogLevel.INFO
    format: str = "json"
    destination: str = "stdout"


@dataclass
class SerializerConfig:
    """Output serialization configuration."""
    format: str = "json"
    pretty: bool = True
    split_by_namespace: bool = False


@dataclass
class Config:
    """Main configuration for XSD2JSON converter."""

    # Input/Output
    input_file: Optional[Path] = None
    output_dir: Optional[Path] = None
    output_mode: OutputMode = OutputMode.SINGLE

    # XSD Processing
    attr_style: AttributeStyle = AttributeStyle.PREFIX
    array_policy: ArrayPolicy = ArrayPolicy.ANY_MAX
    flatten_singletons: bool = False
    preserve_qnames: bool = True
    resolve_refs: str = "reference"  # "inline" | "reference"
    namespace_handling: str = "preserve"  # "preserve" | "collapse"

    # LLM Optimizations
    llm_optimized: bool = False
    llm: LLMOptimizations = field(default_factory=LLMOptimizations)

    # System Configuration
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    serializer: SerializerConfig = field(default_factory=SerializerConfig)

    # Advanced Options
    diagnose: bool = False
    max_recursion_depth: int = 50
    cache_schemas: bool = True
    parallel_processing: bool = True

    def enable_all_llm_optimizations(self) -> None:
        """Enable all LLM optimization flags."""
        self.llm_optimized = True
        self.llm.simplify = True
        self.llm.add_metadata = True
        self.llm.flatten = True
        self.llm.natural_naming = True
        self.llm.embed_docs = True

    def validate(self) -> List[str]:
        """Validate configuration and return any errors."""
        errors = []

        if self.input_file and not self.input_file.exists():
            errors.append(f"Input file does not exist: {self.input_file}")

        if self.input_file and self.input_file.suffix.lower() not in {'.xsd', '.xml'}:
            errors.append(f"Input file must have .xsd or .xml extension: {self.input_file}")

        if self.output_dir and not self.output_dir.parent.exists():
            errors.append(f"Output directory parent does not exist: {self.output_dir.parent}")

        if self.max_recursion_depth < 1:
            errors.append("max_recursion_depth must be at least 1")

        return errors

    @classmethod
    def from_cli_args(cls, **kwargs) -> "Config":
        """Create config from CLI arguments."""
        config = cls()

        # Update with provided arguments
        for key, value in kwargs.items():
            if hasattr(config, key) and value is not None:
                setattr(config, key, value)

        # Handle nested LLM optimizations
        llm_flags = {
            "simplify": kwargs.get("simplify", False),
            "add_metadata": kwargs.get("add_metadata", False),
            "flatten": kwargs.get("flatten", False),
            "natural_naming": kwargs.get("natural_naming", False),
            "embed_docs": kwargs.get("embed_docs", False),
        }

        if any(llm_flags.values()):
            config.llm_optimized = True
            for flag, enabled in llm_flags.items():
                setattr(config.llm, flag, enabled)

        # Handle logging level
        if "log_level" in kwargs:
            config.logging.level = LogLevel(kwargs["log_level"])

        return config