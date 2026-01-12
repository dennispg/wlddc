"""Backend modules for display and brightness control."""

from wlddc.backends.display import (
    DisplayManager,
    WaylandOutput,
    DDCDisplay,
    CorrelatedDisplay,
)
from wlddc.backends.brightness import BrightnessController

__all__ = [
    "DisplayManager",
    "WaylandOutput",
    "DDCDisplay",
    "CorrelatedDisplay",
    "BrightnessController",
]
