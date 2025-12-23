"""
Pure extraction functions for list crawl mode.

These functions are unit-testable and don't perform I/O.
They extract item links and pagination links from HTML content.
"""

from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from bs4 import BeautifulSoup
import re


def normalize_url(base_url: str, href: str) -> str:
    """
    Convert a relative URL to an absolute URL.

    Args:
        base_url: The base URL to resolve against
        href: The href attribute (may be relative or absolute)

    Returns:
        Absolute URL string
    """
    return urljoin(base_url, href)


def canonicalize(url: str, strip_tracking_params: bool = True) -> str:
    """
    Canonicalize a URL by:
    - Removing fragments
    - Optionally removing common tracking parameters
    - Removing trailing slashes (except for root path)

    Args:
        url: URL to canonicalize
        strip_tracking_params: Whether to remove tracking parameters

    Returns:
        Canonicalized URL string
    """
    parsed = urlparse(url)

    # Remove fragment
    path = parsed.path.rstrip('/') if parsed.path != '/' else parsed.path

    # Optionally strip tracking parameters
    query = parsed.query
    if strip_tracking_params and query:
        # Common tracking parameters to remove
        tracking_params = {
            'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
            'fbclid', 'gclid', 'msclkid', 'mc_cid', 'mc_eid',
            '_ga', '_gl', 'ref', 'source'
        }

        params = parse_qs(query, keep_blank_values=True)
        filtered_params = {k: v for k, v in params.items() if k not in tracking_params}

        # Rebuild query string
        if filtered_params:
            query = urlencode(filtered_params, doseq=True)
        else:
            query = ''

    # Reconstruct URL
    canonical = urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        query,
        ''  # No fragment
    ))

    return canonical


def extract_item_links(html: str, base_url: str, scope_css: str,
                      item_link_css: str = "a[href]") -> List[Dict[str, str]]:
    """
    Extract item links from HTML content.

    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative links
        scope_css: CSS selector to scope the search (e.g., "div.quote")
        item_link_css: CSS selector for links within each scope (default: "a[href]")

    Returns:
        List of dicts with keys: url, text, selector_path
    """
    soup = BeautifulSoup(html, 'lxml')
    items = []

    # Find all scope containers
    scopes = soup.select(scope_css)

    for scope_idx, scope in enumerate(scopes):
        # Find links within this scope
        links = scope.select(item_link_css)

        for link_idx, link in enumerate(links):
            href = link.get('href', '').strip()

            # Skip invalid hrefs
            if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:'):
                continue

            # Get link text
            text = link.get_text(strip=True)

            # Normalize to absolute URL
            absolute_url = normalize_url(base_url, href)

            # Build selector path for debugging
            selector_path = f"{scope_css}[{scope_idx}] {item_link_css}[{link_idx}]"

            items.append({
                'url': absolute_url,
                'text': text,
                'selector_path': selector_path
            })

    return items


def extract_pagination_links(html: str, base_url: str,
                            pagination_config: Dict[str, Any]) -> List[str]:
    """
    Extract pagination links based on the pagination strategy.

    Args:
        html: HTML content to parse
        base_url: Base URL for resolving relative links
        pagination_config: Pagination configuration dict with keys:
            - type: 'next' | 'all_links' | 'url_template'
            - next_css: CSS selector for next button (type=next)
            - pagination_scope_css: CSS selector for pagination container (type=all_links)
            - page_param: Query parameter name (type=url_template)
            - page_start: Starting page number (type=url_template)
            - page_end: Ending page number (type=url_template)

    Returns:
        List of absolute URLs
    """
    pagination_type = pagination_config.get('type', 'next')

    if pagination_type == 'next':
        return _extract_next_pagination(html, base_url, pagination_config)
    elif pagination_type == 'all_links':
        return _extract_all_links_pagination(html, base_url, pagination_config)
    elif pagination_type == 'url_template':
        return _extract_url_template_pagination(base_url, pagination_config)
    else:
        raise ValueError(f"Unknown pagination type: {pagination_type}")


def _extract_next_pagination(html: str, base_url: str,
                            config: Dict[str, Any]) -> List[str]:
    """
    Extract next page link using next button CSS selector.

    Args:
        html: HTML content
        base_url: Base URL
        config: Config with 'next_css' key

    Returns:
        List with single URL or empty list
    """
    next_css = config.get('next_css')
    if not next_css:
        return []

    soup = BeautifulSoup(html, 'lxml')
    next_link = soup.select_one(next_css)

    if not next_link:
        return []

    href = next_link.get('href', '').strip()
    if not href or href.startswith('#') or href.startswith('javascript:'):
        return []

    absolute_url = normalize_url(base_url, href)
    return [absolute_url]


def _extract_all_links_pagination(html: str, base_url: str,
                                 config: Dict[str, Any]) -> List[str]:
    """
    Extract all pagination links from a pagination container.

    Args:
        html: HTML content
        base_url: Base URL
        config: Config with 'pagination_scope_css' key

    Returns:
        List of URLs
    """
    pagination_scope_css = config.get('pagination_scope_css')
    if not pagination_scope_css:
        return []

    soup = BeautifulSoup(html, 'lxml')
    pagination_container = soup.select_one(pagination_scope_css)

    if not pagination_container:
        return []

    # Find all links in pagination container
    links = pagination_container.select('a[href]')
    urls = []

    base_parsed = urlparse(base_url)

    for link in links:
        href = link.get('href', '').strip()

        if not href or href.startswith('#') or href.startswith('javascript:'):
            continue

        absolute_url = normalize_url(base_url, href)

        # Filter to same host and similar path pattern
        link_parsed = urlparse(absolute_url)
        if link_parsed.netloc == base_parsed.netloc:
            # Check if path is similar (same base path)
            base_path_parts = base_parsed.path.rstrip('/').split('/')
            link_path_parts = link_parsed.path.rstrip('/').split('/')

            # Allow if paths match or link is slightly different (pagination variant)
            if len(link_path_parts) >= len(base_path_parts) - 1:
                urls.append(absolute_url)

    return urls


def _extract_url_template_pagination(base_url: str,
                                    config: Dict[str, Any]) -> List[str]:
    """
    Generate pagination URLs from a template.

    Args:
        base_url: Base URL
        config: Config with 'page_param', 'page_start', 'page_end' keys

    Returns:
        List of generated URLs
    """
    page_param = config.get('page_param', 'page')
    page_start = config.get('page_start', 1)
    page_end = config.get('page_end', 10)

    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    urls = []
    for page_num in range(page_start, page_end + 1):
        # Update page parameter
        params[page_param] = [str(page_num)]

        # Rebuild query string
        query = urlencode(params, doseq=True)

        # Reconstruct URL
        url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query,
            ''
        ))

        urls.append(url)

    return urls


def get_selector_match_count(html: str, css_selector: str) -> int:
    """
    Count how many elements match a CSS selector.
    Useful for debugging and verbose mode.

    Args:
        html: HTML content
        css_selector: CSS selector to test

    Returns:
        Number of matching elements
    """
    soup = BeautifulSoup(html, 'lxml')
    matches = soup.select(css_selector)
    return len(matches)

