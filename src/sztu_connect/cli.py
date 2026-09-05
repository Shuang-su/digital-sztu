"""Compatibility alias for :mod:`digital_sztu.cli`."""
import sys
from digital_sztu import cli as _implementation
sys.modules[__name__] = _implementation
