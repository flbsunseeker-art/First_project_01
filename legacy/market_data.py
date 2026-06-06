"""Compatibility wrapper for the relocated market data module."""

from __future__ import annotations

import sys

from apps.api.adapters import market_data as _market_data

sys.modules[__name__] = _market_data
