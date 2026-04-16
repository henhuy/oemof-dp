

import pathlib
import jsonschema
from frictionless import Package, Checklist
from oemof_dp import checks


def test_datapackage_with_nested_yamls():
    path = pathlib.Path(__file__).parent.parent / "datapackages" / "simple" / "datapackage.json"
    package = Package(path)
    
    # 1. Validate the whole package (including our custom checks for tables)
    checklist = Checklist(checks=[checks.SequenceReferenceCheck()])
    report = package.validate(checklist=checklist)
    assert report.valid
    
    # 2. Specifically validate JSON resources using JSON Schema
    # (Since we saw that JsonResource in v5 doesn't automatically validate against jsonSchema in descriptor)
    for resource in package.resources:
        if resource.type == "json":
            import yaml
            data = yaml.safe_load(resource.read_bytes())
            schema = resource.custom.get("jsonSchema")
            if schema:
                jsonschema.validate(instance=data, schema=schema)