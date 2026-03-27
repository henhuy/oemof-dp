
import pathlib

from frictionless import Package, Checklist

from checks import SequenceReferenceCheck

DATAPACKAGES_DIR = pathlib.Path(__file__).parent / "datapackages"

dp = Package(DATAPACKAGES_DIR / "simple" / "datapackage.json")

checklist = Checklist(checks=[SequenceReferenceCheck()])
report = dp.validate(checklist=checklist)

if report.valid:
    print("Datapackage is valid!")
else:
    print("Datapackage is invalid!")
    for error in report.flatten(["type", "note"]):
        print(f"[{error[0]}] {error[1]}")