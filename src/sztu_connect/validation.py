"""Compatibility alias for :mod:`digital_sztu.validation`."""
import sys
from digital_sztu import validation as _implementation
sys.modules[__name__] = _implementation
