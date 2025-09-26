"""Tests for CLI system."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from src.xsd2json.cli import main, validate_input_file
from src.xsd2json.config import OutputMode
from src.xsd2json.logger import LogLevel


class TestValidateInputFile:
    """Tests for input file validation function."""

    def test_validate_input_file_none(self):
        """Test validation with None input."""
        result = validate_input_file(None, None, None)
        assert result is None

    def test_validate_input_file_nonexistent(self, temp_dir):
        """Test validation with non-existent file."""
        runner = CliRunner()
        nonexistent_file = str(temp_dir / "nonexistent.xsd")

        with pytest.raises(SystemExit):
            with runner.isolated_filesystem():
                validate_input_file(None, None, nonexistent_file)

    def test_validate_input_file_wrong_extension(self, temp_dir):
        """Test validation with wrong extension."""
        wrong_file = temp_dir / "test.txt"
        wrong_file.touch()

        runner = CliRunner()

        with pytest.raises(SystemExit):
            validate_input_file(None, None, str(wrong_file))

    def test_validate_input_file_valid_xsd(self, simple_xsd_file):
        """Test validation with valid XSD file."""
        result = validate_input_file(None, None, str(simple_xsd_file))
        assert result == simple_xsd_file

    def test_validate_input_file_valid_xml(self, temp_dir):
        """Test validation with valid XML file."""
        xml_file = temp_dir / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><root/>", encoding='utf-8')

        result = validate_input_file(None, None, str(xml_file))
        assert result == xml_file


class TestCLIMain:
    """Tests for main CLI function."""

    def setup_method(self):
        """Set up test method."""
        self.runner = CliRunner()

    def test_cli_help(self):
        """Test CLI help output."""
        result = self.runner.invoke(main, ['--help'])

        assert result.exit_code == 0
        assert "Convert XSD schema files to JSON Schema" in result.output
        assert "--input" in result.output
        assert "--output-mode" in result.output

    def test_cli_version(self):
        """Test CLI version output."""
        result = self.runner.invoke(main, ['--version'])

        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_cli_missing_input(self):
        """Test CLI with missing required input."""
        result = self.runner.invoke(main, [])

        assert result.exit_code != 0
        assert "Missing option" in result.output

    def test_cli_nonexistent_input(self, temp_dir):
        """Test CLI with non-existent input file."""
        nonexistent_file = temp_dir / "nonexistent.xsd"

        result = self.runner.invoke(main, [
            '--input', str(nonexistent_file)
        ])

        assert result.exit_code != 0
        assert "does not exist" in result.output

    @patch('src.xsd2json.cli.Converter')
    def test_cli_successful_conversion(self, mock_converter_class, simple_xsd_file, temp_dir):
        """Test successful CLI conversion."""
        # Mock converter and its result
        mock_converter = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.output_files = [Path("output.json")]
        mock_result.processing_time = 1.5
        mock_result.errors = []

        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        result = self.runner.invoke(main, [
            '--input', str(simple_xsd_file),
            '--output', str(temp_dir / 'output')
        ])

        assert result.exit_code == 0
        assert "Conversion completed successfully" in result.output
        mock_converter_class.assert_called_once()
        mock_converter.convert.assert_called_once()

    @patch('src.xsd2json.cli.Converter')
    def test_cli_failed_conversion(self, mock_converter_class, simple_xsd_file):
        """Test failed CLI conversion."""
        # Mock converter with failed result
        mock_converter = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_result.errors = ["Conversion failed"]

        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        result = self.runner.invoke(main, [
            '--input', str(simple_xsd_file)
        ])

        assert result.exit_code == 1
        assert "Conversion failed" in result.output

    def test_cli_all_parameters(self, simple_xsd_file, temp_dir):
        """Test CLI with all parameters specified."""
        with patch('src.xsd2json.cli.Converter') as mock_converter_class:
            mock_converter = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.output_files = [Path("output.json")]
            mock_result.processing_time = 1.0
            mock_result.errors = []

            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            result = self.runner.invoke(main, [
                '--input', str(simple_xsd_file),
                '--output', str(temp_dir / 'output'),
                '--output-mode', 'MULTI',
                '--log-level', 'DEBUG',
                '--llm-optimized',
                '--simplify',
                '--add-metadata',
                '--flatten',
                '--natural-naming',
                '--embed-docs',
                '--diagnose',
                '--compact'
            ])

            assert result.exit_code == 0

            # Verify config was created correctly
            call_args = mock_converter_class.call_args[0][0]  # First positional arg (config)
            assert call_args.input_file == simple_xsd_file
            assert call_args.output_mode == OutputMode.MULTI
            assert call_args.logging.level == LogLevel.DEBUG
            assert call_args.llm_optimized
            assert call_args.llm.simplify
            assert call_args.llm.add_metadata
            assert call_args.llm.flatten
            assert call_args.llm.natural_naming
            assert call_args.llm.embed_docs
            assert call_args.diagnose
            assert not call_args.serializer.pretty

    def test_cli_llm_optimized_flag(self, simple_xsd_file):
        """Test CLI with --llm-optimized flag enables all optimizations."""
        with patch('src.xsd2json.cli.Converter') as mock_converter_class:
            mock_converter = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.output_files = []
            mock_result.processing_time = 1.0
            mock_result.errors = []

            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            result = self.runner.invoke(main, [
                '--input', str(simple_xsd_file),
                '--llm-optimized'
            ])

            assert result.exit_code == 0

            # Verify all LLM optimizations are enabled
            call_args = mock_converter_class.call_args[0][0]
            assert call_args.llm_optimized
            assert call_args.llm.simplify
            assert call_args.llm.add_metadata
            assert call_args.llm.flatten
            assert call_args.llm.natural_naming
            assert call_args.llm.embed_docs

    def test_cli_config_validation_errors(self, temp_dir):
        """Test CLI with configuration validation errors."""
        # Create XSD file in non-existent parent directory structure
        invalid_output_dir = temp_dir / "nonexistent" / "deeply" / "nested" / "output"

        with patch('src.xsd2json.cli.Config') as mock_config_class:
            mock_config = Mock()
            mock_config.validate.return_value = ["Configuration error"]

            mock_config_class.from_cli_args.return_value = mock_config

            result = self.runner.invoke(main, [
                '--input', 'test.xsd',
                '--output', str(invalid_output_dir)
            ])

            assert result.exit_code == 1
            assert "Configuration error" in result.output

    @patch('src.xsd2json.cli.Converter')
    def test_cli_keyboard_interrupt(self, mock_converter_class, simple_xsd_file):
        """Test CLI handling of keyboard interrupt."""
        mock_converter = Mock()
        mock_converter.convert.side_effect = KeyboardInterrupt()
        mock_converter_class.return_value = mock_converter

        result = self.runner.invoke(main, [
            '--input', str(simple_xsd_file)
        ])

        assert result.exit_code == 130
        assert "interrupted by user" in result.output

    @patch('src.xsd2json.cli.Converter')
    def test_cli_unexpected_exception(self, mock_converter_class, simple_xsd_file):
        """Test CLI handling of unexpected exceptions."""
        mock_converter = Mock()
        mock_converter.convert.side_effect = RuntimeError("Unexpected error")
        mock_converter_class.return_value = mock_converter

        result = self.runner.invoke(main, [
            '--input', str(simple_xsd_file)
        ])

        assert result.exit_code == 1
        assert "Unexpected error" in result.output

    @patch('src.xsd2json.cli.Converter')
    def test_cli_debug_mode_exception_traceback(self, mock_converter_class, simple_xsd_file):
        """Test CLI shows traceback in debug mode."""
        mock_converter = Mock()
        mock_converter.convert.side_effect = RuntimeError("Test error")
        mock_converter_class.return_value = mock_converter

        result = self.runner.invoke(main, [
            '--input', str(simple_xsd_file),
            '--log-level', 'DEBUG'
        ])

        assert result.exit_code == 1
        # In debug mode, we might see more detailed error info
        # but traceback printing depends on implementation

    def test_cli_default_output_directory(self, simple_xsd_file):
        """Test CLI uses default output directory when not specified."""
        with patch('src.xsd2json.cli.Converter') as mock_converter_class:
            mock_converter = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.output_files = []
            mock_result.processing_time = 1.0
            mock_result.errors = []

            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter

            result = self.runner.invoke(main, [
                '--input', str(simple_xsd_file)
            ])

            assert result.exit_code == 0

            # Verify default output directory is used
            call_args = mock_converter_class.call_args[0][0]
            assert call_args.output_dir == Path("./output")