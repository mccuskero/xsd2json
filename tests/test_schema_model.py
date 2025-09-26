"""Tests for schema model classes."""

import pytest
from src.xsd2json.schema_model import (
    Schema, Element, Attribute, SimpleType, ComplexType,
    QName, ElementOccurrence, AttributeUse, DerivationMethod,
    ContentType, Annotation, Facet, Sequence, Choice, All
)


class TestQName:
    """Tests for QName class."""

    def test_qname_creation(self):
        """Test QName creation with different parameters."""
        qname = QName("localName")
        assert qname.local_name == "localName"
        assert qname.namespace_uri is None
        assert qname.prefix is None

    def test_qname_with_namespace(self):
        """Test QName with namespace."""
        qname = QName("localName", "http://example.com", "ex")
        assert qname.local_name == "localName"
        assert qname.namespace_uri == "http://example.com"
        assert qname.prefix == "ex"

    def test_expanded_name(self):
        """Test expanded name generation."""
        qname = QName("localName", "http://example.com")
        assert qname.expanded_name == "{http://example.com}localName"

        qname_no_ns = QName("localName")
        assert qname_no_ns.expanded_name == "localName"

    def test_qname_string_representation(self):
        """Test QName string representation."""
        qname = QName("localName", "http://example.com", "ex")
        assert str(qname) == "ex:localName"

        qname_no_prefix = QName("localName", "http://example.com")
        assert str(qname_no_prefix) == "localName"


class TestElementOccurrence:
    """Tests for ElementOccurrence class."""

    def test_default_occurrence(self):
        """Test default occurrence (1..1)."""
        occurs = ElementOccurrence()
        assert occurs.min == 1
        assert occurs.max == 1
        assert not occurs.is_optional
        assert not occurs.is_array
        assert occurs.is_required

    def test_optional_occurrence(self):
        """Test optional occurrence (0..1)."""
        occurs = ElementOccurrence(0, 1)
        assert occurs.min == 0
        assert occurs.max == 1
        assert occurs.is_optional
        assert not occurs.is_array
        assert not occurs.is_required

    def test_array_occurrence(self):
        """Test array occurrence (1..unbounded)."""
        occurs = ElementOccurrence(1, "unbounded")
        assert occurs.min == 1
        assert occurs.max == "unbounded"
        assert not occurs.is_optional
        assert occurs.is_array
        assert occurs.is_required

    def test_occurrence_string_representation(self):
        """Test string representation of occurrence."""
        occurs = ElementOccurrence(0, "unbounded")
        assert str(occurs) == "[0..unbounded]"


class TestAnnotation:
    """Tests for Annotation class."""

    def test_empty_annotation(self):
        """Test empty annotation creation."""
        annotation = Annotation()
        assert annotation.documentation == []
        assert annotation.appinfo == []

    def test_add_documentation(self):
        """Test adding documentation."""
        annotation = Annotation()
        annotation.add_documentation("Test documentation")
        annotation.add_documentation("  Another doc  ")

        assert len(annotation.documentation) == 2
        assert annotation.documentation[0] == "Test documentation"
        assert annotation.documentation[1] == "Another doc"

    def test_add_empty_documentation(self):
        """Test adding empty documentation is ignored."""
        annotation = Annotation()
        annotation.add_documentation("")
        annotation.add_documentation("   ")

        assert annotation.documentation == []

    def test_add_appinfo(self):
        """Test adding appinfo."""
        annotation = Annotation()
        info = {"source": "test", "content": "value"}
        annotation.add_appinfo(info)

        assert len(annotation.appinfo) == 1
        assert annotation.appinfo[0] == info


class TestSimpleType:
    """Tests for SimpleType class."""

    def test_simple_type_creation(self):
        """Test simple type creation."""
        simple_type = SimpleType("StringType")
        assert simple_type.name == "StringType"
        assert simple_type.variety == "atomic"
        assert not simple_type.is_derived
        assert simple_type.derivation_chain == [simple_type]

    def test_add_facet(self):
        """Test adding facets to simple type."""
        simple_type = SimpleType("RestrictedString")
        simple_type.add_facet("maxLength", 100)
        simple_type.add_facet("pattern", "[a-z]+")

        assert len(simple_type.facets) == 2
        assert simple_type.facets[0].name == "maxLength"
        assert simple_type.facets[0].value == 100

    def test_enumeration_facet(self):
        """Test enumeration facet handling."""
        simple_type = SimpleType("ColorType")
        simple_type.add_facet("enumeration", "red")
        simple_type.add_facet("enumeration", "green")
        simple_type.add_facet("enumeration", "blue")

        assert len(simple_type.enumeration_values) == 3
        assert "red" in simple_type.enumeration_values

    def test_union_variety(self):
        """Test union type variety."""
        union_type = SimpleType("UnionType")
        member1 = SimpleType("StringType")
        member2 = SimpleType("IntType")
        union_type.union_member_types = [member1, member2]

        assert union_type.variety == "union"

    def test_list_variety(self):
        """Test list type variety."""
        list_type = SimpleType("ListType")
        item_type = SimpleType("StringType")
        list_type.list_item_type = item_type

        assert list_type.variety == "list"


