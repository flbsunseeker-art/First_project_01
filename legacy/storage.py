"""Compatibility wrapper for the relocated storage module."""

from __future__ import annotations

import sys

from apps.api.repositories import storage as _storage

sys.modules[__name__] = _storage
