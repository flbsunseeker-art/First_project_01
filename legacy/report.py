"""Compatibility wrapper for the relocated report service."""

from __future__ import annotations

import sys

from apps.api.services import report as _report

sys.modules[__name__] = _report
