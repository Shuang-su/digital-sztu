"""Compatibility alias for :mod:`digital_sztu.knowledge`."""
import sys
from digital_sztu import knowledge as _implementation
sys.modules[__name__] = _implementation
