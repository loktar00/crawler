"""
Unit tests for extractor functions.

Tests the pure extraction functions without requiring network access.
"""

import unittest
from pathlib import Path

from extractors.list_page import (
    normalize_url,
    canonicalize,
    extract_item_links,
    extract_pagination_links,
    get_selector_match_count
)


class TestNormalizeUrl(unittest.TestCase):
    """Test URL normalization."""

    def test_absolute_url(self):
        """Absolute URLs should be returned as-is."""
        result = normalize_url("https://example.com/", "https://other.com/page")
        self.assertEqual(result, "https://other.com/page")

    def test_relative_url(self):
        """Relative URLs should be converted to absolute."""
        result = normalize_url("https://example.com/base/", "page.html")
        self.assertEqual(result, "https://example.com/base/page.html")

    def test_root_relative_url(self):
        """Root-relative URLs should work correctly."""
        result = normalize_url("https://example.com/base/", "/page.html")
        self.assertEqual(result, "https://example.com/page.html")

    def test_protocol_relative_url(self):
        """Protocol-relative URLs should inherit protocol."""
        result = normalize_url("https://example.com/", "//other.com/page")
        self.assertEqual(result, "https://other.com/page")


class TestCanonicalize(unittest.TestCase):
    """Test URL canonicalization."""

    def test_remove_fragment(self):
        """Fragments should be removed."""
        result = canonicalize("https://example.com/page#section")
        self.assertEqual(result, "https://example.com/page")

    def test_remove_trailing_slash(self):
        """Trailing slashes should be removed (except root)."""
        result = canonicalize("https://example.com/page/")
        self.assertEqual(result, "https://example.com/page")

        # Root should keep slash
        result = canonicalize("https://example.com/")
        self.assertEqual(result, "https://example.com/")

    def test_remove_tracking_params(self):
        """Tracking parameters should be removed."""
        result = canonicalize("https://example.com/page?utm_source=test&id=123")
        # Should keep id but remove utm_source
        self.assertIn("id=123", result)
        self.assertNotIn("utm_source", result)

    def test_keep_tracking_params(self):
        """Can optionally keep tracking parameters."""
        result = canonicalize("https://example.com/page?utm_source=test",
                            strip_tracking_params=False)
        self.assertIn("utm_source=test", result)


class TestExtractItemLinks(unittest.TestCase):
    """Test item link extraction."""

    def setUp(self):
        """Load sample HTML fixture."""
        fixture_path = Path(__file__).parent / "fixtures" / "sample_list_page.html"
        with open(fixture_path, 'r', encoding='utf-8') as f:
            self.html = f.read()

    def test_extract_from_scope(self):
        """Should extract links from within scope."""
        items = extract_item_links(
            self.html,
            "https://example.com/products",
            "div.product",
            "a.details-link"
        )

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]['url'], "https://example.com/products/widget-1")
        self.assertEqual(items[0]['text'], "View Details")

    def test_extract_all_links_in_scope(self):
        """Should extract all matching links in each scope."""
        items = extract_item_links(
            self.html,
            "https://example.com/products",
            "div.product",
            "a[href]"  # All links
        )

        # Each product has 2 links (h2 link + details link)
        self.assertEqual(len(items), 6)

    def test_skip_invalid_hrefs(self):
        """Should skip javascript:, mailto:, and # links."""
        html = """
        <div class="item">
            <a href="javascript:void(0)">JS Link</a>
            <a href="mailto:test@example.com">Email</a>
            <a href="#section">Anchor</a>
            <a href="/valid">Valid</a>
        </div>
        """

        items = extract_item_links(html, "https://example.com/", "div.item", "a[href]")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['url'], "https://example.com/valid")

    def test_relative_url_resolution(self):
        """Should resolve relative URLs correctly."""
        html = """
        <div class="item">
            <a href="page.html">Relative</a>
            <a href="/absolute">Root Relative</a>
        </div>
        """

        items = extract_item_links(html, "https://example.com/base/", "div.item", "a[href]")

        self.assertEqual(items[0]['url'], "https://example.com/base/page.html")
        self.assertEqual(items[1]['url'], "https://example.com/absolute")


class TestExtractPaginationLinks(unittest.TestCase):
    """Test pagination link extraction."""

    def setUp(self):
        """Load sample HTML fixture."""
        fixture_path = Path(__file__).parent / "fixtures" / "sample_list_page.html"
        with open(fixture_path, 'r', encoding='utf-8') as f:
            self.html = f.read()

    def test_next_pagination(self):
        """Should extract next button link."""
        config = {
            'type': 'next',
            'next_css': 'a.next-link'
        }

        links = extract_pagination_links(self.html, "https://example.com/products", config)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0], "https://example.com/products?page=3")

    def test_all_links_pagination(self):
        """Should extract all pagination links."""
        config = {
            'type': 'all_links',
            'pagination_scope_css': 'div.pagination'
        }

        links = extract_pagination_links(self.html, "https://example.com/products", config)

        # Should find page links (may include duplicates in fixture)
        self.assertGreater(len(links), 0)
        self.assertTrue(any('page=1' in link for link in links))

    def test_url_template_pagination(self):
        """Should generate URLs from template."""
        config = {
            'type': 'url_template',
            'page_param': 'page',
            'page_start': 1,
            'page_end': 3
        }

        links = extract_pagination_links(self.html, "https://example.com/products", config)

        self.assertEqual(len(links), 3)
        self.assertIn("page=1", links[0])
        self.assertIn("page=2", links[1])
        self.assertIn("page=3", links[2])

    def test_next_pagination_not_found(self):
        """Should return empty list if next link not found."""
        config = {
            'type': 'next',
            'next_css': 'a.nonexistent'
        }

        links = extract_pagination_links(self.html, "https://example.com/products", config)

        self.assertEqual(len(links), 0)


class TestGetSelectorMatchCount(unittest.TestCase):
    """Test selector match counting."""

    def test_count_matches(self):
        """Should count matching elements."""
        html = """
        <div class="item">Item 1</div>
        <div class="item">Item 2</div>
        <div class="other">Other</div>
        """

        count = get_selector_match_count(html, "div.item")
        self.assertEqual(count, 2)

    def test_no_matches(self):
        """Should return 0 for no matches."""
        html = "<div>Content</div>"

        count = get_selector_match_count(html, "span.nonexistent")
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()

