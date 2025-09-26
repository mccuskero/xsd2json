"""Pytest configuration and fixtures for xsd2json tests."""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from src.xsd2json.config import Config, OutputMode
from src.xsd2json.logger import LogLevel


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_path:
        yield Path(temp_path)


@pytest.fixture
def simple_xsd_content() -> str:
    """Simple XSD content for testing."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://example.com/test"
           xmlns:tns="http://example.com/test"
           elementFormDefault="qualified">

    <xs:element name="person" type="tns:PersonType">
        <xs:annotation>
            <xs:documentation>A person element</xs:documentation>
        </xs:annotation>
    </xs:element>

    <xs:complexType name="PersonType">
        <xs:annotation>
            <xs:documentation>Person complex type</xs:documentation>
        </xs:annotation>
        <xs:sequence>
            <xs:element name="name" type="xs:string"/>
            <xs:element name="age" type="xs:int" minOccurs="0"/>
        </xs:sequence>
        <xs:attribute name="id" type="xs:ID" use="required"/>
    </xs:complexType>

    <xs:simpleType name="EmailType">
        <xs:annotation>
            <xs:documentation>Email address type</xs:documentation>
        </xs:annotation>
        <xs:restriction base="xs:string">
            <xs:pattern value="[^@]+@[^@]+\\.[^@]+"/>
        </xs:restriction>
    </xs:simpleType>

</xs:schema>'''


@pytest.fixture
def simple_xsd_file(temp_dir: Path, simple_xsd_content: str) -> Path:
    """Create a simple XSD file for testing."""
    xsd_file = temp_dir / "test.xsd"
    xsd_file.write_text(simple_xsd_content, encoding='utf-8')
    return xsd_file


@pytest.fixture
def default_config(temp_dir: Path) -> Config:
    """Default configuration for testing."""
    config = Config(
        input_file=None,
        output_dir=temp_dir / "output",
        output_mode=OutputMode.SINGLE
    )
    config.logging.level = LogLevel.ERROR  # Suppress logs in tests
    return config


@pytest.fixture
def complex_xsd_content() -> str:
    """Complex XSD with inheritance for testing."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="http://example.com/complex"
           xmlns:tns="http://example.com/complex"
           elementFormDefault="qualified">

    <xs:complexType name="BaseType">
        <xs:sequence>
            <xs:element name="id" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

    <xs:complexType name="ExtendedType">
        <xs:complexContent>
            <xs:extension base="tns:BaseType">
                <xs:sequence>
                    <xs:element name="extra" type="xs:string"/>
                </xs:sequence>
            </xs:extension>
        </xs:complexContent>
    </xs:complexType>

    <xs:element name="root">
        <xs:complexType>
            <xs:choice maxOccurs="unbounded">
                <xs:element name="option1" type="xs:string"/>
                <xs:element name="option2" type="xs:int"/>
            </xs:choice>
        </xs:complexType>
    </xs:element>

</xs:schema>'''


@pytest.fixture
def complex_xsd_file(temp_dir: Path, complex_xsd_content: str) -> Path:
    """Create a complex XSD file for testing."""
    xsd_file = temp_dir / "complex.xsd"
    xsd_file.write_text(complex_xsd_content, encoding='utf-8')
    return xsd_file