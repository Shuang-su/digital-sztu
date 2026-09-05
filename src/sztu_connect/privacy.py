"""Compatibility alias for :mod:`digital_sztu.privacy`."""
import sys
from digital_sztu import privacy as _implementation
sys.modules[__name__] = _implementation
