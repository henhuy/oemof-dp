import warnings
from decimal import Decimal
from typing import Any, Dict, List, Union

import pandas as pd
from frictionless import Checklist, Package, Resource, Row
from oemof.network import Node as SolphNode
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
        self.buses: Dict[str, Node] = {}
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
        bridge._load_buses()
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
            sequence_name = data[sequence_ref["field"]]
            sequence = self._get_sequence(sequence_ref["reference"], sequence_name)
            # Replace reference name with actual sequence
            data[sequence_ref["field"]] = sequence
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

    def _load_node_instance(self, resource: Resource, row: Row):
        data = row.to_dict()
        data = self._convert_decimal_to_float(data)
        node_type = data.pop("type")
        label = self._get_label(data)
        foreign_keys = resource.schema.foreign_keys
        sequence_keys = resource.schema.custom.get("sequenceKeys", [])
        node = Node(type=node_type, foreign_keys=foreign_keys, sequence_keys=sequence_keys, data=data)
        return label, node

    def _load_buses(self):
        """Load buses"""
        for resource in self.package.resources:
            if "sequences" in resource.path:
                continue
            
            for row in resource.read_rows():
                if row["type"] != "bus":
                    continue
                label, bus = self._load_node_instance(resource, row)
                self.buses[label] = bus

    def _load_components(self):
        """Load components (Sinks, Sources, Transformers)"""
        for resource in self.package.resources:
            if resource.name not in ["bus", "flows"] and not resource.name.endswith("_profile"):
                for row in resource.read_rows():
                    label, node = self._load_node_instance(resource, row)
                    self.nodes[label] = node


    def build_energysystem(self) -> EnergySystem:
        def add_buses_to_data(foreign_keys: list[dict[str, str]], data: dict) -> dict:
            """Replace bus references in data with actual buses."""
            for bus_ref in foreign_keys:
                bus_name = data[bus_ref["fields"][0]]
                # Replace reference name with actual bus
                data[bus_ref["fields"][0]] = solph_buses[bus_name]
            return data

        def build_solph_component(node: Node) -> SolphNode:
            """Build solph component using API node."""
            if node.type not in self.typemap:
                raise KeyError(f"Node type '{node.type}' not found in typemap.")
            solph_component = self.typemap[node.type]
            data = add_buses_to_data(node.foreign_keys, node.data)
            data = self._add_sequences_to_data(node.sequence_keys, data)
            return solph_component(**data)

        # Determine timeindex from sequences if available
        timeindex = None
        if self.sequences:
            # Take first one
            first_seq = next(iter(self.sequences.values()))
            timeindex = first_seq.index
        
        es = EnergySystem(timeindex=timeindex)
        
        # 1. Create Solph Buses
        solph_buses = {}
        for label, bus_internal in self.buses.items():
            bus = build_solph_component(bus_internal)
            solph_buses[label] = bus
            es.add(bus)
            
        # 2. Create Solph Nodes
        for node_internal in self.nodes.values():
            node = build_solph_component(node_internal)
            es.add(node)
            
        self.es = es
        return es

    def build_datapackage(self):
        # To be implemented
        pass
