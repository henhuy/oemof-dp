
from pydantic import BaseModel


class Node(BaseModel):
    """Base class for all oemof.solph nodes."""
    type: str  # e.g., 'source', 'sink', 'transformer'
    foreign_keys: list[dict]
    sequence_keys: list[dict]
    data: dict  # Component data to init oemof.solph component
