"""Compatibility alias for :mod:`digital_sztu.chat`."""
import sys
from digital_sztu import chat as _implementation
sys.modules[__name__] = _implementation
