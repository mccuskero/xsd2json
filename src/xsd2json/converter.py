"""Main converter class for XSD to JSON Schema transformation."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from .config import Config
from .logger import create_logger
from .parser import XSDParser
from .schema_model import Schema


@dataclass
class ConversionResult:
    """Result of XSD to JSON conversion."""
    success: bool
    output_files: List[Path]
    processing_time: float
    errors: List[str]
    warnings: List[str]
    statistics: Dict[str, int]


class Converter:
    """Main converter for transforming XSD schemas to JSON Schema."""

    def __init__(self, config: Config):
        self.config = config
        self.logger = create_logger(level=config.logging.level, component="converter")

        # Initialize components
        self.parser = XSDParser()
        self.mapper = None  # Will be implemented next
        self.serializer = None  # Will be implemented next

        self.logger.info(
            "Converter initialized",
            outputMode=config.output_mode,
            llmOptimized=config.llm_optimized,
        )

    def convert(self) -> ConversionResult:
        """Convert XSD schema to JSON Schema format."""
        start_time = time.time()
        errors = []
        warnings = []
        output_files = []
        statistics = {}

        try:
            self.logger.info("Starting XSD conversion", inputFile=str(self.config.input_file))

            # Step 1: Load and parse XSD
            self.logger.info("Loading XSD schema")
            schema_model = self._load_and_parse_xsd()
            if not schema_model:
                errors.append("Failed to load or parse XSD schema")
                return self._create_result(False, output_files, time.time() - start_time, errors, warnings, statistics)

            # Step 2: Transform to JSON Schema
            self.logger.info("Transforming to JSON Schema")
            json_schemas = self._transform_to_json(schema_model)
            if not json_schemas:
                errors.append("Failed to transform XSD to JSON Schema")
                return self._create_result(False, output_files, time.time() - start_time, errors, warnings, statistics)

            # Step 3: Apply LLM optimizations if enabled
            if self.config.llm_optimized:
                self.logger.info("Applying LLM optimizations")
                json_schemas = self._apply_llm_optimizations(json_schemas)

            # Step 4: Generate output files
            self.logger.info("Generating output files", outputMode=self.config.output_mode)
            output_files = self._generate_output_files(json_schemas)

            # Collect statistics
            statistics = {
                "complexTypes": len([s for s in json_schemas if s.get("type") == "object"]),
                "simpleTypes": len([s for s in json_schemas if s.get("type") != "object"]),
                "outputFiles": len(output_files),
            }

            processing_time = time.time() - start_time
            self.logger.info("Conversion completed successfully", processingTime=processing_time, **statistics)

            return self._create_result(True, output_files, processing_time, errors, warnings, statistics)

        except Exception as e:
            self.logger.error("Conversion failed with exception", error=str(e), type=type(e).__name__)
            errors.append(f"Conversion failed: {str(e)}")
            return self._create_result(False, output_files, time.time() - start_time, errors, warnings, statistics)

    def _load_and_parse_xsd(self) -> Optional[Schema]:
        """Load and parse the XSD file into internal schema model."""
        self.logger.debug("Loading XSD file", inputFile=str(self.config.input_file))

        if not self.config.input_file.exists():
            self.logger.error("Input file does not exist", inputFile=str(self.config.input_file))
            return None

        # Use the XSD parser to parse the file
        schema = self.parser.parse(self.config.input_file)

        if schema:
            self.logger.info(
                "XSD parsing completed",
                targetNamespace=schema.target_namespace,
                elements=len(schema.elements),
                types=len(schema.types),
            )
        else:
            self.logger.error("Failed to parse XSD file")

        return schema

    def _transform_to_json(self, schema_model: Schema) -> List[Dict]:
        """Transform internal schema model to JSON Schema format."""
        self.logger.debug("Transforming schema model to JSON Schema")

        json_schemas = []

        # Create a basic JSON schema structure for each complex type
        self.logger.debug("Processing schema types", typeCount=len(schema_model.types), typeNames=list(schema_model.types.keys()))
        for type_name, xsd_type in schema_model.types.items():
            self.logger.debug("Processing type", typeName=type_name, typeClass=type(xsd_type).__name__)
            json_schema = self._create_json_schema_for_type(xsd_type, schema_model.target_namespace or 'http://example.com')

            json_schemas.append(json_schema)
            self.logger.debug("Created JSON schema for type", typeName=type_name, schemaId=json_schema["$id"])

        # Create schemas for top-level elements
        for element_name, element in schema_model.elements.items():
            json_schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"{schema_model.target_namespace or 'http://example.com'}/elements/{element_name}",
                "title": f"Element: {element_name}",
                "type": "object",
                "description": " ".join(element.annotation.documentation) if element.annotation.documentation else None
            }

            json_schemas.append(json_schema)
            self.logger.debug("Created JSON schema for element", elementName=element_name, schemaId=json_schema["$id"])

        self.logger.debug("Total JSON schemas created", count=len(json_schemas))

        if not json_schemas:
            # Fallback schema if no types found
            json_schemas.append({
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"{schema_model.target_namespace or 'http://example.com'}",
                "title": "Generated JSON Schema",
                "type": "object",
                "properties": {},
            })

        return json_schemas

    def _extract_properties_from_particle(self, particle) -> tuple[Dict[str, Any], List[str]]:
        """Extract properties and required elements from a particle with better sequence/choice/all handling."""
        properties = {}
        required_elements = []

        if not particle:
            return properties, required_elements

        # Handle different particle types
        if hasattr(particle, 'particles') and particle.particles:
            # This is a model group (sequence, choice, all)
            particle_type = type(particle).__name__

            for child_particle in particle.particles:
                if hasattr(child_particle, 'name') and child_particle.name:
                    # This is an element
                    element_schema = self._create_element_schema(child_particle)
                    properties[child_particle.name] = element_schema

                    # For xs:all elements, if minOccurs >= 1, make them required
                    # For sequence/choice, check individual element minOccurs
                    if 'All' in particle_type:
                        # xs:all - all elements with minOccurs >= 1 are required
                        if hasattr(child_particle, 'occurs') and hasattr(child_particle.occurs, 'min'):
                            if child_particle.occurs.min >= 1:
                                required_elements.append(child_particle.name)
                    else:
                        # sequence/choice - check individual element requirements
                        if hasattr(child_particle, 'occurs') and hasattr(child_particle.occurs, 'min'):
                            if child_particle.occurs.min >= 1:
                                required_elements.append(child_particle.name)

                elif hasattr(child_particle, 'particles'):
                    # Nested model group - recurse
                    nested_properties, nested_required = self._extract_properties_from_particle(child_particle)
                    properties.update(nested_properties)
                    required_elements.extend(nested_required)

        elif hasattr(particle, 'name') and particle.name:
            # This is a single element
            element_schema = self._create_element_schema(particle)
            properties[particle.name] = element_schema

            # Check if this single element is required
            if hasattr(particle, 'occurs') and hasattr(particle.occurs, 'min'):
                if particle.occurs.min >= 1:
                    required_elements.append(particle.name)

        return properties, required_elements

    def _create_element_schema(self, element) -> Dict[str, Any]:
        """Create JSON schema for a single element."""
        element_schema = {}

        # Determine type based on element's type
        if hasattr(element, 'type') and element.type:
            if hasattr(element.type, 'name'):
                # Reference to a named type
                element_schema["$ref"] = f"#/definitions/{element.type.name}"
            else:
                # Inline type - map to JSON type
                element_schema["type"] = self._map_xsd_type_to_json_type(element.type)
        else:
            # Fallback
            element_schema["type"] = "string"

        # Handle occurrence constraints
        if hasattr(element, 'occurs'):
            if element.occurs.is_array:
                # Wrap in array for multiple occurrences
                element_schema = {
                    "type": "array",
                    "items": element_schema,
                    "minItems": element.occurs.min,
                }
                if element.occurs.max != "unbounded":
                    element_schema["maxItems"] = element.occurs.max

            if element.occurs.is_optional:
                # Element is optional - this would be handled in the required array
                pass

        # Add description
        if hasattr(element, 'annotation') and element.annotation and element.annotation.documentation:
            element_schema["description"] = " ".join(element.annotation.documentation)

        return element_schema

    def _apply_llm_optimizations(self, json_schemas: List[Dict]) -> List[Dict]:
        """Apply LLM-specific optimizations to JSON schemas."""
        optimizations_applied = []

        for schema in json_schemas:
            if self.config.llm.simplify:
                self._apply_simplification(schema)
                optimizations_applied.append("simplify")

            if self.config.llm.add_metadata:
                self._add_metadata(schema)
                optimizations_applied.append("metadata")

            if self.config.llm.flatten:
                self._apply_flattening(schema)
                optimizations_applied.append("flatten")

            if self.config.llm.natural_naming:
                self._apply_natural_naming(schema)
                optimizations_applied.append("natural_naming")

            if self.config.llm.embed_docs:
                self._embed_documentation(schema)
                optimizations_applied.append("embed_docs")

        self.logger.info("Applied LLM optimizations", optimizations=optimizations_applied)
        return json_schemas

    def _apply_simplification(self, schema: Dict) -> None:
        """Simplify schema structure for LLM consumption."""
        # TODO: Implement simplification logic
        self.logger.debug("Applying schema simplification")

    def _add_metadata(self, schema: Dict) -> None:
        """Add semantic metadata for LLM understanding."""
        # TODO: Implement metadata addition logic
        self.logger.debug("Adding semantic metadata")

    def _apply_flattening(self, schema: Dict) -> None:
        """Flatten nested structures to reduce hierarchy depth."""
        # TODO: Implement flattening logic
        self.logger.debug("Applying schema flattening")

    def _apply_natural_naming(self, schema: Dict) -> None:
        """Convert technical names to more natural language."""
        # TODO: Implement natural naming logic
        self.logger.debug("Applying natural naming")

    def _embed_documentation(self, schema: Dict) -> None:
        """Embed documentation and comments in schema."""
        # TODO: Implement documentation embedding logic
        self.logger.debug("Embedding documentation")

    def _generate_output_files(self, json_schemas: List[Dict]) -> List[Path]:
        """Generate output files based on configuration."""
        output_files = []

        # Ensure output directory exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        if self.config.output_mode.value == "single":
            output_files = self._generate_single_file_output(json_schemas)
        else:
            output_files = self._generate_multi_file_output(json_schemas)

        return output_files

    def _generate_single_file_output(self, json_schemas: List[Dict]) -> List[Path]:
        """Generate single consolidated JSON schema file."""
        output_file = self.config.output_dir / "schema.json"

        import json

        if len(json_schemas) == 1:
            # If only one schema, write it directly
            consolidated_schema = json_schemas[0]
        else:
            # Create a consolidated schema with definitions for multiple schemas
            definitions = {}
            properties = {}

            for schema in json_schemas:
                schema_id = schema.get("$id", "unknown")
                title = schema.get("title", "Unknown Schema")

                # Extract the schema name from the ID
                if "/" in schema_id:
                    schema_name = schema_id.split("/")[-1]
                else:
                    schema_name = title.replace(" ", "").replace("Generated JSON Schema for ", "")

                # Add to definitions
                definitions[schema_name] = {k: v for k, v in schema.items() if k != "$id"}

                # Add reference in properties
                properties[schema_name] = {"$ref": f"#/definitions/{schema_name}"}

            consolidated_schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "http://example.com/consolidated",
                "title": "Consolidated JSON Schema",
                "type": "object",
                "properties": properties,
                "definitions": definitions
            }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(consolidated_schema, f, indent=2 if self.config.serializer.pretty else None)

        self.logger.info("Generated single output file", outputFile=str(output_file), schemasConsolidated=len(json_schemas))
        return [output_file]

    def _generate_multi_file_output(self, json_schemas: List[Dict]) -> List[Path]:
        """Generate multiple JSON schema files with master file and references."""
        output_files = []
        import json

        # Create directories
        types_dir = self.config.output_dir / "types"
        types_dir.mkdir(parents=True, exist_ok=True)

        # Organize schemas by type
        complex_types = []
        simple_types = []
        element_schemas = []

        for schema in json_schemas:
            schema_id = schema.get("$id", "unknown")
            title = schema.get("title", "Unknown")
            schema_type = schema.get("type", "object")

            if "elements/" in schema_id:
                element_schemas.append(schema)
            elif schema_type == "object" and "Generated JSON Schema for" in title:
                complex_types.append(schema)
            else:
                simple_types.append(schema)

        # Generate individual type files
        master_properties = {}
        file_catalog = []

        for schema in complex_types + simple_types:
            type_name = self._extract_type_name(schema)
            filename = self._sanitize_filename(type_name) + ".json"
            type_file = types_dir / filename

            # Clean schema for individual file (remove master-specific fields)
            individual_schema = {k: v for k, v in schema.items() if k != "$id"}
            individual_schema["$id"] = f"http://example.com/types/{type_name}"

            with open(type_file, 'w', encoding='utf-8') as f:
                json.dump(individual_schema, f, indent=2 if self.config.serializer.pretty else None)

            output_files.append(type_file)
            master_properties[type_name] = {"$ref": f"types/{filename}"}

            file_catalog.append({
                "filename": filename,
                "type_name": type_name,
                "description": individual_schema.get("description", "No description available"),
                "schema_type": individual_schema.get("type", "unknown")
            })

            self.logger.debug("Generated type file", typeName=type_name, outputFile=filename)

        # Generate master schema file
        master_file = self.config.output_dir / "schema.json"
        master_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "http://example.com/master",
            "title": "Master Schema",
            "description": f"Master schema with references to individual type definitions. Generated from {self.config.input_file.name}",
            "type": "object",
            "properties": master_properties
        }

        with open(master_file, 'w', encoding='utf-8') as f:
            json.dump(master_schema, f, indent=2 if self.config.serializer.pretty else None)

        output_files.append(master_file)
        self.logger.debug("Generated master schema file", outputFile="schema.json")

        # Generate README catalog
        readme_file = self.config.output_dir / "README.md"
        readme_content = self._generate_readme_catalog(file_catalog)

        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(readme_content)

        output_files.append(readme_file)
        self.logger.debug("Generated README catalog", outputFile="README.md")

        self.logger.info(
            "Generated multi-file output",
            totalFiles=len(output_files),
            complexTypes=len(complex_types),
            simpleTypes=len(simple_types),
            elements=len(element_schemas)
        )
        return output_files

    def _create_result(
        self,
        success: bool,
        output_files: List[Path],
        processing_time: float,
        errors: List[str],
        warnings: List[str],
        statistics: Dict[str, int]
    ) -> ConversionResult:
        """Create conversion result object."""
        return ConversionResult(
            success=success,
            output_files=output_files,
            processing_time=processing_time,
            errors=errors,
            warnings=warnings,
            statistics=statistics,
        )

    def _extract_type_name(self, schema: Dict) -> str:
        """Extract type name from schema."""
        title = schema.get("title", "")
        if "Generated JSON Schema for" in title:
            return title.replace("Generated JSON Schema for ", "")

        schema_id = schema.get("$id", "")
        if "/" in schema_id:
            return schema_id.split("/")[-1]

        return "UnknownType"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename by converting to lowercase and replacing spaces with hyphens."""
        import re
        # Convert camelCase to kebab-case
        name = re.sub('([a-z0-9])([A-Z])', r'\1-\2', name).lower()
        # Replace spaces and other characters with hyphens
        name = re.sub('[^a-z0-9-]', '-', name)
        # Remove multiple consecutive hyphens
        name = re.sub('-+', '-', name)
        # Remove leading/trailing hyphens
        return name.strip('-')

    def _generate_readme_catalog(self, file_catalog: List[Dict]) -> str:
        """Generate README content with catalog of schema files."""
        content = ["# JSON Schema Files\n"]
        content.append("This directory contains JSON Schema files generated from XSD.\n")
        content.append(f"**Generated on:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
        content.append(f"**Source XSD:** {self.config.input_file.name}\n")

        content.append("## File Structure\n")
        content.append("- `schema.json` - Master schema file with $ref references to individual types")
        content.append("- `types/` - Individual type definition files")
        content.append("- `README.md` - This catalog file\n")

        if file_catalog:
            content.append("## Type Definitions\n")
            content.append("| File | Type Name | Schema Type | Description |")
            content.append("|------|-----------|-------------|-------------|")

            for item in sorted(file_catalog, key=lambda x: x['filename']):
                description = item['description'] or "No description"
                # Truncate long descriptions
                if len(description) > 60:
                    description = description[:57] + "..."
                # Escape markdown characters in description
                description = description.replace("|", "\\|").replace("\n", " ")

                content.append(
                    f"| `types/{item['filename']}` | {item['type_name']} | {item['schema_type']} | {description} |"
                )

        content.append("\n## Usage\n")
        content.append("To reference these schemas in your application:")
        content.append("\n```json")
        content.append('{ "$ref": "schema.json" }')
        content.append("```\n")
        content.append("Or reference individual types:")
        content.append("\n```json")
        content.append('{ "$ref": "types/person-type.json" }')
        content.append("```\n")

        content.append("---\n")
        content.append("*Generated by [xsd2json](https://github.com/example/xsd2json)*")

        return "\n".join(content)

    def _create_json_schema_for_type(self, xsd_type, namespace: str) -> Dict:
        """Create JSON Schema for a specific XSD type with inheritance support."""
        json_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{namespace}/{xsd_type.name}",
            "title": f"Generated JSON Schema for {xsd_type.name}",
            "properties": {},
        }

        # Add description from annotation
        if xsd_type.annotation and xsd_type.annotation.documentation:
            json_schema["description"] = " ".join(xsd_type.annotation.documentation)

        # Check for enumerations FIRST (before inheritance) since enum types also have base_type
        if hasattr(xsd_type, 'facets') and xsd_type.facets:
            # Handle enumeration facets - facets can be dict or list depending on parser
            enumeration_values = []

            if isinstance(xsd_type.facets, dict):
                # Old format (dict)
                for facet_name, facet_value in xsd_type.facets.items():
                    if facet_name == 'enumeration':
                        if isinstance(facet_value, list):
                            enumeration_values.extend(facet_value)
                        else:
                            enumeration_values.append(facet_value)
            elif isinstance(xsd_type.facets, list):
                # New format (list of Facet objects)
                for facet in xsd_type.facets:
                    if hasattr(facet, 'name') and facet.name == 'enumeration':
                        if isinstance(facet.value, list):
                            enumeration_values.extend(facet.value)
                        else:
                            enumeration_values.append(facet.value)

            if enumeration_values:
                json_schema["type"] = "string"
                json_schema["enum"] = enumeration_values
                additional_properties = {}  # Enums don't have properties
            else:
                # Simple type without enums - fall through to other handling
                json_schema["type"] = self._map_xsd_type_to_json_type(xsd_type)
                additional_properties = {}
        # Handle inheritance with allOf pattern for extensions
        elif hasattr(xsd_type, 'base_type') and xsd_type.base_type and hasattr(xsd_type, 'derivation_method'):
            if xsd_type.derivation_method and xsd_type.derivation_method.value == "extension":
                # Use allOf for extensions to combine base type with extensions
                json_schema["allOf"] = [
                    {"$ref": f"#/definitions/{xsd_type.base_type.name}"},
                    {
                        "type": "object",
                        "properties": {}
                    }
                ]

                # Add metadata about inheritance
                json_schema["x-inheritance"] = {
                    "type": "extension",
                    "baseType": xsd_type.base_type.name
                }

                # Extract additional properties from this type
                additional_properties = json_schema["allOf"][1]["properties"]
            else:
                # For restrictions, copy base and then restrict
                json_schema["type"] = "object"
                json_schema["x-inheritance"] = {
                    "type": "restriction",
                    "baseType": xsd_type.base_type.name
                }
                additional_properties = json_schema["properties"]
        else:
            # No inheritance - regular type
            # Complex type or simple type without facets
            json_schema["type"] = "object" if hasattr(xsd_type, 'particle') or hasattr(xsd_type, 'attributes') else "string"
            additional_properties = json_schema["properties"]

        # Extract properties from particle (elements)
        if hasattr(xsd_type, 'particle') and xsd_type.particle:
            particle_properties, required_elements = self._extract_properties_from_particle(xsd_type.particle)
            additional_properties.update(particle_properties)

            # Add required elements from particle (e.g., xs:all with minOccurs=1)
            if required_elements:
                if "required" not in json_schema:
                    json_schema["required"] = []
                json_schema["required"].extend(required_elements)

        # Add attributes as properties (only additional attributes for derived types)
        if hasattr(xsd_type, 'attributes'):
            # For derived types, only add attributes not present in base type
            base_attribute_names = set()
            if hasattr(xsd_type, 'base_type') and xsd_type.base_type and hasattr(xsd_type.base_type, 'attributes'):
                base_attribute_names = {attr.name for attr in xsd_type.base_type.attributes}

            for attr in xsd_type.attributes:
                # Skip attributes that are inherited from base type (unless this is the base type itself)
                if xsd_type.base_type and attr.name in base_attribute_names:
                    continue

                attr_name = f"@{attr.name}" if self.config.attr_style.value == "prefix" else attr.name
                additional_properties[attr_name] = {
                    "type": self._map_xsd_type_to_json_type(attr.type if attr.type else None),
                    "description": " ".join(attr.annotation.documentation) if attr.annotation.documentation else f"Attribute: {attr.name}"
                }

                # Add required attributes to schema
                if attr.use and attr.use.value == "required":
                    if "required" not in json_schema:
                        json_schema["required"] = []
                    json_schema["required"].append(attr_name)

        return json_schema

    def _map_xsd_type_to_json_type(self, xsd_type) -> str:
        """Map XSD type to JSON Schema type."""
        if not xsd_type:
            return "string"

        # Simple type mapping
        type_name = getattr(xsd_type, 'name', '') if xsd_type else ''
        primitive_type = getattr(xsd_type, 'primitive_type', '') if xsd_type else ''

        # Use primitive type if available, otherwise use name
        type_to_check = primitive_type or type_name or ''

        # Common XSD to JSON type mappings
        if any(t in type_to_check.lower() for t in ['string', 'normalizedstring', 'token', 'name', 'ncname', 'id']):
            return "string"
        elif any(t in type_to_check.lower() for t in ['int', 'integer', 'long', 'short', 'byte']):
            return "integer"
        elif any(t in type_to_check.lower() for t in ['decimal', 'double', 'float']):
            return "number"
        elif any(t in type_to_check.lower() for t in ['boolean']):
            return "boolean"
        elif any(t in type_to_check.lower() for t in ['date', 'time', 'datetime']):
            return "string"  # Could add format: "date-time"
        else:
            return "string"