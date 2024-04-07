from dataclasses import dataclass, fields

from simple_parsing import Serializable


@dataclass
class APIStats(Serializable):
    total_cost: float = 0
    instance_cost: float = 0
    tokens_sent: int = 0
    tokens_received: int = 0
    api_calls: int = 0

    def __add__(self, other):
        if not isinstance(other, APIStats):
            raise TypeError("Can only add APIStats with APIStats")

        return APIStats(**{
            field.name: getattr(self, field.name) + getattr(other, field.name)
            for field in fields(self)
        })

    def replace(self, other):
        if not isinstance(other, APIStats):
            raise TypeError("Can only replace APIStats with APIStats")

        return APIStats(**{
            field.name: getattr(other, field.name)
            for field in fields(self)
        })
