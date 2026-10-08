"""Jeddah-only batch orchestration.

This package intentionally contains only site-specific orchestration and styling.
Existing G File Studio engines/processors remain untouched and are reused as-is.
"""

from .batch_processor import JeddahBatchSettings, process_jeddah_batch

__all__ = ["JeddahBatchSettings", "process_jeddah_batch"]
