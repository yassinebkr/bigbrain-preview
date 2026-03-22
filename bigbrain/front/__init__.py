"""Front Brain package - User-facing layer with focus management for BigBrain."""

from .front_brain import FrontBrain
from .focus_manager import FocusManager, FocusMode, FocusState

__all__ = ["FrontBrain", "FocusManager", "FocusMode", "FocusState"]