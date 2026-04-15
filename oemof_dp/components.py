
from pydantic import BaseModel, ConfigDict, computed_field, Field, model_serializer

from oemof.network import Node as SolphNode
from oemof.solph import Flow
from oemof.solph.components import Converter
import pandas as pd
from typing import Type


class DataModel(BaseModel):
    # This allows arbitrary data
    model_config = ConfigDict(extra='allow')


class Node(BaseModel):
    """Base class for all oemof.solph nodes."""
    type: Type[SolphNode]  # e.g., 'source', 'sink', 'transformer'
    data: DataModel  # Component data to init oemof.solph component

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _instance = None

    @computed_field
    @property
    def instance(self) -> SolphNode:
        if self._instance is None:
            data = self.data.model_dump()
            self._instance = self.type(**data)
        return self._instance

    @model_serializer
    def ser_model(self) -> SolphNode:
        # This resolves references in other models to return solph instance
        return self.instance



class DispatchableDataModel(BaseModel):
    bus: Node = Field(exclude=True)
    capacity: float = Field(exclude=True)
    profile: pd.Series = Field(exclude=True)
    marginal_cost: pd.Series = Field(exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @computed_field
    @property
    def outputs(self) -> dict:
        f = Flow(
            nominal_capacity=self.capacity,
            variable_costs=self.marginal_cost,
            max=self.profile,
        )
        return {self.bus.instance: f}


class Dispatchable(Node):
    type: Type[SolphNode] = Converter
    data: DispatchableDataModel
