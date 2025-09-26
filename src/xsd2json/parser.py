"""XSD parser using xmlschema library with object-oriented model conversion."""

from pathlib import Path
from typing import Dict, List, Optional, Set, Union, Any
from urllib.parse import urljoin, urlparse
import xmlschema
# Import what's available and use hasattr checks for the rest
try:
    from xmlschema.validators import XsdElement, XsdComplexType, XsdSimpleType, XsdAttribute
except ImportError:
    # Fallback for different xmlschema versions
    XsdElement = XsdComplexType = XsdSimpleType = XsdAttribute = None

from .logger import create_logger
from .schema_model import (
    Schema, Element, Attribute, SimpleType, ComplexType, Type,
    ModelGroup, Sequence, Choice, All, Group, AttributeGroup,
    Any, AnyAttribute, IdentityConstraint, Particle,
    QName, ElementOccurrence, AttributeUse, DerivationMethod,
    ContentType, Annotation, Facet
)


class XSDParser:
    """Parser for XSD files using xmlschema library."""

    def __init__(self):
        self.logger = create_logger(component="parser")
        self._parsed_schemas: Dict[str, Schema] = {}
        self._type_cache: Dict[str, Type] = {}

    def parse(self, xsd_path: Union[str, Path]) -> Optional[Schema]:
        """Parse XSD file and return schema model."""
        try:
            xsd_path = Path(xsd_path)
            self.logger.info("Starting XSD parsing", xsdFile=str(xsd_path))

            if not xsd_path.exists():
                self.logger.error("XSD file does not exist", xsdFile=str(xsd_path))
                return None

            # Use xmlschema to parse the XSD
            xmlschema_obj = xmlschema.XMLSchema(str(xsd_path))
            self.logger.info("XSD parsed by xmlschema", targetNamespace=xmlschema_obj.target_namespace)

            # Convert to our object model
            schema = self._convert_schema(xmlschema_obj, str(xsd_path))

            if schema:
                self.logger.info(
                    "Schema conversion completed",
                    elements=len(schema.elements),
                    types=len(schema.types),
                    complexTypes=len(schema.get_all_complex_types()),
                    simpleTypes=len(schema.get_all_simple_types())
                )

            return schema

        except xmlschema.XMLSchemaException as e:
            self.logger.error("XMLSchema parsing error", error=str(e), errorType=type(e).__name__)
            return None
        except Exception as e:
            self.logger.error("Unexpected parsing error", error=str(e), errorType=type(e).__name__)
            return None

    def _convert_schema(self, xmlschema_obj: xmlschema.XMLSchema, source_path: str) -> Schema:
        """Convert xmlschema object to our Schema model."""
        schema = Schema(target_namespace=xmlschema_obj.target_namespace)
        schema.namespace_prefixes = dict(xmlschema_obj.namespaces)
        schema.element_form_default = xmlschema_obj.element_form_default
        schema.attribute_form_default = xmlschema_obj.attribute_form_default

        self.logger.debug("Converting schema components", targetNamespace=schema.target_namespace)

        # Convert types first (needed for element references)
        self._convert_types(xmlschema_obj, schema)

        # Convert top-level elements
        self._convert_elements(xmlschema_obj, schema)

        # Convert top-level attributes
        self._convert_attributes(xmlschema_obj, schema)

        # Convert groups
        self._convert_groups(xmlschema_obj, schema)

        # Convert attribute groups
        self._convert_attribute_groups(xmlschema_obj, schema)

        # Handle imports and includes
        self._handle_imports_includes(xmlschema_obj, schema)

        return schema

    def _convert_types(self, xmlschema_obj: xmlschema.XMLSchema, schema: Schema) -> None:
        """Convert all type definitions."""
        for name, xsd_type in xmlschema_obj.types.items():
            type_class_name = type(xsd_type).__name__

            # Use class name to determine type
            if 'ComplexType' in type_class_name:
                # This is a complex type
                complex_type = self._convert_complex_type(xsd_type)
                if complex_type:
                    schema.add_type(complex_type)
                    self._type_cache[name] = complex_type
                    self.logger.debug("Converted complex type", typeName=name)
                else:
                    self.logger.warn("Failed to convert complex type", typeName=name)
            elif any(x in type_class_name for x in ['SimpleType', 'Atomic', 'Restriction', 'List', 'Union']):
                # This is a simple type
                simple_type = self._convert_simple_type(xsd_type)
                if simple_type:
                    schema.add_type(simple_type)
                    self._type_cache[name] = simple_type
                    self.logger.debug("Converted simple type", typeName=name)
                else:
                    self.logger.warn("Failed to convert simple type", typeName=name)
            else:
                # Generic type handling
                self.logger.debug(
                    "Unknown type structure",
                    typeName=name,
                    typeClass=type_class_name,
                    hasContentType=hasattr(xsd_type, 'content_type'),
                    hasPythonType=hasattr(xsd_type, 'python_type'),
                    attributes=sorted([attr for attr in dir(xsd_type) if not attr.startswith('_')])[:10]
                )

        self.logger.debug("Converted types", count=len(schema.types), typeNames=list(schema.types.keys()))

    def _convert_simple_type(self, xsd_simple_type) -> Optional[SimpleType]:
        """Convert XSD simple type to our model."""
        try:
            name = xsd_simple_type.local_name or xsd_simple_type.name
            if not name:
                return None

            qname = self._create_qname(xsd_simple_type)
            simple_type = SimpleType(name, qname)

            # Set primitive type
            if hasattr(xsd_simple_type, 'primitive_type') and xsd_simple_type.primitive_type:
                simple_type.primitive_type = xsd_simple_type.primitive_type.local_name

            # Handle derivation
            if hasattr(xsd_simple_type, 'base_type') and xsd_simple_type.base_type:
                base_type = self._get_or_create_type_reference(xsd_simple_type.base_type)
                if base_type:
                    simple_type.base_type = base_type
                    simple_type.derivation_method = DerivationMethod.RESTRICTION

            # Convert facets
            if hasattr(xsd_simple_type, 'facets'):
                for facet_name, facet_obj in xsd_simple_type.facets.items():
                    # Handle enumeration facets specially
                    if 'enumeration' in facet_name.lower() and hasattr(facet_obj, 'enumeration'):
                        # XsdEnumerationFacets stores the actual values in the 'enumeration' attribute
                        simple_type.add_facet('enumeration', facet_obj.enumeration)
                    elif hasattr(facet_obj, 'value') and facet_obj.value is not None:
                        simple_type.add_facet(facet_name, facet_obj.value)

            # Handle union types
            if hasattr(xsd_simple_type, 'member_types'):
                for member_type in xsd_simple_type.member_types:
                    member_simple_type = self._convert_simple_type(member_type)
                    if member_simple_type:
                        simple_type.union_member_types.append(member_simple_type)

            # Handle list types
            if hasattr(xsd_simple_type, 'item_type') and xsd_simple_type.item_type:
                item_type = self._convert_simple_type(xsd_simple_type.item_type)
                if item_type:
                    simple_type.list_item_type = item_type

            # Add annotation
            self._add_annotation(xsd_simple_type, simple_type)

            return simple_type

        except Exception as e:
            import traceback
            self.logger.error(
                "Error converting simple type",
                typeName=getattr(xsd_simple_type, 'name', 'unknown'),
                error=str(e),
                traceback=traceback.format_exc()
            )
            return None

    def _convert_complex_type(self, xsd_complex_type) -> Optional[ComplexType]:
        """Convert XSD complex type to our model."""
        try:
            name = xsd_complex_type.local_name or xsd_complex_type.name
            if not name:
                return None

            qname = self._create_qname(xsd_complex_type)
            complex_type = ComplexType(name, qname)

            # Set basic properties
            complex_type.abstract = getattr(xsd_complex_type, 'abstract', False)
            complex_type.mixed = getattr(xsd_complex_type, 'mixed', False)

            # Determine content type
            if hasattr(xsd_complex_type, 'content'):
                if xsd_complex_type.content is None:
                    complex_type.content_type = ContentType.EMPTY
                elif complex_type.mixed:
                    complex_type.content_type = ContentType.MIXED
                else:
                    complex_type.content_type = ContentType.ELEMENT_ONLY
            else:
                complex_type.content_type = ContentType.SIMPLE

            # Handle derivation
            if hasattr(xsd_complex_type, 'base_type') and xsd_complex_type.base_type:
                base_type = self._get_or_create_type_reference(xsd_complex_type.base_type)
                if base_type:
                    complex_type.base_type = base_type
                    # Determine derivation method
                    if hasattr(xsd_complex_type, 'derivation'):
                        if xsd_complex_type.derivation == 'extension':
                            complex_type.derivation_method = DerivationMethod.EXTENSION
                        else:
                            complex_type.derivation_method = DerivationMethod.RESTRICTION

            # Convert content model (particle)
            if hasattr(xsd_complex_type, 'content') and xsd_complex_type.content:
                particle = self._convert_particle(xsd_complex_type.content)
                if particle:
                    complex_type.particle = particle

            # Convert attributes
            if hasattr(xsd_complex_type, 'attributes'):
                for attr_name, xsd_attr in xsd_complex_type.attributes.items():
                    if isinstance(xsd_attr, XsdAttribute):
                        attribute = self._convert_attribute(xsd_attr)
                        if attribute:
                            complex_type.add_attribute(attribute)

            # Convert attribute groups
            if hasattr(xsd_complex_type, 'attribute_groups'):
                for attr_group in xsd_complex_type.attribute_groups.values():
                    converted_group = self._convert_attribute_group(attr_group)
                    if converted_group:
                        complex_type.attribute_groups.append(converted_group)

            # Handle anyAttribute
            if hasattr(xsd_complex_type, 'any_attribute') and xsd_complex_type.any_attribute:
                any_attr = self._convert_any_attribute(xsd_complex_type.any_attribute)
                if any_attr:
                    complex_type.any_attribute = any_attr

            # Add annotation
            self._add_annotation(xsd_complex_type, complex_type)

            return complex_type

        except Exception as e:
            self.logger.error(
                "Error converting complex type",
                typeName=getattr(xsd_complex_type, 'name', 'unknown'),
                error=str(e)
            )
            return None

    def _convert_elements(self, xmlschema_obj: xmlschema.XMLSchema, schema: Schema) -> None:
        """Convert top-level elements."""
        for name, xsd_element in xmlschema_obj.elements.items():
            element = self._convert_element(xsd_element)
            if element:
                schema.add_element(element)

        self.logger.debug("Converted elements", count=len(schema.elements))

    def _convert_element(self, xsd_element) -> Optional[Element]:
        """Convert XSD element to our model."""
        try:
            name = xsd_element.local_name or xsd_element.name
            if not name:
                return None

            qname = self._create_qname(xsd_element)
            element = Element(name, qname)

            # Set occurrence
            min_occurs = getattr(xsd_element, 'min_occurs', 1)
            max_occurs = getattr(xsd_element, 'max_occurs', 1)

            # Handle None values (use defaults)
            if min_occurs is None:
                min_occurs = 1
            if max_occurs is None:
                max_occurs = 1

            element.occurs = ElementOccurrence(min_occurs, max_occurs)

            # Set basic properties
            element.nillable = getattr(xsd_element, 'nillable', False)
            element.abstract = getattr(xsd_element, 'abstract', False)
            element.default_value = getattr(xsd_element, 'default', None)
            element.fixed_value = getattr(xsd_element, 'fixed', None)

            # Set type
            if hasattr(xsd_element, 'type') and xsd_element.type:
                element_type = self._get_or_create_type_reference(xsd_element.type)
                if element_type:
                    element.type = element_type

            # Handle substitution group
            if hasattr(xsd_element, 'substitution_group') and xsd_element.substitution_group:
                # This would need to be resolved later in a second pass
                pass

            # Add annotation
            self._add_annotation(xsd_element, element)

            return element

        except Exception as e:
            self.logger.error(
                "Error converting element",
                elementName=getattr(xsd_element, 'name', 'unknown'),
                error=str(e)
            )
            return None

    def _convert_particle(self, xsd_particle) -> Optional[Particle]:
        """Convert XSD particle to our model."""
        try:
            # Use string comparison instead of isinstance
            particle_type = type(xsd_particle).__name__

            if 'Element' in particle_type:
                return self._convert_element(xsd_particle)
            elif 'Sequence' in particle_type:
                return self._convert_sequence(xsd_particle)
            elif 'Choice' in particle_type:
                return self._convert_choice(xsd_particle)
            elif 'All' in particle_type:
                return self._convert_all(xsd_particle)
            elif 'Group' in particle_type:
                # Check if this is an XsdGroup with a specific model (all, sequence, choice)
                if hasattr(xsd_particle, 'model'):
                    if xsd_particle.model == 'all':
                        return self._convert_all(xsd_particle)
                    elif xsd_particle.model == 'sequence':
                        return self._convert_sequence(xsd_particle)
                    elif xsd_particle.model == 'choice':
                        return self._convert_choice(xsd_particle)
                # Fallback to group reference
                return self._convert_group_reference(xsd_particle)
            elif 'Any' in particle_type:
                return self._convert_any(xsd_particle)
            else:
                self.logger.warn("Unknown particle type", particleType=particle_type)
                return None

        except Exception as e:
            self.logger.error("Error converting particle", error=str(e))
            return None

    def _convert_sequence(self, xsd_sequence) -> Sequence:
        """Convert XSD sequence to our model."""
        sequence = Sequence()

        # Set occurrence
        min_occurs = getattr(xsd_sequence, 'min_occurs', 1)
        max_occurs = getattr(xsd_sequence, 'max_occurs', 1)
        sequence.occurs = ElementOccurrence(min_occurs, max_occurs)

        # Convert child particles
        if hasattr(xsd_sequence, '_group'):
            for child in xsd_sequence._group:
                particle = self._convert_particle(child)
                if particle:
                    sequence.add_particle(particle)

        return sequence

    def _convert_choice(self, xsd_choice) -> Choice:
        """Convert XSD choice to our model."""
        choice = Choice()

        # Set occurrence
        min_occurs = getattr(xsd_choice, 'min_occurs', 1)
        max_occurs = getattr(xsd_choice, 'max_occurs', 1)
        choice.occurs = ElementOccurrence(min_occurs, max_occurs)

        # Convert child particles
        if hasattr(xsd_choice, '_group'):
            for child in xsd_choice._group:
                particle = self._convert_particle(child)
                if particle:
                    choice.add_particle(particle)

        return choice

    def _convert_all(self, xsd_all) -> All:
        """Convert XSD all to our model."""
        all_group = All()

        # Set occurrence
        min_occurs = getattr(xsd_all, 'min_occurs', 1)
        max_occurs = getattr(xsd_all, 'max_occurs', 1)
        all_group.occurs = ElementOccurrence(min_occurs, max_occurs)

        # Convert child particles
        if hasattr(xsd_all, '_group'):
            for child in xsd_all._group:
                particle = self._convert_particle(child)
                if particle:
                    all_group.add_particle(particle)

        return all_group

    def _convert_attribute(self, xsd_attribute) -> Optional[Attribute]:
        """Convert XSD attribute to our model."""
        try:
            name = xsd_attribute.local_name or xsd_attribute.name
            if not name:
                return None

            qname = self._create_qname(xsd_attribute)
            attribute = Attribute(name, qname)

            # Set usage
            use = getattr(xsd_attribute, 'use', 'optional')
            if use == 'required':
                attribute.use = AttributeUse.REQUIRED
            elif use == 'prohibited':
                attribute.use = AttributeUse.PROHIBITED
            else:
                attribute.use = AttributeUse.OPTIONAL

            # Set values
            attribute.default_value = getattr(xsd_attribute, 'default', None)
            attribute.fixed_value = getattr(xsd_attribute, 'fixed', None)

            # Set type
            if hasattr(xsd_attribute, 'type') and xsd_attribute.type:
                attr_type = self._get_or_create_type_reference(xsd_attribute.type)
                if attr_type and isinstance(attr_type, SimpleType):
                    attribute.type = attr_type

            # Add annotation
            self._add_annotation(xsd_attribute, attribute)

            return attribute

        except Exception as e:
            self.logger.error(
                "Error converting attribute",
                attrName=getattr(xsd_attribute, 'name', 'unknown'),
                error=str(e)
            )
            return None

    def _convert_groups(self, xmlschema_obj: xmlschema.XMLSchema, schema: Schema) -> None:
        """Convert named groups."""
        # Implementation for groups would go here
        pass

    def _convert_attribute_groups(self, xmlschema_obj: xmlschema.XMLSchema, schema: Schema) -> None:
        """Convert attribute groups."""
        # Implementation for attribute groups would go here
        pass

    def _convert_group_reference(self, xsd_group) -> Optional[Group]:
        """Convert group reference."""
        # Implementation for group references would go here
        return None

    def _convert_attribute_group(self, xsd_attr_group) -> Optional[AttributeGroup]:
        """Convert attribute group."""
        # Implementation for attribute groups would go here
        return None

    def _convert_any(self, xsd_any) -> Any:
        """Convert XSD any element."""
        any_element = Any()

        # Set occurrence
        min_occurs = getattr(xsd_any, 'min_occurs', 1)
        max_occurs = getattr(xsd_any, 'max_occurs', 1)
        any_element.occurs = ElementOccurrence(min_occurs, max_occurs)

        any_element.namespace_constraint = getattr(xsd_any, 'namespace', '##any')
        any_element.process_contents = getattr(xsd_any, 'process_contents', 'strict')

        return any_element

    def _convert_any_attribute(self, xsd_any_attr) -> AnyAttribute:
        """Convert XSD anyAttribute."""
        any_attr = AnyAttribute()
        any_attr.namespace_constraint = getattr(xsd_any_attr, 'namespace', '##any')
        any_attr.process_contents = getattr(xsd_any_attr, 'process_contents', 'strict')
        return any_attr

    def _convert_attributes(self, xmlschema_obj: xmlschema.XMLSchema, schema: Schema) -> None:
        """Convert top-level attributes."""
        # Implementation for top-level attributes
        pass

    def _handle_imports_includes(self, xmlschema_obj: xmlschema.XMLSchema, schema: Schema) -> None:
        """Handle schema imports and includes."""
        # Implementation for imports/includes would go here
        pass

    def _create_qname(self, xsd_component) -> QName:
        """Create QName from XSD component."""
        name = getattr(xsd_component, 'local_name', None) or getattr(xsd_component, 'name', '')
        namespace = getattr(xsd_component, 'target_namespace', None)
        prefix = None  # Could be derived from namespace prefixes if needed

        return QName(name, namespace, prefix)

    def _get_or_create_type_reference(self, xsd_type) -> Optional[Type]:
        """Get or create a type reference from XSD type."""
        if not xsd_type:
            return None

        type_name = getattr(xsd_type, 'name', None) or getattr(xsd_type, 'local_name', None)

        # Check cache first
        if type_name and type_name in self._type_cache:
            return self._type_cache[type_name]

        # Convert the type if not in cache
        if isinstance(xsd_type, XsdSimpleType):
            converted_type = self._convert_simple_type(xsd_type)
        elif isinstance(xsd_type, XsdComplexType):
            converted_type = self._convert_complex_type(xsd_type)
        else:
            self.logger.warn("Unknown type for reference", typeName=type_name)
            return None

        # Cache and return
        if converted_type and type_name:
            self._type_cache[type_name] = converted_type

        return converted_type

    def _add_annotation(self, xsd_component, our_component) -> None:
        """Add annotation from XSD component to our component."""
        if hasattr(xsd_component, 'annotation') and xsd_component.annotation:
            annotation = xsd_component.annotation

            # Add documentation
            if hasattr(annotation, 'documentation'):
                for doc in annotation.documentation:
                    if hasattr(doc, 'text') and doc.text:
                        our_component.annotation.add_documentation(doc.text)

            # Add appinfo
            if hasattr(annotation, 'appinfo'):
                for appinfo in annotation.appinfo:
                    if hasattr(appinfo, 'text') and appinfo.text:
                        our_component.annotation.add_appinfo({'text': appinfo.text})