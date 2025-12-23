"""
List Crawler - Recipe-driven paginated list crawling.

This module implements the list crawl mode, which:
1. Loads a recipe defining how to extract item links from list pages
2. Follows pagination to discover all list pages
3. Extracts and deduplicates item links
4. Persists state for resume capability
"""

import logging
from typing import Optional, Set
from collections import deque
from pathlib import Path

from recipe_loader import Recipe, load_recipe, validate_recipe
from persistence.list_crawl_state import JSONStateStore
from extractors.list_page import (
    extract_item_links,
    extract_pagination_links,
    canonicalize,
    get_selector_match_count
)
from crawler import WebCrawler

logger = logging.getLogger(__name__)


class ListCrawler:
    """
    Recipe-driven list crawler.

    Crawls paginated list pages and extracts item links according to
    a recipe configuration.
    """

    def __init__(self, recipe: Recipe, headless: Optional[bool] = None,
                 dry_run: bool = False, verbose_selectors: bool = False,
                 force: bool = False):
        """
        Initialize the list crawler.

        Args:
            recipe: Recipe configuration
            headless: Run browser in headless mode (None = use config default)
            dry_run: Print discovered links without saving
            verbose_selectors: Log match counts for CSS selectors
            force: Ignore seen_list_pages and reprocess
        """
        self.recipe = recipe
        self.dry_run = dry_run
        self.verbose_selectors = verbose_selectors
        self.force = force

        # Initialize state store
        output_dir = Path(recipe.output.items_jsonl).parent
        self.state = JSONStateStore(str(output_dir))

        # Clear state if force flag is set
        if force:
            logger.info("Force flag set - clearing existing state")
            self.state.clear()

        # Initialize queue with start URLs
        self.queue = deque()
        for url in recipe.start_urls:
            canonical_url = canonicalize(url)
            self.queue.append(canonical_url)

        # Track URLs in current queue to avoid duplicates
        self.queued_urls: Set[str] = set(recipe.start_urls)

        # Initialize browser (reuse WebCrawler's browser logic)
        self.web_crawler = WebCrawler(
            start_urls=[],
            max_depth=0,
            headless=headless
        )

        # Statistics
        self.stats = {
            'list_pages_visited': 0,
            'list_pages_skipped': 0,
            'items_discovered': 0,
            'pagination_links_found': 0
        }

    def _fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch a page using Playwright.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        response = self.web_crawler.fetch_page(url)
        if response:
            return response.text
        return None

    def _enqueue_pagination_links(self, links: list, base_url: str) -> None:
        """
        Add pagination links to the queue (with deduplication).

        Args:
            links: List of pagination URLs
            base_url: Base URL for logging
        """
        new_links = 0
        for link in links:
            canonical_link = canonicalize(link)

            # Skip if already queued or seen
            if canonical_link in self.queued_urls:
                continue

            if self.state.has_seen_list_page(canonical_link):
                continue

            self.queue.append(canonical_link)
            self.queued_urls.add(canonical_link)
            new_links += 1

        if new_links > 0:
            logger.info(f"  Enqueued {new_links} new pagination links")

    def _process_list_page(self, url: str) -> bool:
        """
        Process a single list page.

        Args:
            url: List page URL

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Processing list page: {url}")

        # Check if already seen (unless force flag)
        if not self.force and self.state.has_seen_list_page(url):
            logger.info(f"  Skipping (already seen)")
            self.stats['list_pages_skipped'] += 1
            return True

        # Fetch page
        html = self._fetch_page(url)
        if not html:
            logger.error(f"  Failed to fetch page")
            self.state.append_list_page_log(url, 'error', 0, 0)
            return False

        # Verbose selector logging
        if self.verbose_selectors:
            scope_count = get_selector_match_count(html, self.recipe.list_scope_css)
            logger.info(f"  Selector '{self.recipe.list_scope_css}' matched {scope_count} elements")

        # Extract item links
        item_links = extract_item_links(
            html,
            url,
            self.recipe.list_scope_css,
            self.recipe.item_link_css
        )

        logger.info(f"  Found {len(item_links)} item links")

        # Add items to state (with deduplication)
        new_items = 0
        for item in item_links:
            canonical_url = canonicalize(item['url'])

            if not self.state.has_seen_item(canonical_url):
                if not self.dry_run:
                    self.state.add_item(canonical_url, item['text'], url)
                new_items += 1
                self.stats['items_discovered'] += 1

            if self.dry_run:
                print(f"    Item: {canonical_url} ({item['text']})")

        logger.info(f"  Added {new_items} new items")

        # Extract pagination links
        pagination_links = []
        if self.recipe.pagination:
            pagination_links = extract_pagination_links(
                html,
                url,
                self.recipe.pagination.to_dict()
            )

            logger.info(f"  Found {len(pagination_links)} pagination links")
            self.stats['pagination_links_found'] += len(pagination_links)

            if self.dry_run and pagination_links:
                print(f"    Pagination links:")
                for plink in pagination_links:
                    print(f"      {plink}")

            # Enqueue pagination links
            if not self.dry_run:
                self._enqueue_pagination_links(pagination_links, url)

        # Mark as seen
        if not self.dry_run:
            self.state.mark_list_page_seen(url)
            self.state.append_list_page_log(url, 'success', len(item_links), len(pagination_links))

        self.stats['list_pages_visited'] += 1

        # Check limits
        if self._should_stop():
            return False

        return True

    def _should_stop(self) -> bool:
        """
        Check if we should stop crawling based on limits.

        Returns:
            True if we should stop, False otherwise
        """
        # Check max_list_pages
        if self.recipe.limits.max_list_pages:
            if self.stats['list_pages_visited'] >= self.recipe.limits.max_list_pages:
                logger.info(f"Reached max_list_pages limit: {self.recipe.limits.max_list_pages}")
                return True

        # Check max_items
        if self.recipe.limits.max_items:
            if self.stats['items_discovered'] >= self.recipe.limits.max_items:
                logger.info(f"Reached max_items limit: {self.recipe.limits.max_items}")
                return True

        return False

    def crawl(self) -> None:
        """Main crawling loop."""
        logger.info("Starting list crawl")
        logger.info(f"Recipe: {len(self.recipe.start_urls)} start URLs")
        logger.info(f"List scope: {self.recipe.list_scope_css}")
        logger.info(f"Item link selector: {self.recipe.item_link_css}")

        if self.recipe.pagination:
            logger.info(f"Pagination type: {self.recipe.pagination.type}")

        if self.recipe.limits.max_list_pages:
            logger.info(f"Max list pages: {self.recipe.limits.max_list_pages}")
        if self.recipe.limits.max_items:
            logger.info(f"Max items: {self.recipe.limits.max_items}")

        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be saved")

        # Main loop
        while self.queue:
            url = self.queue.popleft()

            success = self._process_list_page(url)

            if not success and not self.dry_run:
                # Save state on error
                self.state.save()

            # Check if we should stop
            if self._should_stop():
                break

            # Periodic state save
            if not self.dry_run and self.stats['list_pages_visited'] % 5 == 0:
                self.state.save()

        # Final state save
        if not self.dry_run:
            self.state.save()

        # Print summary
        logger.info("=" * 60)
        logger.info("List crawl complete!")
        logger.info(f"List pages visited: {self.stats['list_pages_visited']}")
        logger.info(f"List pages skipped: {self.stats['list_pages_skipped']}")
        logger.info(f"Items discovered: {self.stats['items_discovered']}")
        logger.info(f"Pagination links found: {self.stats['pagination_links_found']}")

        if not self.dry_run:
            logger.info(f"Output files:")
            logger.info(f"  Items: {self.recipe.output.items_jsonl}")
            logger.info(f"  Pages: {self.recipe.output.pages_jsonl}")

        logger.info("=" * 60)

    def cleanup(self) -> None:
        """Clean up resources."""
        self.web_crawler._cleanup_browser()


def run_list_crawl(recipe_path: str, headless: Optional[bool] = None,
                   dry_run: bool = False, verbose_selectors: bool = False,
                   force: bool = False) -> None:
    """
    Run a list crawl from a recipe file.

    Args:
        recipe_path: Path to recipe YAML file
        headless: Run browser in headless mode
        dry_run: Print discovered links without saving
        verbose_selectors: Log match counts for CSS selectors
        force: Ignore seen_list_pages and reprocess
    """
    # Load recipe
    logger.info(f"Loading recipe: {recipe_path}")
    recipe = load_recipe(recipe_path)

    # Validate recipe
    warnings = validate_recipe(recipe)
    if warnings:
        logger.warning("Recipe validation warnings:")
        for warning in warnings:
            logger.warning(f"  - {warning}")

    # Create crawler
    crawler = ListCrawler(
        recipe=recipe,
        headless=headless,
        dry_run=dry_run,
        verbose_selectors=verbose_selectors,
        force=force
    )

    try:
        crawler.crawl()
    finally:
        crawler.cleanup()

