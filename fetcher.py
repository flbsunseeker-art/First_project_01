"""Compatibility wrapper for the relocated live data fetcher."""

from __future__ import annotations

import sys

from apps.api.adapters import fetcher as _fetcher

sys.modules[__name__] = _fetcher
