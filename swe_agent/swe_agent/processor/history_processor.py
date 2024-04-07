from abc import abstractmethod
from dataclasses import dataclass


class HistoryProcessorMeta(type):
    _registry = {}

    def __new__(cls, name, bases, attrs):
        new_cls = super().__new__(cls, name, bases, attrs)
        if name != "HistoryProcessor":
            cls._registry[name] = new_cls
        return new_cls


@dataclass
class HistoryProcessor(metaclass=HistoryProcessorMeta):
    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def __call__(self, history: list[str]) -> list[str]:
        raise NotImplementedError

    @classmethod
    def get(cls, name, *args, **kwargs):
        try:
            return cls._registry[name](*args, **kwargs)
        except KeyError:
            raise ValueError(f"Model output parser ({name}) not found.")


class DefaultHistoryProcessor(HistoryProcessor):
    def __call__(self, history):
        return history


class FormatError(Exception):
    pass
