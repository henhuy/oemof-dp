
from oemof_dp.bridge import SolphBridge
import os
from oemof.solph import Bus, Model
from oemof.tabular.facades import Conversion, Dispatchable, Link, Load, Storage, Volatile


def test_bridge_with_facades():
    dp_path = "datapackages/foreignkeys/datapackage.json"
    if not os.path.exists(dp_path):
        raise FileNotFoundError(f"Datapackage not found at {dp_path}")

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
    es.results = model.results()


