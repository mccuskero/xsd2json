"""Tests for converter system."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.xsd2json.converter import Converter, ConversionResult
from src.xsd2json.config import Config, OutputMode
from src.xsd2json.schema_model import Schema, ComplexType, SimpleType, Element


class TestConversionResult:
    """Tests for ConversionResult dataclass."""

    def test_conversion_result_creation(self):
        """Test ConversionResult creation."""
        result = ConversionResult(
            success=True,
            output_files=[Path("test.json")],
            processing_time=1.5,
            errors=[],
            warnings=["Warning message"],
            statistics={"types": 5}
        )

        assert result.success
        assert len(result.output_files) == 1
        assert result.processing_time == 1.5
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert result.statistics["types"] == 5


class TestConverter:
    """Tests for Converter class."""

    def test_converter_creation(self, default_config):
        """Test converter creation with configuration."""
        converter = Converter(default_config)

        assert converter.config == default_config
        assert converter.parser is not None
        assert converter.logger is not None

    def test_converter_initialization_logging(self, default_config):
        """Test converter logs initialization."""
        with patch.object(default_config, 'logging') as mock_logging:
            mock_logging.level.value = "info"

            converter = Converter(default_config)

            assert converter is not None

    def test_convert_nonexistent_file(self, default_config, temp_dir):
        """Test converting non-existent file."""
        default_config.input_file = temp_dir / "nonexistent.xsd"
        converter = Converter(default_config)

        result = converter.convert()

        assert not result.success
        assert len(result.errors) > 0
        assert "does not exist" in result.errors[0]

    def test_convert_simple_xsd_single_mode(self, simple_xsd_file, temp_dir):
        """Test converting simple XSD in single file mode."""
        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output",
            output_mode=OutputMode.SINGLE
        )
        converter = Converter(config)

        result = converter.convert()

        assert result.success
        assert len(result.output_files) == 1
        assert result.processing_time > 0

        # Check output file exists
        output_file = result.output_files[0]
        assert output_file.exists()
        assert output_file.suffix == ".json"

    def test_convert_simple_xsd_content_validation(self, simple_xsd_file, temp_dir):
        """Test converting simple XSD and validate content."""
        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output",
            output_mode=OutputMode.SINGLE
        )
        converter = Converter(config)

        result = converter.convert()

        assert result.success

        # Read and validate JSON content
        output_file = result.output_files[0]
        with open(output_file, 'r', encoding='utf-8') as f:
            json_content = json.load(f)

        assert json_content["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "definitions" in json_content
        assert "PersonType" in json_content["definitions"]
        assert "EmailType" in json_content["definitions"]

    def test_convert_with_llm_optimizations(self, simple_xsd_file, temp_dir):
        """Test converting with LLM optimizations enabled."""
        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output",
            output_mode=OutputMode.SINGLE
        )
        config.enable_all_llm_optimizations()
        converter = Converter(config)

        result = converter.convert()

        assert result.success
        assert len(result.output_files) == 1

    def test_transform_to_json_empty_schema(self, default_config):
        """Test transforming empty schema to JSON."""
        converter = Converter(default_config)
        empty_schema = Schema("http://example.com/empty")

        json_schemas = converter._transform_to_json(empty_schema)

        assert len(json_schemas) == 1
        assert json_schemas[0]["$id"] == "http://example.com/empty"

    def test_transform_to_json_with_types(self, default_config):
        """Test transforming schema with types to JSON."""
        converter = Converter(default_config)

        schema = Schema("http://example.com/test")

        # Add a complex type
        complex_type = ComplexType("PersonType")
        complex_type.annotation.add_documentation("A person type")
        schema.add_type(complex_type)

        # Add a simple type
        simple_type = SimpleType("EmailType")
        simple_type.annotation.add_documentation("Email type")
        schema.add_type(simple_type)

        json_schemas = converter._transform_to_json(schema)

        # Should have schemas for both types plus element if any
        assert len(json_schemas) >= 2

        # Find PersonType schema
        person_schema = next(
            (s for s in json_schemas if "PersonType" in s.get("title", "")),
            None
        )
        assert person_schema is not None
        assert person_schema["type"] == "object"
        assert "A person type" in person_schema["description"]

    def test_generate_single_file_output_one_schema(self, default_config, temp_dir):
        """Test generating single file output with one schema."""
        default_config.output_dir = temp_dir
        converter = Converter(default_config)

        test_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "http://example.com/test",
            "title": "Test Schema",
            "type": "object"
        }

        output_files = converter._generate_single_file_output([test_schema])

        assert len(output_files) == 1
        output_file = output_files[0]
        assert output_file.exists()

        with open(output_file, 'r', encoding='utf-8') as f:
            content = json.load(f)

        assert content == test_schema

    def test_generate_single_file_output_multiple_schemas(self, default_config, temp_dir):
        """Test generating single file output with multiple schemas."""
        default_config.output_dir = temp_dir
        converter = Converter(default_config)

        test_schemas = [
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "http://example.com/type1",
                "title": "Generated JSON Schema for Type1",
                "type": "object"
            },
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "http://example.com/type2",
                "title": "Generated JSON Schema for Type2",
                "type": "string"
            }
        ]

        output_files = converter._generate_single_file_output(test_schemas)

        assert len(output_files) == 1
        output_file = output_files[0]

        with open(output_file, 'r', encoding='utf-8') as f:
            content = json.load(f)

        assert "definitions" in content
        assert "Type1" in content["definitions"]
        assert "Type2" in content["definitions"]
        assert content["properties"]["Type1"]["$ref"] == "#/definitions/Type1"

    def test_extract_properties_from_particle(self, default_config):
        """Test extracting properties from particle."""
        converter = Converter(default_config)

        # Mock particle with particles
        mock_particle = Mock()
        mock_child1 = Mock()
        mock_child1.name = "element1"
        mock_child1.occurs = Mock()
        mock_child1.occurs.is_array = False

        mock_child2 = Mock()
        mock_child2.name = "element2"
        mock_child2.occurs = Mock()
        mock_child2.occurs.is_array = True

        mock_particle.particles = [mock_child1, mock_child2]

        properties = converter._extract_properties_from_particle(mock_particle)

        assert "element1" in properties
        assert "element2" in properties
        assert properties["element1"]["type"] == "string"
        assert properties["element2"]["type"] == "array"

    def test_apply_llm_optimizations(self, default_config):
        """Test applying LLM optimizations."""
        default_config.llm_optimized = True
        default_config.llm.simplify = True
        default_config.llm.add_metadata = True
        converter = Converter(default_config)

        test_schemas = [{
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "http://example.com/test",
            "type": "object"
        }]

        # Should not raise exception
        optimized_schemas = converter._apply_llm_optimizations(test_schemas)

        assert len(optimized_schemas) == len(test_schemas)

    def test_create_result_helper(self, default_config):
        """Test _create_result helper method."""
        converter = Converter(default_config)

        result = converter._create_result(
            success=True,
            output_files=[Path("test.json")],
            processing_time=1.0,
            errors=[],
            warnings=["test warning"],
            statistics={"count": 1}
        )

        assert isinstance(result, ConversionResult)
        assert result.success
        assert len(result.output_files) == 1
        assert result.processing_time == 1.0
        assert len(result.warnings) == 1
        assert result.statistics["count"] == 1

    def test_converter_error_handling(self, default_config, temp_dir):
        """Test converter error handling."""
        # Create invalid XSD file
        invalid_xsd = temp_dir / "invalid.xsd"
        invalid_xsd.write_text("invalid xml content", encoding='utf-8')

        default_config.input_file = invalid_xsd
        default_config.output_dir = temp_dir / "output"
        converter = Converter(default_config)

        result = converter.convert()

        assert not result.success
        assert len(result.errors) > 0

    def test_statistics_collection(self, simple_xsd_file, temp_dir):
        """Test statistics collection during conversion."""
        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output",
            output_mode=OutputMode.SINGLE
        )
        converter = Converter(config)

        result = converter.convert()

        assert result.success
        assert "complexTypes" in result.statistics
        assert "simpleTypes" in result.statistics
        assert "outputFiles" in result.statistics
        assert result.statistics["outputFiles"] == len(result.output_files)

    @patch('src.xsd2json.converter.time.time')
    def test_processing_time_measurement(self, mock_time, simple_xsd_file, temp_dir):
        """Test processing time measurement."""
        # Mock time.time() to return specific values
        mock_time.side_effect = [0.0, 2.5]  # start and end times

        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output"
        )
        converter = Converter(config)

        result = converter.convert()

        assert result.processing_time == 2.5

    def test_convert_simple_xsd_multi_mode(self, simple_xsd_file, temp_dir):
        """Test converting simple XSD in multi-file mode."""
        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output",
            output_mode=OutputMode.MULTI
        )
        converter = Converter(config)

        result = converter.convert()

        assert result.success
        assert len(result.output_files) >= 3  # Master, types, README
        assert result.processing_time > 0

        # Check that master schema file exists
        master_file = temp_dir / "output" / "schema.json"
        assert master_file.exists()

        # Check that types directory exists
        types_dir = temp_dir / "output" / "types"
        assert types_dir.exists()

        # Check that README exists
        readme_file = temp_dir / "output" / "README.md"
        assert readme_file.exists()

        # Validate master schema content
        with open(master_file, 'r', encoding='utf-8') as f:
            master_content = json.load(f)

        assert master_content["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert master_content["$id"] == "http://example.com/master"
        assert "properties" in master_content
        assert "PersonType" in master_content["properties"]
        assert "EmailType" in master_content["properties"]
        assert master_content["properties"]["PersonType"]["$ref"] == "types/person-type.json"

        # Validate individual type files exist
        person_type_file = types_dir / "person-type.json"
        email_type_file = types_dir / "email-type.json"
        assert person_type_file.exists()
        assert email_type_file.exists()

        # Validate individual type file content
        with open(person_type_file, 'r', encoding='utf-8') as f:
            person_content = json.load(f)

        assert person_content["$id"] == "http://example.com/types/PersonType"
        assert person_content["type"] == "object"
        assert "properties" in person_content

    def test_multi_file_readme_generation(self, simple_xsd_file, temp_dir):
        """Test README generation in multi-file mode."""
        config = Config(
            input_file=simple_xsd_file,
            output_dir=temp_dir / "output",
            output_mode=OutputMode.MULTI
        )
        converter = Converter(config)

        result = converter.convert()

        readme_file = temp_dir / "output" / "README.md"
        assert readme_file.exists()

        readme_content = readme_file.read_text(encoding='utf-8')
        assert "# JSON Schema Files" in readme_content
        assert "PersonType" in readme_content
        assert "EmailType" in readme_content
        assert "types/person-type.json" in readme_content
        assert "types/email-type.json" in readme_content
        assert "Generated by" in readme_content

    def test_extract_type_name(self, default_config):
        """Test type name extraction."""
        converter = Converter(default_config)

        # Test with title containing "Generated JSON Schema for"
        schema1 = {"title": "Generated JSON Schema for PersonType"}
        assert converter._extract_type_name(schema1) == "PersonType"

        # Test with $id
        schema2 = {"$id": "http://example.com/types/EmailType"}
        assert converter._extract_type_name(schema2) == "EmailType"

        # Test fallback
        schema3 = {}
        assert converter._extract_type_name(schema3) == "UnknownType"

    def test_sanitize_filename(self, default_config):
        """Test filename sanitization."""
        converter = Converter(default_config)

        assert converter._sanitize_filename("PersonType") == "person-type"
        assert converter._sanitize_filename("XMLHttpRequest") == "xmlhttp-request"
        assert converter._sanitize_filename("Simple Name") == "simple-name"
        assert converter._sanitize_filename("Complex_Name-123") == "complex-name-123"
        assert converter._sanitize_filename("Multiple---Hyphens") == "multiple-hyphens"

    def test_inheritance_handling(self, temp_dir):
        """Test inheritance (extension/restriction) handling."""
        # Create XSD with inheritance
        inheritance_xsd = temp_dir / "inheritance.xsd"
        inheritance_content = '''<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://example.com/inheritance"
           xmlns:tns="http://example.com/inheritance">

    <xs:complexType name="BaseType">
        <xs:sequence>
            <xs:element name="id" type="xs:string"/>
        </xs:sequence>
        <xs:attribute name="version" type="xs:string"/>
    </xs:complexType>

    <xs:complexType name="ExtendedType">
        <xs:complexContent>
            <xs:extension base="tns:BaseType">
                <xs:sequence>
                    <xs:element name="name" type="xs:string"/>
                </xs:sequence>
                <xs:attribute name="priority" type="xs:int"/>
            </xs:extension>
        </xs:complexContent>
    </xs:complexType>

</xs:schema>'''
        inheritance_xsd.write_text(inheritance_content, encoding='utf-8')

        config = Config(
            input_file=inheritance_xsd,
            output_dir=temp_dir / "output"
        )
        converter = Converter(config)

        result = converter.convert()

        assert result.success
        output_file = result.output_files[0]
        with open(output_file, 'r', encoding='utf-8') as f:
            content = json.load(f)

        # Check base type
        base_type = content["definitions"]["BaseType"]
        assert base_type["type"] == "object"
        assert "@version" in base_type["properties"]

        # Check extended type
        extended_type = content["definitions"]["ExtendedType"]
        assert "allOf" in extended_type
        assert extended_type["allOf"][0]["$ref"] == "#/definitions/BaseType"
        assert extended_type["x-inheritance"]["type"] == "extension"
        assert extended_type["x-inheritance"]["baseType"] == "BaseType"

        # Check that only additional attributes are in extended type
        extended_props = extended_type["allOf"][1]["properties"]
        assert "@priority" in extended_props
        assert "@version" not in extended_props  # Should not duplicate base attributes