class TestComplexType:
    """Tests for ComplexType class."""

    def test_complex_type_creation(self):
        """Test complex type creation."""
        complex_type = ComplexType("PersonType")
        assert complex_type.name == "PersonType"
        assert complex_type.content_type == ContentType.ELEMENT_ONLY
        assert not complex_type.abstract
        assert not complex_type.mixed

    def test_add_attribute(self):
        """Test adding attributes to complex type."""
        complex_type = ComplexType("PersonType")
        attr = Attribute("id")
        attr.use = AttributeUse.REQUIRED

        complex_type.add_attribute(attr)
        assert len(complex_type.attributes) == 1
        assert complex_type.attributes[0] == attr

    def test_get_all_attributes(self):
        """Test getting all attributes including from groups."""
        complex_type = ComplexType("PersonType")

        # Direct attribute
        attr1 = Attribute("id")
        complex_type.add_attribute(attr1)

        # This test would need AttributeGroup implementation
        # For now, just test direct attributes
        all_attrs = complex_type.get_all_attributes()
        assert len(all_attrs) == 1
        assert all_attrs[0] == attr1


class TestElement:
    """Tests for Element class."""

    def test_element_creation(self):
        """Test element creation."""
        element = Element("person")
        assert element.name == "person"
        assert not element.nillable
        assert not element.abstract
        assert element.occurs.min == 1
        assert element.occurs.max == 1

    def test_element_with_type(self):
        """Test element with type reference."""
        element = Element("person")
        person_type = ComplexType("PersonType")
        element.type = person_type

        assert element.type == person_type


class TestAttribute:
    """Tests for Attribute class."""

    def test_attribute_creation(self):
        """Test attribute creation."""
        attr = Attribute("id")
        assert attr.name == "id"
        assert attr.use == AttributeUse.OPTIONAL
        assert not attr.is_required

    def test_required_attribute(self):
        """Test required attribute."""
        attr = Attribute("id")
        attr.use = AttributeUse.REQUIRED
        assert attr.is_required


class TestModelGroups:
    """Tests for model group classes."""

    def test_sequence_creation(self):
        """Test sequence creation."""
        sequence = Sequence()
        assert sequence.particles == []

        element = Element("test")
        sequence.add_particle(element)
        assert len(sequence.particles) == 1

    def test_choice_creation(self):
        """Test choice creation."""
        choice = Choice()
        assert choice.particles == []

        element1 = Element("option1")
        element2 = Element("option2")
        choice.add_particle(element1)
        choice.add_particle(element2)
        assert len(choice.particles) == 2

    def test_all_creation(self):
        """Test all group creation."""
        all_group = All()
        assert all_group.particles == []


class TestSchema:
    """Tests for Schema class."""

    def test_schema_creation(self):
        """Test schema creation."""
        schema = Schema("http://example.com/test")
        assert schema.target_namespace == "http://example.com/test"
        assert schema.elements == {}
        assert schema.types == {}

    def test_add_element(self):
        """Test adding elements to schema."""
        schema = Schema()
        element = Element("person")
        schema.add_element(element)

        assert "person" in schema.elements
        assert schema.elements["person"] == element

    def test_add_type(self):
        """Test adding types to schema."""
        schema = Schema()
        complex_type = ComplexType("PersonType")
        schema.add_type(complex_type)

        assert "PersonType" in schema.types
        assert schema.types["PersonType"] == complex_type

    def test_get_complex_types(self):
        """Test getting all complex types."""
        schema = Schema()
        complex_type = ComplexType("PersonType")
        simple_type = SimpleType("EmailType")

        schema.add_type(complex_type)
        schema.add_type(simple_type)

        complex_types = schema.get_all_complex_types()
        assert len(complex_types) == 1
        assert complex_types[0] == complex_type

    def test_get_simple_types(self):
        """Test getting all simple types."""
        schema = Schema()
        complex_type = ComplexType("PersonType")
        simple_type = SimpleType("EmailType")

        schema.add_type(complex_type)
        schema.add_type(simple_type)

        simple_types = schema.get_all_simple_types()
        assert len(simple_types) == 1
        assert simple_types[0] == simple_type


class TestFacet:
    """Tests for Facet class."""

    def test_facet_creation(self):
        """Test facet creation."""
        facet = Facet("maxLength", 100)
        assert facet.name == "maxLength"
        assert facet.value == 100
        assert not facet.fixed

    def test_fixed_facet(self):
        """Test fixed facet."""
        facet = Facet("pattern", "[a-z]+", fixed=True)
        assert facet.fixed