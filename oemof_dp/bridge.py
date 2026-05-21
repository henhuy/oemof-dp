import os
import warnings
import yaml
from decimal import Decimal
from typing import Any, Dict, List, Union

import pandas as pd
from frictionless import Checklist, Package, Resource, Row
from frictionless.resources import JsonResource
from oemof.solph import Bus, EnergySystem, Flow
from oemof.solph.components import Sink, Source

from oemof_dp.checks import SequenceReferenceCheck
from oemof_dp.components import Node

DEFAULT_TYPEMAP = {
    "bus": Bus,
    "flows": Flow,
    "source": Source,
    "sink": Sink,
}


class SolphBridge:
    def __init__(self, typemap: dict = None):
        self.package = None
        self.es = None
        self.typemap = typemap or DEFAULT_TYPEMAP
        self.nodes: Dict[str, Node] = {}
        self.flows: List[Node] = []
        self.sequences: Dict[str, pd.DataFrame] = {}

    @classmethod
    def from_datapackage(cls, path: str, typemap: dict = None):
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
    def from_energysystem(cls, es: EnergySystem, typemap: dict = None):
        bridge = cls(typemap)
        bridge.es = es
        raise NotImplementedError("This feature is not yet implemented.")

    def _load_sequences(self):
        for resource in self.package.resources:
            if "sequences" in resource.path:
                df = resource.to_pandas()
                # Ensure all columns with Decimal are converted to float
                for col in df.columns:
                    if df[col].dtype == object:
                        df[col] = df[col].apply(lambda x: float(x) if isinstance(x, Decimal) else x)

                # If timeindex is present, set it as index
                if "timeindex" in df.columns:
                    df.set_index("timeindex", inplace=True)
                self.sequences[resource.name] = df

    def _get_sequence(self, resource_name: str, sequence_name: str) -> Union[pd.Series, None]:
        """Return sequence from preloaded sequences in the datapackage."""
        if sequence_name is None:
            return None
        if resource_name not in self.sequences:
            raise KeyError(f"Resource '{resource_name}' not found in datapackage.")
        if sequence_name not in self.sequences[resource_name]:
            raise KeyError(f"Sequence '{sequence_name}' not found in resource '{resource_name}'.")
        return self.sequences[resource_name][sequence_name]

    def _add_sequences_to_data(self, sequence_keys: list, data: dict) -> dict:
        """Adds sequences to data based on referenced sequence keys."""
        for sequence_ref in sequence_keys:
            field_name = sequence_ref["field"]
            sequence_name = data[field_name]
            if sequence_name is None:
                continue
            sequence = self._get_sequence(sequence_ref["reference"], sequence_name)
            # Replace reference name with actual sequence
            data[field_name] = sequence
        return data

    def _resolve_references(self, foreign_keys: list[dict[str, str]], data: dict) -> dict:
        """Replace references in data with related nodes."""
        for reference in foreign_keys:
            field_name = reference["fields"][0]
            ref_name = data[field_name]
            # Replace reference name with actual bus
            data[field_name] = self.nodes[ref_name]
        return data

    @staticmethod
    def _get_label(data: dict) -> str:
        """Get label from node."""
        if "label" not in data:
            if "name" in data:
                warnings.warn("Node label should be defined by key 'label' not 'name'.")
                data["label"] = data.pop("name")
                return data["label"]
            raise KeyError("Key 'label' or 'name' not found in data.")
        return data["label"]

    @staticmethod
    def _convert_decimal_to_float(data: Any) -> Any:
        """Recursively convert Decimal to float in data structures."""
        if isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, dict):
            return {k: SolphBridge._convert_decimal_to_float(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [SolphBridge._convert_decimal_to_float(v) for v in data]
        return data

    def _load_node_instance(self, resource: Resource, row: dict) -> tuple[str, Node]:
        data = self._convert_decimal_to_float(row)
        node_type = data.pop("type")
        label = self._get_label(data)
        data = self._resolve_references(resource.schema.foreign_keys, data)
        sequence_keys = resource.schema.custom.get("sequenceKeys", [])
        data = self._add_sequences_to_data(sequence_keys, data)
        if node_type in self.typemap and issubclass(self.typemap[node_type], Node):
            node_class = self.typemap[node_type]
            node = node_class(data=data)
        else:
            node_class = Node
            node = node_class(type=self.typemap[node_type], data=data)
        return label, node

    def _load_specific_components(self, component_type: str):
        """
        Load components of specific type

        This is needed to preload buses and flows.
        """
        for resource in self.package.resources:
            if "sequences" in resource.path:
                continue

            rows = resource.read_json() if isinstance(resource, JsonResource) else resource.read_rows()
            for row in rows:
                if row["type"] != component_type:
                    continue
                label, bus = self._load_node_instance(resource, row)
                self.nodes[label] = bus

    def _load_components(self):
        """Load components (Sinks, Sources, Transformers)"""
        for resource in self.package.resources:
            if resource.name not in ["bus", "flows"] and not resource.name.endswith("_profile"):
                rows = resource.read_json() if isinstance(resource, JsonResource) else resource.read_rows()
                for row in rows:
                    data = row.to_dict() if isinstance(row, Row) else row
                    label, node = self._load_node_instance(resource, data)
                    self.nodes[label] = node

    def build_energysystem(self) -> EnergySystem:
        # Determine timeindex from sequences if available
        timeindex = None
        if self.sequences:
            # Take first one
            first_seq = next(iter(self.sequences.values()))
            timeindex = first_seq.index
        
        es = EnergySystem(timeindex=timeindex)
            
        # 2. Create all Nodes
        for node in self.nodes.values():
            # Skip flows as those are already added to the es by components
            if node.type == Flow:
                continue
            # TODO: What's with subnodes?
            es.add(node.instance)
            
        self.es = es
        return es

    def build_datapackage(self):
        # To be implemented
        pass
