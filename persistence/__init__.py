"""
Persistence layer for list crawl state.

This package provides state management for list crawl mode,
with support for JSON-based storage and future SQLite migration.
"""

from .list_crawl_state import JSONStateStore, StateStore

__all__ = ['JSONStateStore', 'StateStore']

