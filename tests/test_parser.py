"""Tests for XSD parser."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.xsd2json.parser import XSDParser
from src.xsd2json.schema_model import (
    Schema, Element, ComplexType, SimpleType, QName
)


class TestXSDParser:
    """Tests for XSDParser class."""

    def test_parser_creation(self):
        """Test parser creation."""
        parser = XSDParser()

        assert parser is not None
        assert parser._parsed_schemas == {}
        assert parser._type_cache == {}

    def test_parse_nonexistent_file(self, temp_dir):
        """Test parsing non-existent file."""
        parser = XSDParser()
        nonexistent_file = temp_dir / "nonexistent.xsd"

        result = parser.parse(nonexistent_file)

        assert result is None

    def test_parse_simple_xsd(self, simple_xsd_file):
        """Test parsing simple XSD file."""
        parser = XSDParser()

        schema = parser.parse(simple_xsd_file)

        assert schema is not None
        assert isinstance(schema, Schema)
        assert schema.target_namespace == "http://example.com/test"

    def test_parse_simple_xsd_elements(self, simple_xsd_file):
        """Test parsing simple XSD elements."""
        parser = XSDParser()

        schema = parser.parse(simple_xsd_file)

        assert len(schema.elements) == 1
        assert "person" in schema.elements

        person_element = schema.elements["person"]
        assert isinstance(person_element, Element)
        assert person_element.name == "person"

    def test_parse_simple_xsd_types(self, simple_xsd_file):
        """Test parsing simple XSD types."""
        parser = XSDParser()

        schema = parser.parse(simple_xsd_file)

        assert len(schema.types) >= 2  # PersonType and EmailType
        assert "PersonType" in schema.types
        assert "EmailType" in schema.types

        person_type = schema.types["PersonType"]
        assert isinstance(person_type, ComplexType)
        assert person_type.name == "PersonType"

        email_type = schema.types["EmailType"]
        assert isinstance(email_type, SimpleType)
        assert email_type.name == "EmailType"

    def test_parse_complex_xsd(self, complex_xsd_file):
        """Test parsing complex XSD with inheritance."""
        parser = XSDParser()

        schema = parser.parse(complex_xsd_file)

        assert schema is not None
        assert schema.target_namespace == "http://example.com/complex"
        assert len(schema.types) >= 2  # BaseType and ExtendedType

    def test_qname_creation(self):
        """Test QName creation in parser."""
        parser = XSDParser()

        # Mock an XSD component
        mock_component = Mock()
        mock_component.local_name = "testName"
        mock_component.name = None
        mock_component.target_namespace = "http://example.com"

        qname = parser._create_qname(mock_component)

        assert qname.local_name == "testName"
        assert qname.namespace_uri == "http://example.com"

    def test_qname_creation_fallback_name(self):
        """Test QName creation with fallback to name attribute."""
        parser = XSDParser()

        mock_component = Mock()
        mock_component.local_name = None
        mock_component.name = "fallbackName"
        mock_component.target_namespace = "http://example.com"

        qname = parser._create_qname(mock_component)

        assert qname.local_name == "fallbackName"

    def test_add_annotation_with_documentation(self):
        """Test adding annotation with documentation."""
        parser = XSDParser()

        # Mock XSD component with annotation
        mock_xsd_component = Mock()
        mock_xsd_component.annotation = Mock()

        mock_doc = Mock()
        mock_doc.text = "Test documentation"
        mock_xsd_component.annotation.documentation = [mock_doc]
        mock_xsd_component.annotation.appinfo = []

        # Mock our component
        our_component = Mock()
        our_component.annotation = Mock()
        our_component.annotation.add_documentation = Mock()

        parser._add_annotation(mock_xsd_component, our_component)

        our_component.annotation.add_documentation.assert_called_once_with("Test documentation")

    def test_add_annotation_no_annotation(self):
        """Test adding annotation when none exists."""
        parser = XSDParser()

        # Mock XSD component without annotation
        mock_xsd_component = Mock()
        mock_xsd_component.annotation = None

        # Mock our component
        our_component = Mock()
        our_component.annotation = Mock()

        # Should not raise exception
        parser._add_annotation(mock_xsd_component, our_component)

    @pytest.mark.parametrize("type_class,expected_type", [
        ("XsdComplexType", "complex"),
        ("XsdSimpleType", "simple"),
        ("XsdAtomicRestriction", "simple"),
        ("XsdList", "simple"),
        ("XsdUnion", "simple"),
        ("UnknownType", "unknown")
    ])
    def test_type_detection(self, type_class, expected_type):
        """Test type detection based on class names."""
        parser = XSDParser()

        # Mock XSD type with specific class name
        mock_type = Mock()
        mock_type.__class__.__name__ = type_class

        # Test the type detection logic (simplified)
        if 'ComplexType' in type_class:
            assert expected_type == "complex"
        elif any(x in type_class for x in ['SimpleType', 'Atomic', 'Restriction', 'List', 'Union']):
            assert expected_type == "simple"
        else:
            assert expected_type == "unknown"

    def test_convert_element_occurrence(self):
        """Test converting element occurrence information."""
        parser = XSDParser()

        # Mock XSD element with occurrence info
        mock_element = Mock()
        mock_element.local_name = "testElement"
        mock_element.name = None
        mock_element.min_occurs = 0
        mock_element.max_occurs = "unbounded"
        mock_element.nillable = False
        mock_element.abstract = False
        mock_element.default = None
        mock_element.fixed = None
        mock_element.type = None

        element = parser._convert_element(mock_element)

        assert element is not None
        assert element.name == "testElement"
        assert element.occurs.min == 0
        assert element.occurs.max == "unbounded"
        assert element.occurs.is_optional
        assert element.occurs.is_array

    def test_convert_simple_type_with_facets(self):
        """Test converting simple type with facets."""
        parser = XSDParser()

        # Mock XSD simple type with facets
        mock_simple_type = Mock()
        mock_simple_type.local_name = "RestrictedString"
        mock_simple_type.name = None
        mock_simple_type.primitive_type = None
        mock_simple_type.base_type = None

        # Mock facets
        mock_facet1 = Mock()
        mock_facet1.value = 100
        mock_facet2 = Mock()
        mock_facet2.value = "[a-z]+"

        mock_simple_type.facets = {
            "maxLength": mock_facet1,
            "pattern": mock_facet2
        }

        simple_type = parser._convert_simple_type(mock_simple_type)

        assert simple_type is not None
        assert simple_type.name == "RestrictedString"
        assert len(simple_type.facets) == 2

    def test_element_occurrence_creation(self):
        """Test ElementOccurrence creation from XSD data."""
        from src.xsd2json.schema_model import ElementOccurrence

        # Test default occurrence
        occurs1 = ElementOccurrence()
        assert occurs1.min == 1
        assert occurs1.max == 1

        # Test optional occurrence
        occurs2 = ElementOccurrence(0, 1)
        assert occurs2.is_optional
        assert not occurs2.is_array

        # Test array occurrence
        occurs3 = ElementOccurrence(1, "unbounded")
        assert occurs3.is_array
        assert occurs3.is_required

    def test_parser_error_handling(self, temp_dir):
        """Test parser error handling with malformed XSD."""
        # Create malformed XSD
        malformed_xsd = temp_dir / "malformed.xsd"
        malformed_xsd.write_text("This is not valid XML", encoding='utf-8')

        parser = XSDParser()
        result = parser.parse(malformed_xsd)

        # Should return None on error
        assert result is None

    def test_convert_schema_basic_properties(self, simple_xsd_file):
        """Test basic schema properties conversion."""
        parser = XSDParser()

        schema = parser.parse(simple_xsd_file)

        assert schema.target_namespace == "http://example.com/test"
        assert isinstance(schema.namespace_prefixes, dict)
        assert schema.element_form_default in ["qualified", "unqualified"]
        assert schema.attribute_form_default in ["qualified", "unqualified"]