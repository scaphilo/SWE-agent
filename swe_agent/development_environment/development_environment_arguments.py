from dataclasses import dataclass
from typing import Optional

from simple_parsing.helpers import FrozenSerializable


@dataclass(frozen=True)
class DevelopmentEnvironmentArguments(FrozenSerializable):
    data_path: str
    image_name: str
    split: str = "dev"
    base_commit: Optional[str] = None  # used only with data_path as url
    container_name: Optional[str] = None
    install_environment: bool = True
    timeout: int = 35
    verbose: bool = False
    no_mirror: bool = False
