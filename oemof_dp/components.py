from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from oemof.solph import Flow
from oemof.solph.components import Converter

if TYPE_CHECKING:
    from oemof_dp.bridge import SolphBridge


class Reference:
    """Reference to another component by label.

    Created for strings starting with '@' in nested component data.
    Resolves lazily so the bridge's nodes dict can be fully populated before
    any instance is requested.
    """

    def __init__(self, name: str, bridge: "SolphBridge") -> None:
        """Initialize reference.

        Args:
            name: Label of the referenced component (without '@' prefix).
            bridge: The SolphBridge instance that owns the components dict.
        """
        self.name = name
        self._bridge = bridge

    @property
    def instance(self) -> object:
        """Return the solph instance of the referenced component.

        Returns:
            The solph component instance.

        Raises:
            KeyError: If the referenced label is not in bridge.nodes.
        """
        return self._bridge.nodes[self.name].instance


class Component:
    """Base class for oemof.solph components.

    Accepts raw data dicts from both flat (table) and nested (JSON/YAML)
    resources. In nested data, keys or values that start with '@' become
    :class:`Reference` objects; nested dicts that contain a ``type`` key
    become nested :class:`Component` instances. Resolution is lazy: solph
    objects are only created when :attr:`instance` is first accessed.

    The bridge populates its nodes incrementally. Because resolution is lazy,
    forward references resolve correctly as long as all components are
    registered before :attr:`instance` is accessed on any of them.
    """

    def __init__(self, data: dict, bridge: "SolphBridge") -> None:
        """Initialize component.

        Args:
            data: Component data. Must contain a ``type`` key (popped here).
            bridge: The SolphBridge that provides the typemap and nodes dict.
        """
        data = dict(data)
        self._type_str: str = data.pop("type")
        self._bridge = bridge
        self._data: dict = self._process_data(data)
        self._instance_cache: object | None = None

    # ------------------------------------------------------------------
    # Data processing (called once at construction time)
    # ------------------------------------------------------------------

    def _process_key(self, key: str) -> str | Reference:
        if isinstance(key, str) and key.startswith("@"):
            return Reference(key[1:], self._bridge)
        return key

    def _process_value(self, value: object) -> object:
        if isinstance(value, str) and value.startswith("@"):
            return Reference(value[1:], self._bridge)
        if isinstance(value, dict):
            if "type" in value:
                return Component(dict(value), self._bridge)
            return {self._process_key(k): self._process_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._process_value(item) for item in value]
        return value

    def _process_data(self, data: dict) -> dict:
        return {self._process_key(k): self._process_value(v) for k, v in data.items()}

    # ------------------------------------------------------------------
    # Resolution (called lazily when instance is needed)
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(value: object) -> object:
        """Recursively resolve Reference/Component nodes to their solph instances."""
        if isinstance(value, (Reference, Component)):
            return value.instance
        if isinstance(value, dict):
            return {Component._resolve(k): Component._resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [Component._resolve(item) for item in value]
        return value

    def _resolve_data(self) -> dict:
        """Return a copy of _data with all References/Components resolved."""
        return {Component._resolve(k): Component._resolve(v) for k, v in self._data.items()}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def type(self) -> type | None:
        """Return the solph class mapped to this component's type string."""
        return self._bridge.typemap.get(self._type_str)

    @staticmethod
    def _call_solph(solph_class: type, data: dict) -> object:
        """Call solph_class with only the kwargs it accepts.

        Classes inheriting from oemof.network.Node accept ``**kwargs`` and
        receive all data. Classes like :class:`~oemof.solph.flows.Flow` only
        accept specific keyword arguments, so unrecognised keys are filtered out.

        Args:
            solph_class: The solph class to instantiate.
            data: Resolved keyword arguments.

        Returns:
            The newly created solph instance.
        """
        sig = inspect.signature(solph_class)
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        if not has_var_keyword:
            valid = set(sig.parameters)
            data = {k: v for k, v in data.items() if k in valid}
        return solph_class(**data)

    @property
    def instance(self) -> object:
        """Return the solph component instance, creating it on first access.

        Returns:
            The solph component instance (singleton per Component object).

        Raises:
            KeyError: If the type string is not in the bridge's typemap.
        """
        if self._instance_cache is None:
            data = self._resolve_data()
            solph_class = self._bridge.typemap[self._type_str]
            self._instance_cache = self._call_solph(solph_class, data)
        return self._instance_cache


class Dispatchable(Component):
    """Dispatchable generator component.

    Builds a :class:`~oemof.solph.components.Converter` whose single output
    flow is derived from ``bus``, ``capacity``, ``profile`` and
    ``marginal_cost`` entries in the data dict.
    """

    @property
    def type(self) -> type:
        """Return Converter as the solph class for this component."""
        return Converter

    @property
    def instance(self) -> object:
        """Return a Converter solph instance (singleton).

        Returns:
            The solph Converter instance.
        """
        if self._instance_cache is None:
            resolved = self._resolve_data()
            label = resolved["label"]
            bus = resolved["bus"]
            capacity = resolved["capacity"]
            profile = resolved["profile"]
            marginal_cost = resolved["marginal_cost"]
            outputs = {
                bus: Flow(
                    nominal_capacity=capacity,
                    variable_costs=marginal_cost,
                    max=profile,
                )
            }
            self._instance_cache = Converter(label=label, outputs=outputs)
        return self._instance_cache
