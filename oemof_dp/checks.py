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
            field = sk.get("field", None)

            if not ref_resource_name or not field:
                continue

            # 1. Check if reference with given name exists
            if not package.has_resource(ref_resource_name):
                yield SequenceKeyError.from_row(
                    row,
                    note=f'referenced resource "{ref_resource_name}" does not exist',
                    field_names=fields,
                    field_values=[row[f] for f in fields if f in row],
                    reference_name=ref_resource_name,
                )
                continue

            ref_resource = package.get_resource(ref_resource_name)
            # Ensure ref_resource schema is available (might need to open/infer if not already)
            # For simplicity, we assume it's already part of the package and has a schema
            ref_field_names = ref_resource.schema.field_names

            # 2. Check for each value in given fields if this value exists as COLUMN in the referenced sequence
            for field in fields:
                if field not in row:
                    continue

                value = row[field]
                if value and value not in ref_field_names:
                    yield SequenceKeyError.from_row(
                        row,
                        note=f'value "{value}" in field "{field}" does not exist as a column in resource "{ref_resource_name}"',
                        field_names=[field],
                        field_values=[value],
                        reference_name=ref_resource_name,
                    )
