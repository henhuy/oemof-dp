from typing import Any, Dict, List, Optional, Union, Sequence
from pydantic import BaseModel, Field

# Define a type for attributes that can be a single value or a sequence
# Using float as a common base for numerical values, but can be Any if needed.
MaybeSequence = Union[float, Sequence[float]]

class NodeModel(BaseModel):
    label: Optional[Union[str, tuple]] = None
    parent_node: Optional[Any] = None
    custom_properties: Optional[Dict[str, Any]] = Field(default_factory=dict)

class NodeInOutModel(NodeModel):
    inputs: Optional[Dict[BusModel, FlowModel]] = Field(default_factory=dict)
    outputs: Optional[Dict[Any, Any]] = Field(default_factory=dict)

class BusModel(NodeInOutModel):
    balanced: bool = True

class ConverterInOutModel(NodeInOutModel):
    conversion_factors: Optional[Dict[Any, MaybeSequence]] = Field(default_factory=dict)

class ExtractionTurbineCHPModel(ConverterInOutModel):
    conversion_factor_full_condensation: Dict[Any, MaybeSequence]

class GenericCHPInOutModel(NodeInOutModel):
    fuel_input: Dict[Any, Any]
    electrical_output: Dict[Any, Any]
    heat_output: Dict[Any, Any]
    beta: MaybeSequence
    back_pressure: bool

class GenericStorageInOutModel(NodeInOutModel):
    nominal_capacity: Optional[Union[float, Any]] = None
    nominal_storage_capacity: Optional[float] = None  # Deprecated but kept for compatibility
    initial_storage_level: Optional[float] = None
    invest_relation_input_output: Optional[MaybeSequence] = None
    invest_relation_input_capacity: Optional[MaybeSequence] = None
    invest_relation_output_capacity: Optional[MaybeSequence] = None
    min_storage_level: MaybeSequence = 0
    max_storage_level: MaybeSequence = 1
    balanced: bool = True
    loss_rate: MaybeSequence = 0
    fixed_losses_relative: MaybeSequence = 0
    fixed_losses_absolute: MaybeSequence = 0
    inflow_conversion_factor: MaybeSequence = 1
    outflow_conversion_factor: MaybeSequence = 1
    fixed_costs: MaybeSequence = 0
    storage_costs: Optional[MaybeSequence] = None
    lifetime_inflow: Optional[int] = None
    lifetime_outflow: Optional[int] = None

class LinkInOutModel(NodeInOutModel):
    conversion_factors: Optional[Dict[Any, MaybeSequence]] = Field(default_factory=dict)

class OffsetConverterInOutModel(NodeInOutModel):
    conversion_factors: Optional[Dict[Any, MaybeSequence]] = None
    normed_offsets: Optional[Dict[Any, MaybeSequence]] = None
    coefficients: Optional[Dict[Any, MaybeSequence]] = None

class SinkInOutModel(NodeInOutModel):
    inputs: Dict[Any, Any]

class SourceInOutModel(NodeInOutModel):
    outputs: Dict[Any, Any]

class FlowModel(BaseModel):
    nominal_capacity: Optional[Union[float, Any]] = None
    variable_costs: MaybeSequence = 0
    minimum: MaybeSequence = 0
    maximum: MaybeSequence = 1
    fix: Optional[MaybeSequence] = None
    positive_gradient_limit: Optional[MaybeSequence] = None
    negative_gradient_limit: Optional[MaybeSequence] = None
    full_load_time_max: Optional[float] = None
    full_load_time_min: Optional[float] = None
    integer: bool = False
    nonconvex: Optional[Any] = None
    lifetime: Optional[int] = None
    age: Optional[int] = None
    fixed_costs: MaybeSequence = 0
    custom_properties: Optional[Dict[str, Any]] = Field(default_factory=dict)
