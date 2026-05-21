import warnings
from decimal import Decimal
from typing import Any, Dict, List, Union

import pandas as pd
from frictionless import Checklist, Package, Resource, Row
from frictionless.resources import JsonResource
from oemof.solph import Bus, EnergySystem, Flow
from oemof.solph.components import Sink, Source

from oemof_dp.checks import SequenceReferenceCheck
from oemof_dp.components import Component

DEFAULT_TYPEMAP = {
    "bus": Bus,
    "flows": Flow,
    "source": Source,
    "sink": Sink,
}


class SolphBridge:
    def __init__(self, typemap: dict | None = None) -> None:
        self.package: Package | None = None
        self.es: EnergySystem | None = None
        self.typemap: dict = typemap or DEFAULT_TYPEMAP
        self.nodes: Dict[str, Component] = {}
        self.flows: List[Component] = []
        self.sequences: Dict[str, pd.DataFrame] = {}

    @classmethod
    def from_datapackage(cls, path: str, typemap: dict | None = None) -> "SolphBridge":
        """Load a datapackage and prepare the bridge for energy system construction.

        Args:
            path: Path to the datapackage.json file.
            typemap: Optional mapping from type strings to solph classes or
                     Component subclasses. Defaults to DEFAULT_TYPEMAP.

        Returns:
            A configured SolphBridge instance.

        Raises:
            RuntimeError: If the datapackage validation fails.
        """
        bridge = cls(typemap)
        bridge.package = Package(path)
        checklist = Checklist(checks=[SequenceReferenceCheck()])
        report = bridge.package.validate(checklist=checklist)
        if not report.valid:
            raise RuntimeError("Invald datapackage", report.errors)
        bridge._load_sequences()
        bridge._load_specific_components("flow")
        bridge._load_specific_components("bus")
        bridge._load_components()
        return bridge

    @classmethod
    def from_energysystem(cls, es: EnergySystem, typemap: dict | None = None) -> "SolphBridge":
        """Create a bridge from an existing EnergySystem (not yet implemented).

        Args:
            es: An oemof.solph EnergySystem.
            typemap: Optional typemap override.

        Returns:
            A SolphBridge wrapping the existing energy system.

        Raises:
            NotImplementedError: Always, as this feature is not yet implemented.
        """
        bridge = cls(typemap)
        bridge.es = es
        raise NotImplementedError("This feature is not yet implemented.")

    def _load_sequences(self) -> None:
        for resource in self.package.resources:
            if "sequences" in resource.path:
                df = resource.to_pandas()
                for col in df.columns:
                    if df[col].dtype == object:
                        df[col] = df[col].apply(
                            lambda x: float(x) if isinstance(x, Decimal) else x
                        )
                if "timeindex" in df.columns:
                    df.set_index("timeindex", inplace=True)
                self.sequences[resource.name] = df

    def _get_sequence(self, resource_name: str, sequence_name: str) -> Union[pd.Series, None]:
        """Return a sequence column from the preloaded sequences.

        Args:
            resource_name: Name of the sequence resource.
            sequence_name: Column name within that resource.

        Returns:
            The sequence as a pandas Series, or None if sequence_name is None.

        Raises:
            KeyError: If the resource or column is not found.
        """
        if sequence_name is None:
            return None
        if resource_name not in self.sequences:
            raise KeyError(f"Resource '{resource_name}' not found in datapackage.")
        if sequence_name not in self.sequences[resource_name]:
            raise KeyError(
                f"Sequence '{sequence_name}' not found in resource '{resource_name}'."
            )
        return self.sequences[resource_name][sequence_name]

    def _add_sequences_to_data(self, sequence_keys: list, data: dict) -> dict:
        """Replace sequence reference strings with actual pd.Series from sequences.

        Args:
            sequence_keys: List of ``{field, reference}`` dicts from the schema.
            data: The row data dict to update in place.

        Returns:
            The updated data dict.
        """
        for sequence_ref in sequence_keys:
            field_name = sequence_ref["field"]
            sequence_name = data[field_name]
            if sequence_name is None:
                continue
            # Strip leading '@' used as a reference convention in YAML sources
            if isinstance(sequence_name, str) and sequence_name.startswith("@"):
                sequence_name = sequence_name[1:]
            sequence = self._get_sequence(sequence_ref["reference"], sequence_name)
            data[field_name] = sequence
        return data

    def _resolve_references(self, foreign_keys: list[dict], data: dict) -> dict:
        """Replace foreign-key fields with the referenced Component objects.

        Args:
            foreign_keys: Normalized foreign-key descriptors from the schema.
            data: The row data dict to update in place.

        Returns:
            The updated data dict.
        """
        for reference in foreign_keys:
            field_name = reference["fields"][0]
            ref_name = data[field_name]
            # Strip leading '@' used as a reference convention in YAML sources
            if isinstance(ref_name, str) and ref_name.startswith("@"):
                ref_name = ref_name[1:]
            data[field_name] = self.nodes[ref_name]
        return data

    @staticmethod
    def _get_label(data: dict) -> str:
        """Return the label from data, renaming 'name' to 'label' if needed.

        Args:
            data: Row data dict (modified in place when 'name' is renamed).

        Returns:
            The label string.

        Raises:
            KeyError: If neither 'label' nor 'name' key is present.
        """
        if "label" not in data:
            if "name" in data:
                warnings.warn("Node label should be defined by key 'label' not 'name'.")
                data["label"] = data.pop("name")
                return data["label"]
            raise KeyError("Key 'label' or 'name' not found in data.")
        return data["label"]

    @staticmethod
    def _convert_decimal_to_float(data: Any) -> Any:
        """Recursively convert Decimal values to float.

        Args:
            data: Any value; dicts and lists are traversed recursively.

        Returns:
            The same structure with Decimal values replaced by float.
        """
        if isinstance(data, Decimal):
            return float(data)
        if isinstance(data, dict):
            return {k: SolphBridge._convert_decimal_to_float(v) for k, v in data.items()}
        if isinstance(data, list):
            return [SolphBridge._convert_decimal_to_float(v) for v in data]
        return data

    def _load_node_instance(self, resource: Resource, row: Any) -> tuple[str, Component]:
        """Create a Component (or subclass) from a row dict or frictionless Row.

        For table resources, foreign-key and sequence references are resolved
        by the bridge using schema metadata. For JSON resources the Component
        class handles '@'-prefixed references internally.

        Args:
            resource: The frictionless Resource the row came from.
            row: A frictionless Row or plain dict.

        Returns:
            A (label, component) tuple.
        """
        data = self._convert_decimal_to_float(row)

        # Ensure data has 'label' key (may rename from 'name')
        label = self._get_label(data)

        # For flat/table resources the bridge resolves references via schema metadata
        if resource.type == "table":
            data = self._resolve_references(resource.schema.foreign_keys, data)
            sequence_keys = resource.schema.custom.get("sequenceKeys", [])
            data = self._add_sequences_to_data(sequence_keys, data)

        # If the typemap provides a Component subclass for this type, use it;
        # otherwise fall back to the generic Component.
        node_type_str = data.get("type")
        mapped_class = self.typemap.get(node_type_str)
        if (
            mapped_class is not None
            and isinstance(mapped_class, type)
            and issubclass(mapped_class, Component)
        ):
            node: Component = mapped_class(data, self)
        else:
            node = Component(data, self)

        return label, node

    def _load_specific_components(self, component_type: str) -> None:
        """Load components of a specific type (e.g. 'bus' or 'flow') first.

        Pre-loading buses and flows ensures that other components can reference
        them via foreign keys or '@'-prefixed References.

        Args:
            component_type: The ``type`` value to filter on.
        """
        for resource in self.package.resources:
            if "sequences" in resource.path:
                continue

            rows = (
                resource.read_json()
                if isinstance(resource, JsonResource)
                else resource.read_rows()
            )
            for row in rows:
                if row["type"] != component_type:
                    continue
                label, component = self._load_node_instance(resource, row)
                self.nodes[label] = component

    def _load_components(self) -> None:
        """Load all remaining components (sinks, sources, converters, etc.)."""
        for resource in self.package.resources:
            if resource.name not in ["bus", "flows"] and not resource.name.endswith(
                "_profile"
            ):
                rows = (
                    resource.read_json()
                    if isinstance(resource, JsonResource)
                    else resource.read_rows()
                )
                for row in rows:
                    data = row.to_dict() if isinstance(row, Row) else row
                    label, node = self._load_node_instance(resource, data)
                    self.nodes[label] = node

    def build_energysystem(self) -> EnergySystem:
        """Build and return an oemof.solph EnergySystem from loaded components.

        Returns:
            A populated EnergySystem with all non-flow nodes added.
        """
        timeindex = None
        if self.sequences:
            first_seq = next(iter(self.sequences.values()))
            timeindex = first_seq.index

        es = EnergySystem(timeindex=timeindex)

        for node in self.nodes.values():
            # Flows are attached to nodes implicitly; adding them separately
            # would duplicate them in the energy system graph.
            if node.type == Flow:
                continue
            es.add(node.instance)

        self.es = es
        return es

    def build_datapackage(self) -> None:
        """Export the energy system back to a datapackage (not yet implemented)."""
        pass
