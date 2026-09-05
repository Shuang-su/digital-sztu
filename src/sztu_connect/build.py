"""Compatibility alias for :mod:`digital_sztu.build`."""
import sys
from digital_sztu import build as _implementation
sys.modules[__name__] = _implementation
