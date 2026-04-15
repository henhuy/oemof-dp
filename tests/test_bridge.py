
from oemof_dp.bridge import SolphBridge
import os
from oemof.solph import Bus, Model, processing
from oemof.tabular.facades import Conversion, Dispatchable, Link, Load, Storage, Volatile
from oemof_dp.components import Dispatchable as DispatchableNode


def test_bridge_with_facades():
    dp_path = "datapackages/foreignkeys/datapackage.json"
    if not os.path.exists(dp_path):
        raise FileNotFoundError(f"Datapackage not found at {dp_path}")

    # Only tabular facades used (expect of Bus)
    typemap = {
        "bus": Bus,
        "conversion": Conversion,
        "dispatchable": Dispatchable,
        "link": Link,
        "load": Load,
        "storage": Storage,
        "volatile": Volatile,
    }

    bridge = SolphBridge.from_datapackage(dp_path, typemap)
    es = bridge.build_energysystem()

    print(f"EnergySystem built with {len(es.nodes)} nodes.")
    for node in es.nodes:
        print(f" - Node: {node.label} ({type(node).__name__})")
        if hasattr(node, 'inputs'):
            for i in node.inputs:
                print(f"   <- Input from {i.label}")
        if hasattr(node, 'outputs'):
            for o in node.outputs:
                print(f"   -> Output to {o.label}")

    model = Model(es)
    model.solve("cbc")
    es.results = processing.convert_keys_to_strings(model.results())
    print(es.results)


def test_bridge_with_custom_base_models():
    dp_path = "datapackages/foreignkeys/datapackage.json"
    if not os.path.exists(dp_path):
        raise FileNotFoundError(f"Datapackage not found at {dp_path}")

    typemap = {
        "bus": Bus,
        "conversion": Conversion,
        "dispatchable": DispatchableNode,  # <-- This is a pydantic model instead of Facade
        "link": Link,
        "load": Load,
        "storage": Storage,
        "volatile": Volatile,
    }

    bridge = SolphBridge.from_datapackage(dp_path, typemap)
    es = bridge.build_energysystem()

    print(f"EnergySystem built with {len(es.nodes)} nodes.")
    for node in es.nodes:
        print(f" - Node: {node.label} ({type(node).__name__})")
        if hasattr(node, 'inputs'):
            for i in node.inputs:
                print(f"   <- Input from {i.label}")
        if hasattr(node, 'outputs'):
            for o in node.outputs:
                print(f"   -> Output to {o.label}")

    model = Model(es)
    model.solve("cbc")
    es.results = processing.convert_keys_to_strings(model.results())
    print(es.results)


