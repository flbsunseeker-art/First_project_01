"""Compatibility wrapper for the relocated ledger module."""

from __future__ import annotations

import sys

from apps.api.domain import ledger as _ledger

sys.modules[__name__] = _ledger
