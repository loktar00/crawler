"""
State management for list crawl mode.

Provides persistence for seen pages, seen items, and append-only logs.
Designed with an abstract interface to allow future SQLite migration.
"""

from typing import Protocol, Set, Dict, Any, Optional
from pathlib import Path
import json
import time
from datetime import datetime


class StateStore(Protocol):
    """
    Abstract interface for state storage.

    This allows us to swap implementations (JSON -> SQLite) without
    changing the ListCrawler code.
    """

    def has_seen_list_page(self, url: str) -> bool:
        """Check if a list page URL has been visited."""
        ...

    def mark_list_page_seen(self, url: str) -> None:
        """Mark a list page URL as visited."""
        ...

    def has_seen_item(self, url: str) -> bool:
        """Check if an item URL has been discovered."""
        ...

    def add_item(self, url: str, text: str, source_page: str) -> None:
        """Add an item to the seen set and log."""
        ...

    def append_list_page_log(self, url: str, status: str,
                            items_found: int, pagination_found: int) -> None:
        """Append an entry to the list pages log."""
        ...

    def get_seen_list_pages_count(self) -> int:
        """Get count of seen list pages."""
        ...

    def get_seen_items_count(self) -> int:
        """Get count of seen items."""
        ...

    def save(self) -> None:
        """Persist state to disk."""
        ...


class JSONStateStore:
    """
    JSON-based implementation of StateStore.

    Uses JSON files for sets and JSONL for append-only logs.
    """

    def __init__(self, output_dir: str = "output"):
        """
        Initialize the JSON state store.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # State files
        self.seen_list_pages_file = self.output_dir / "seen_list_pages.json"
        self.seen_item_links_file = self.output_dir / "seen_item_links.json"
        self.list_pages_log_file = self.output_dir / "list_pages.jsonl"
        self.items_log_file = self.output_dir / "items.jsonl"

        # In-memory sets
        self.seen_list_pages: Set[str] = set()
        self.seen_item_links: Set[str] = set()

        # Load existing state
        self._load_state()

    def _load_state(self) -> None:
        """Load existing state from disk."""
        # Load seen list pages
        if self.seen_list_pages_file.exists():
            try:
                with open(self.seen_list_pages_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.seen_list_pages = set(data)
            except Exception as e:
                print(f"Warning: Could not load seen_list_pages: {e}")

        # Load seen item links
        if self.seen_item_links_file.exists():
            try:
                with open(self.seen_item_links_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.seen_item_links = set(data)
            except Exception as e:
                print(f"Warning: Could not load seen_item_links: {e}")

    def has_seen_list_page(self, url: str) -> bool:
        """Check if a list page URL has been visited."""
        return url in self.seen_list_pages

    def mark_list_page_seen(self, url: str) -> None:
        """Mark a list page URL as visited."""
        self.seen_list_pages.add(url)

    def has_seen_item(self, url: str) -> bool:
        """Check if an item URL has been discovered."""
        return url in self.seen_item_links

    def add_item(self, url: str, text: str, source_page: str) -> None:
        """
        Add an item to the seen set and log.

        Args:
            url: Item URL
            text: Link text
            source_page: URL of the list page where this was found
        """
        # Skip if already seen
        if url in self.seen_item_links:
            return

        self.seen_item_links.add(url)

        # Append to items log
        entry = {
            'url': url,
            'text': text,
            'source_page': source_page,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        with open(self.items_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

    def append_list_page_log(self, url: str, status: str,
                            items_found: int, pagination_found: int) -> None:
        """
        Append an entry to the list pages log.

        Args:
            url: List page URL
            status: Status (e.g., 'success', 'error')
            items_found: Number of item links found
            pagination_found: Number of pagination links found
        """
        entry = {
            'url': url,
            'status': status,
            'items_found': items_found,
            'pagination_found': pagination_found,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

        with open(self.list_pages_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

    def get_seen_list_pages_count(self) -> int:
        """Get count of seen list pages."""
        return len(self.seen_list_pages)

    def get_seen_items_count(self) -> int:
        """Get count of seen items."""
        return len(self.seen_item_links)

    def save(self) -> None:
        """Persist state to disk."""
        # Save seen list pages
        with open(self.seen_list_pages_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.seen_list_pages), f, indent=2)

        # Save seen item links
        with open(self.seen_item_links_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.seen_item_links), f, indent=2)

    def clear(self) -> None:
        """Clear all state (useful for --force flag)."""
        self.seen_list_pages.clear()
        self.seen_item_links.clear()

        # Optionally delete files
        for file in [self.seen_list_pages_file, self.seen_item_links_file]:
            if file.exists():
                file.unlink()

