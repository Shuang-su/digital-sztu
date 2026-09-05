"""Compatibility alias for :mod:`digital_sztu.ingest`."""
import sys
from digital_sztu import ingest as _implementation
sys.modules[__name__] = _implementation
