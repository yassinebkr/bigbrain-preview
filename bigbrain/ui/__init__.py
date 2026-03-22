"""UI package - Terminal user interface for BigBrain."""

from .ui_adapter import UIAdapter
from .rich_adapter import RichAdapter

__all__ = ["UIAdapter", "RichAdapter"]