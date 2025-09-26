"""Object-oriented schema model for XSD representation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Union, Any
from urllib.parse import urlparse


class ElementOccurrence:
    """Represents minOccurs/maxOccurs for elements."""

    def __init__(self, min_occurs: int = 1, max_occurs: Union[int, str] = 1):
        self.min = max(0, min_occurs)
        self.max = max_occurs if max_occurs == "unbounded" else max(1, int(max_occurs))

    @property
    def is_optional(self) -> bool:
        """Whether element is optional (minOccurs = 0)."""
        return self.min == 0

    @property
    def is_array(self) -> bool:
        """Whether element can occur multiple times."""
        return self.max == "unbounded" or (isinstance(self.max, int) and self.max > 1)

    @property
    def is_required(self) -> bool:
        """Whether element is required (minOccurs >= 1)."""
        return self.min >= 1

    def __str__(self) -> str:
        return f"[{self.min}..{self.max}]"


class AttributeUse(str, Enum):
    """Attribute usage types."""
    REQUIRED = "required"
    OPTIONAL = "optional"
    PROHIBITED = "prohibited"


class DerivationMethod(str, Enum):
    """Type derivation methods."""
    EXTENSION = "extension"
    RESTRICTION = "restriction"


class ContentType(str, Enum):
    """Complex type content types."""
    ELEMENT_ONLY = "elementOnly"
    MIXED = "mixed"
    EMPTY = "empty"
    SIMPLE = "simple"


@dataclass
class Annotation:
    """XSD annotation (documentation and appinfo)."""
    documentation: List[str] = field(default_factory=list)
    appinfo: List[Dict[str, Any]] = field(default_factory=list)

    def add_documentation(self, text: str) -> None:
        """Add documentation text."""
        if text.strip():
            self.documentation.append(text.strip())

    def add_appinfo(self, info: Dict[str, Any]) -> None:
        """Add appinfo content."""
        self.appinfo.append(info)


@dataclass
class QName:
    """Qualified name with namespace support."""
    local_name: str
    namespace_uri: Optional[str] = None
    prefix: Optional[str] = None

    @property
    def expanded_name(self) -> str:
        """Get expanded name format: {namespace}localname."""
        if self.namespace_uri:
            return f"{{{self.namespace_uri}}}{self.local_name}"
        return self.local_name

    def __str__(self) -> str:
        if self.prefix:
            return f"{self.prefix}:{self.local_name}"
        return self.local_name


class SchemaComponent(ABC):
    """Base class for all schema components."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        self.name = name
        self.qname = qname or QName(name)
        self.annotation = Annotation()
        self.schema_location: Optional[str] = None
        self.line_number: Optional[int] = None

    @property
    def id(self) -> str:
        """Unique identifier for this component."""
        return f"{self.__class__.__name__}_{self.qname.expanded_name}"

    @abstractmethod
    def accept(self, visitor: 'SchemaVisitor') -> Any:
        """Accept visitor pattern."""
        pass


class Type(SchemaComponent):
    """Base class for all type definitions."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.base_type: Optional['Type'] = None
        self.derivation_method: Optional[DerivationMethod] = None

    @property
    def is_derived(self) -> bool:
        """Whether this type is derived from another."""
        return self.base_type is not None

    @property
    def derivation_chain(self) -> List['Type']:
        """Get complete derivation chain from base to this type."""
        chain = []
        current = self
        while current:
            chain.append(current)
            current = current.base_type
        return chain


@dataclass
class Facet:
    """XSD facet constraint."""
    name: str
    value: Any
    fixed: bool = False


class SimpleType(Type):
    """XSD simple type definition."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.primitive_type: Optional[str] = None
        self.facets: List[Facet] = []
        self.enumeration_values: List[str] = []
        self.union_member_types: List['SimpleType'] = []
        self.list_item_type: Optional['SimpleType'] = None

    @property
    def variety(self) -> str:
        """Get simple type variety: atomic, list, or union."""
        if self.union_member_types:
            return "union"
        elif self.list_item_type:
            return "list"
        else:
            return "atomic"

    def add_facet(self, name: str, value: Any, fixed: bool = False) -> None:
        """Add a facet constraint."""
        self.facets.append(Facet(name, value, fixed))

        # Special handling for enumeration
        if name == "enumeration":
            self.enumeration_values.append(str(value))

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_simple_type(self)


class Attribute(SchemaComponent):
    """XSD attribute definition."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.type: Optional[SimpleType] = None
        self.use: AttributeUse = AttributeUse.OPTIONAL
        self.default_value: Optional[str] = None
        self.fixed_value: Optional[str] = None

    @property
    def is_required(self) -> bool:
        return self.use == AttributeUse.REQUIRED

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_attribute(self)


class Particle(SchemaComponent):
    """Base class for particles (element, choice, sequence, all, group)."""

    def __init__(self, name: str = "", qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.occurs = ElementOccurrence()


class Element(Particle):
    """XSD element definition."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.type: Optional[Type] = None
        self.nillable: bool = False
        self.default_value: Optional[str] = None
        self.fixed_value: Optional[str] = None
        self.substitution_group: Optional['Element'] = None
        self.substitutable_elements: List['Element'] = field(default_factory=list)
        self.abstract: bool = False

    @property
    def is_substitutable(self) -> bool:
        """Whether this element can be substituted by others."""
        return len(self.substitutable_elements) > 0

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_element(self)


class ModelGroup(Particle):
    """Base class for model groups (sequence, choice, all)."""

    def __init__(self, name: str = ""):
        super().__init__(name)
        self.particles: List[Particle] = []

    def add_particle(self, particle: Particle) -> None:
        """Add a particle to this group."""
        self.particles.append(particle)


