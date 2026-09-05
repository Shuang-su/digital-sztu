"""Compatibility alias for :mod:`digital_sztu.utils`."""
import sys
from digital_sztu import utils as _implementation
sys.modules[__name__] = _implementation
