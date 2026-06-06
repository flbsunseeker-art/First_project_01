"""Compatibility wrapper for the relocated valuation module."""

from __future__ import annotations

import sys

from apps.api.services import valuation as _valuation

sys.modules[__name__] = _valuation
