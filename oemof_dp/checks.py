from typing import List, Any, Iterable

import attrs
from frictionless import Check, Error
from frictionless.errors import RowError


@attrs.define(kw_only=True, repr=False)
class SequenceKeyError(RowError):
    type = "sequence-key"
    title = "SequenceKey Error"
    description = "Values in the sequence key fields should exist as column names in the reference table"
    template = 'Row at position "{rowNumber}" violates the sequence key: {note}'

    field_name: str
    field_cells: List[str]
    reference_name: str

    @classmethod
    def from_row(
        cls,
        row,
        *,
        note: str,
        field_name: str,
        field_values: List[Any],
        reference_name: str,
    ):
        to_str = lambda v: str(v) if v is not None else ""
        return cls(
            note=note,
            cells=list(map(to_str, row.cells)),
            row_number=row.row_number,
            field_name=field_name,
            field_cells=list(map(to_str, field_values)),
            reference_name=reference_name,
        )


class SequenceReferenceCheck(Check):
    """Check sequence references"""
    type = "sequence-reference"
    Errors = [SequenceKeyError]

    def validate_row(self, row) -> Iterable[Error]:
        # Only validate table resources here
        if self.resource.type != "table":
            return

        # Get sequenceKeys from resource schema
        # Schema is a Metadata object, use get_defined
        sequence_keys = self.resource.schema.get_defined("sequenceKeys", default=[])
        if not sequence_keys:
            return

        package = self.resource.package
        if not package:
            # If no package, we might not be able to find the referenced resource
            # Frictionless usually attaches package to resource if they are part of one.
            return

        for sk in sequence_keys:
            ref_resource_name = sk.get("reference")
            field_name = sk.get("field", None)

            if not ref_resource_name or not field_name:
                continue

            # 1. Check if reference with given name exists
            if not package.has_resource(ref_resource_name):
                yield SequenceKeyError.from_row(
                    row,
                    note=f'referenced resource "{ref_resource_name}" does not exist',
                    field_name=field_name,
                    field_values=[row[field_name]] if field_name in row else [],
                    reference_name=ref_resource_name,
                )
                continue

            ref_resource = package.get_resource(ref_resource_name)
            # Ensure ref_resource schema is available (might need to open/infer if not already)
            # For simplicity, we assume it's already part of the package and has a schema
            ref_field_names = ref_resource.schema.field_names

            # 2. Check for each value in given fields if this value exists as COLUMN in the referenced sequence
            if field_name not in row:
                continue

            value = row[field_name]
            if value and value not in ref_field_names:
                yield SequenceKeyError.from_row(
                    row,
                    note=f'value "{value}" in field "{field_name}" does not exist as a column in resource "{ref_resource_name}"',
                    field_name=field_name,
                    field_values=[value],
                    reference_name=ref_resource_name,
                )

    def validate_resource(self, resource) -> Iterable[Error]:
        # Handle non-table resources (like JSON/YAML)
        if resource.type != "json":
            return

        # Check for sequenceKeys in the resource descriptor directly
        sequence_keys = resource.custom.get("sequenceKeys", [])
        if not sequence_keys:
            return

        package = resource.package
        if not package:
            return

        # We need to read the data to validate "rows"
        import yaml
        data = yaml.safe_load(resource.read_bytes())
        if not isinstance(data, list):
            # If it's not a list of objects, we might need a different logic
            # but for our case (YAML list), it should be a list.
            return

        for i, item in enumerate(data):
            for sk in sequence_keys:
                ref_resource_name = sk.get("reference")
                field_name = sk.get("field", None)

                if not ref_resource_name or not field_name:
                    continue

                if field_name not in item:
                    continue

                value = item[field_name]
                if not value:
                    continue

                if not package.has_resource(ref_resource_name):
                    # For non-table resources, we don't have Row objects,
                    # and SequenceKeyError is a RowError.
                    # We could yield a general Error or just skip for now.
                    continue

                ref_resource = package.get_resource(ref_resource_name)
                ref_field_names = ref_resource.schema.field_names

                if value not in ref_field_names:
                    # For now, we only support RowError for tables.
                    # If needed, we could define a new Error for JSON resources.
                    pass