class Sequence(ModelGroup):
    """XSD sequence group."""

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_sequence(self)


class Choice(ModelGroup):
    """XSD choice group."""

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_choice(self)


class All(ModelGroup):
    """XSD all group."""

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_all(self)


class Group(Particle):
    """XSD named group definition."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.model_group: Optional[ModelGroup] = None

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_group(self)


class ComplexType(Type):
    """XSD complex type definition."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.content_type: ContentType = ContentType.ELEMENT_ONLY
        self.particle: Optional[Particle] = None
        self.attributes: List[Attribute] = []
        self.attribute_groups: List['AttributeGroup'] = []
        self.any_attribute: Optional['AnyAttribute'] = None
        self.abstract: bool = False
        self.mixed: bool = False

    def add_attribute(self, attribute: Attribute) -> None:
        """Add an attribute to this complex type."""
        self.attributes.append(attribute)

    def get_all_attributes(self) -> List[Attribute]:
        """Get all attributes including those from attribute groups."""
        all_attributes = list(self.attributes)
        for attr_group in self.attribute_groups:
            all_attributes.extend(attr_group.attributes)
        return all_attributes

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_complex_type(self)


class AttributeGroup(SchemaComponent):
    """XSD attribute group definition."""

    def __init__(self, name: str, qname: Optional[QName] = None):
        super().__init__(name, qname)
        self.attributes: List[Attribute] = []
        self.attribute_groups: List['AttributeGroup'] = []
        self.any_attribute: Optional['AnyAttribute'] = None

    def add_attribute(self, attribute: Attribute) -> None:
        """Add an attribute to this group."""
        self.attributes.append(attribute)

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_attribute_group(self)


class AnyAttribute(SchemaComponent):
    """XSD anyAttribute wildcard."""

    def __init__(self):
        super().__init__("anyAttribute")
        self.namespace_constraint: str = "##any"
        self.process_contents: str = "strict"

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_any_attribute(self)


class Any(Particle):
    """XSD any element wildcard."""

    def __init__(self):
        super().__init__("any")
        self.namespace_constraint: str = "##any"
        self.process_contents: str = "strict"

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_any(self)


@dataclass
class IdentityConstraint(SchemaComponent):
    """XSD identity constraint (key, keyref, unique)."""

    constraint_type: str  # "key", "keyref", "unique"
    selector: str
    fields: List[str]
    refer: Optional[str] = None  # For keyref

    def accept(self, visitor: 'SchemaVisitor') -> Any:
        return visitor.visit_identity_constraint(self)


class Schema:
    """Root XSD schema representation."""

    def __init__(self, target_namespace: Optional[str] = None):
        self.target_namespace = target_namespace
        self.namespace_prefixes: Dict[str, str] = {}
        self.element_form_default = "unqualified"
        self.attribute_form_default = "unqualified"

        # Schema components
        self.elements: Dict[str, Element] = {}
        self.types: Dict[str, Type] = {}
        self.attributes: Dict[str, Attribute] = {}
        self.groups: Dict[str, Group] = {}
        self.attribute_groups: Dict[str, AttributeGroup] = {}
        self.identity_constraints: Dict[str, IdentityConstraint] = {}

        # Import/include tracking
        self.imported_schemas: List['Schema'] = []
        self.included_schemas: List['Schema'] = []

    def add_element(self, element: Element) -> None:
        """Add a top-level element."""
        self.elements[element.name] = element

    def add_type(self, type_def: Type) -> None:
        """Add a type definition."""
        self.types[type_def.name] = type_def

    def add_attribute(self, attribute: Attribute) -> None:
        """Add a top-level attribute."""
        self.attributes[attribute.name] = attribute

    def add_group(self, group: Group) -> None:
        """Add a group definition."""
        self.groups[group.name] = group

    def add_attribute_group(self, attr_group: AttributeGroup) -> None:
        """Add an attribute group."""
        self.attribute_groups[attr_group.name] = attr_group

    def get_all_complex_types(self) -> List[ComplexType]:
        """Get all complex types defined in this schema."""
        return [t for t in self.types.values() if isinstance(t, ComplexType)]

    def get_all_simple_types(self) -> List[SimpleType]:
        """Get all simple types defined in this schema."""
        return [t for t in self.types.values() if isinstance(t, SimpleType)]


class SchemaVisitor(ABC):
    """Visitor pattern for traversing schema components."""

    @abstractmethod
    def visit_schema(self, schema: Schema) -> Any:
        pass

    @abstractmethod
    def visit_element(self, element: Element) -> Any:
        pass

    @abstractmethod
    def visit_attribute(self, attribute: Attribute) -> Any:
        pass

    @abstractmethod
    def visit_simple_type(self, simple_type: SimpleType) -> Any:
        pass

    @abstractmethod
    def visit_complex_type(self, complex_type: ComplexType) -> Any:
        pass

    @abstractmethod
    def visit_sequence(self, sequence: Sequence) -> Any:
        pass

    @abstractmethod
    def visit_choice(self, choice: Choice) -> Any:
        pass

    @abstractmethod
    def visit_all(self, all_group: All) -> Any:
        pass

    @abstractmethod
    def visit_group(self, group: Group) -> Any:
        pass

    @abstractmethod
    def visit_attribute_group(self, attr_group: AttributeGroup) -> Any:
        pass

    @abstractmethod
    def visit_any(self, any_element: Any) -> Any:
        pass

    @abstractmethod
    def visit_any_attribute(self, any_attr: AnyAttribute) -> Any:
        pass

    @abstractmethod
    def visit_identity_constraint(self, constraint: IdentityConstraint) -> Any:
        pass