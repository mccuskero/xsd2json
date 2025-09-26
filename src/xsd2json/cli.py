"""Command-line interface for XSD2JSON converter."""

import sys
from pathlib import Path
from typing import Optional

import click

from . import __version__
from .config import Config, LogLevel, OutputMode
from .converter import Converter
from .logger import create_logger


def validate_input_file(ctx, param, value):
    """Validate input file exists and has correct extension."""
    if value is None:
        return None

    path = Path(value)
    if not path.exists():
        raise click.BadParameter(f"Input file does not exist: {value}")

    if path.suffix.lower() not in {'.xsd', '.xml'}:
        raise click.BadParameter(f"Input file must have .xsd or .xml extension: {value}")

    return path


@click.command()
@click.version_option(__version__)
@click.option(
    "--input", "-i",
    required=True,
    callback=validate_input_file,
    help="Path to XSD schema file to convert"
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    help="Output directory (default: ./output)"
)
@click.option(
    "--output-mode",
    type=click.Choice([OutputMode.SINGLE, OutputMode.MULTI]),
    default=OutputMode.SINGLE,
    help="Output mode: single file or multiple files with references"
)
@click.option(
    "--log-level",
    type=click.Choice([LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR]),
    default=LogLevel.INFO,
    help="Logging level"
)
@click.option(
    "--llm-optimized",
    is_flag=True,
    help="Enable all LLM optimization flags"
)
@click.option(
    "--simplify",
    is_flag=True,
    help="LLM optimization: Simplify structure and reduce complexity"
)
@click.option(
    "--add-metadata",
    is_flag=True,
    help="LLM optimization: Add semantic hints and usage examples"
)
@click.option(
    "--flatten",
    is_flag=True,
    help="LLM optimization: Minimize hierarchy depth for token efficiency"
)
@click.option(
    "--natural-naming",
    is_flag=True,
    help="LLM optimization: Convert technical names to natural language"
)
@click.option(
    "--embed-docs",
    is_flag=True,
    help="LLM optimization: Include inline documentation and comments"
)
@click.option(
    "--diagnose",
    is_flag=True,
    help="Enable diagnostic mode with detailed analysis"
)
@click.option(
    "--pretty/--compact",
    default=True,
    help="Pretty-print JSON output (default: pretty)"
)
def main(
    input: Path,
    output: Optional[Path],
    output_mode: OutputMode,
    log_level: LogLevel,
    llm_optimized: bool,
    simplify: bool,
    add_metadata: bool,
    flatten: bool,
    natural_naming: bool,
    embed_docs: bool,
    diagnose: bool,
    pretty: bool,
) -> None:
    """Convert XSD schema files to JSON Schema with LLM optimization features.

    Examples:
        # Basic single-file conversion
        xsd2json --input schema.xsd

        # Multi-file output with LLM optimizations
        xsd2json --input schema.xsd --output-mode multi --llm-optimized

        # Custom LLM optimizations
        xsd2json --input schema.xsd --simplify --add-metadata --flatten
    """
    # Set default output directory
    if output is None:
        output = Path("./output")

    # Create configuration from CLI arguments
    config = Config.from_cli_args(
        input_file=input,
        output_dir=output,
        output_mode=output_mode,
        log_level=log_level,
        llm_optimized=llm_optimized,
        simplify=simplify,
        add_metadata=add_metadata,
        flatten=flatten,
        natural_naming=natural_naming,
        embed_docs=embed_docs,
        diagnose=diagnose,
        pretty=pretty,
    )

    # Enable all LLM optimizations if --llm-optimized flag is used
    if llm_optimized:
        config.enable_all_llm_optimizations()

    # Create logger with specified level
    logger = create_logger(level=config.logging.level, component="cli")

    # Validate configuration
    errors = config.validate()
    if errors:
        logger.error("Configuration validation failed", errors=errors)
        for error in errors:
            click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    # Log startup information
    logger.info(
        "Starting XSD2JSON conversion",
        inputFile=str(config.input_file),
        outputDir=str(config.output_dir),
        outputMode=config.output_mode,
        llmOptimized=config.llm_optimized,
    )

    try:
        # Create and run converter
        converter = Converter(config)
        result = converter.convert()

        if result.success:
            logger.info(
                "Conversion completed successfully",
                outputFiles=len(result.output_files),
                processingTime=result.processing_time,
            )
            click.echo(f"✓ Conversion completed successfully!")
            click.echo(f"  Output files: {len(result.output_files)}")
            click.echo(f"  Processing time: {result.processing_time:.2f}s")
        else:
            logger.error("Conversion failed", errors=result.errors)
            click.echo("✗ Conversion failed:", err=True)
            for error in result.errors:
                click.echo(f"  {error}", err=True)
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Conversion interrupted by user")
        click.echo("\nConversion interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Unexpected error during conversion", error=str(e), type=type(e).__name__)
        click.echo(f"✗ Unexpected error: {e}", err=True)
        if config.logging.level == LogLevel.DEBUG:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()