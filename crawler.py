"""
Generic Web Crawler

A flexible web crawler that can:
- Start from a single URL or multiple URLs
- Follow links discovered on pages
- Track link discovery hierarchy
- Save pages and discovered links
- Bypass CloudFlare protection using curl_cffi and Playwright
"""

import os
import sys
import time
import logging
import hashlib
import json
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from collections import defaultdict, deque
from curl_cffi import requests
from curl_cffi.requests import exceptions as requests_exceptions
from bs4 import BeautifulSoup
import crawler_config

# Try to import Playwright for browser-based fallback
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WebCrawler:
    """Generic web crawler with CloudFlare bypass capabilities."""

    def __init__(self, start_urls=None, max_depth=None, allowed_domains=None,
                 output_dir="crawled_pages", links_file="discovered_links.json", headless=None):
        """
        Initialize the web crawler.

        Args:
            start_urls: List of URLs to start crawling from
            max_depth: Maximum depth to crawl (None = unlimited)
            allowed_domains: List of domains to restrict crawling to (None = no restriction)
            output_dir: Directory to save crawled pages
            links_file: File to save discovered links
            headless: Run browser in headless mode (None = use config default)
        """
        self.start_urls = start_urls or []
        self.max_depth = max_depth if max_depth is not None else crawler_config.MAX_DEPTH
        self.allowed_domains = allowed_domains or crawler_config.ALLOWED_DOMAINS
        self.headless = headless if headless is not None else crawler_config.HEADLESS
        self.rate_limit_delay = crawler_config.RATE_LIMIT_DELAY
        self.max_retries = crawler_config.MAX_RETRIES
        self.retry_delay = crawler_config.RETRY_DELAY

        # Use curl_cffi with Chrome impersonation to bypass bot detection
        self.session = requests.Session()
        self.impersonate = "chrome120"

        # Set up output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Links file path
        self.links_file = Path(links_file)

        # Crawl queue: (url, depth, parent_url)
        self.queue = deque()

        # Track visited URLs to avoid duplicates
        self.visited = set()

        # Track discovered links: {url: {'found_on': [parent_urls], 'depth': int}}
        self.discovered_links = defaultdict(lambda: {'found_on': [], 'depth': None})

        # Initialize Playwright browser (lazy initialization)
        self._playwright = None
        self._browser = None
        self._context = None

        # Session persistence for Cloudflare bypass
        self.session_dir = self.output_dir / 'browser_session'
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = self.session_dir / 'cookies.json'

    def _init_browser(self):
        """Initialize Playwright browser if available."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.debug("Playwright not available")
            return False

        # Check if browser is already initialized and still valid
        if self._browser is not None:
            try:
                _ = self._browser.version
                return True
            except Exception:
                logger.warning("Browser is no longer valid, reinitializing")
                self._browser = None
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except Exception:
                        pass
                    self._playwright = None

        # Initialize browser
        if self._playwright is None:
            try:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--start-maximized'
                    ]
                )
                mode = "headless" if self.headless else "visible"
                logger.info(f"Playwright browser initialized ({mode} mode)")
                return True
            except Exception as e:
                error_msg = str(e)
                if "playwright install" in error_msg.lower() or "executable doesn't exist" in error_msg.lower():
                    logger.error("Playwright browsers not installed!")
                    logger.error("Please run: playwright install")
                else:
                    logger.warning(f"Failed to initialize Playwright browser: {e}")
                self._playwright = None
                self._browser = None
                return False
        return True

    def _fetch_page_with_browser(self, url):
        """
        Fetch a page using Playwright browser automation.

        Args:
            url: URL to fetch

        Returns:
            Mock Response object with .text attribute or None if failed
        """
        time.sleep(self.rate_limit_delay)

        if not self._init_browser():
            logger.error("Failed to initialize browser for fetching")
            return None

        if self._browser is None:
            logger.error("Browser is None after initialization")
            return None

        try:
            # Create or reuse persistent context
            if self._context is None:
                import random
                viewport_width = 1920 + random.randint(-100, 100)
                viewport_height = 1080 + random.randint(-100, 100)

                context_options = {
                    'viewport': {'width': viewport_width, 'height': viewport_height},
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'locale': 'en-US',
                    'timezone_id': 'America/New_York',
                }

                self._context = self._browser.new_context(**context_options)

                # Load saved cookies if they exist
                if self.cookies_file.exists():
                    try:
                        with open(self.cookies_file, 'r') as f:
                            cookies = json.load(f)
                            self._context.add_cookies(cookies)
                        logger.info("Loaded saved session cookies")
                    except Exception as e:
                        logger.warning(f"Could not load cookies: {e}")

            page = self._context.new_page()

            # Override navigator.webdriver to hide automation
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page.goto(url, wait_until='domcontentloaded', timeout=60000)

            # Human-like behavior: random delay
            import random
            time.sleep(random.uniform(1.5, 3.5))

            html_content = page.content()

            # Check for Cloudflare challenge
            has_challenge_text = 'Just a moment' in html_content and 'challenge-platform' in html_content
            has_cf_verification = 'cf-browser-verification' in html_content
            has_checking_browser = 'Checking your browser' in html_content or 'Checking if the site connection is secure' in html_content

            is_cloudflare_challenge = (has_challenge_text or has_cf_verification) and has_checking_browser

            if is_cloudflare_challenge:
                logger.warning("Cloudflare challenge detected, waiting...")
                wait_time = 300  # 5 minutes
                time.sleep(wait_time)
                html_content = page.content()

            # Save cookies after successful fetch
            try:
                cookies = self._context.cookies()
                with open(self.cookies_file, 'w') as f:
                    json.dump(cookies, f)
            except Exception as e:
                logger.debug(f"Could not save cookies: {e}")

            # Close page but keep context alive
            try:
                page.close()
            except Exception as e:
                logger.debug(f"Could not close page: {e}")

            # Create a mock response object
            class MockResponse:
                def __init__(self, text, url):
                    self.text = text
                    self.status_code = 200
                    self.url = url

            return MockResponse(html_content, url)

        except Exception as e:
            logger.error(f"Browser fetch failed for {url}: {e}")
            return None

    def fetch_page(self, url):
        """
        Fetch a page with retry logic and rate limiting.
        Uses browser automation for maximum reliability.

        Args:
            url: URL to fetch

        Returns:
            Response object or None if failed
        """
        return self._fetch_page_with_browser(url)

    def normalize_url(self, url):
        """
        Normalize URL by removing fragments and trailing slashes.

        Args:
            url: URL to normalize

        Returns:
            Normalized URL string
        """
        parsed = urlparse(url)
        # Remove fragment
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/') if parsed.path != '/' else parsed.path,
            parsed.params,
            parsed.query,
            ''  # Remove fragment
        ))
        return normalized

    def is_allowed_domain(self, url):
        """
        Check if URL is within allowed domains.

        Args:
            url: URL to check

        Returns:
            True if allowed, False otherwise
        """
        if not self.allowed_domains:
            return True

        parsed = urlparse(url)
        domain = parsed.netloc

        for allowed in self.allowed_domains:
            if domain == allowed or domain.endswith('.' + allowed):
                return True

        return False

    def extract_links(self, html_content, base_url):
        """
        Extract all links from HTML content.

        Args:
            html_content: HTML string
            base_url: Base URL for resolving relative links

        Returns:
            Set of absolute URLs
        """
        soup = BeautifulSoup(html_content, 'lxml')
        links = set()

        for tag in soup.find_all('a', href=True):
            href = tag.get('href', '')
            if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:'):
                continue

            # Convert to absolute URL
            absolute_url = urljoin(base_url, href)

            # Normalize URL
            normalized_url = self.normalize_url(absolute_url)

            # Check if allowed domain
            if self.is_allowed_domain(normalized_url):
                links.add(normalized_url)

        return links

    def get_url_hash(self, url):
        """Generate a hash for the URL to use as filename."""
        return hashlib.md5(url.encode()).hexdigest()

    def save_page(self, url, html_content):
        """
        Save HTML content to file.

        Args:
            url: URL of the page
            html_content: HTML content to save

        Returns:
            Path to saved file
        """
        url_hash = self.get_url_hash(url)
        parsed = urlparse(url)

        # Create subdirectory based on domain
        domain_dir = self.output_dir / parsed.netloc
        domain_dir.mkdir(exist_ok=True)

        # Save with hash as filename
        file_path = domain_dir / f"{url_hash}.html"

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Saved: {url} -> {file_path.name}")
        return file_path

    def save_discovered_links(self):
        """Save discovered links to JSON file."""
        # Convert defaultdict to regular dict for JSON serialization
        links_data = {
            url: {
                'found_on': data['found_on'],
                'depth': data['depth']
            }
            for url, data in self.discovered_links.items()
        }

        with open(self.links_file, 'w', encoding='utf-8') as f:
            json.dump(links_data, f, indent=2)

        logger.info(f"Saved discovered links to {self.links_file}")

    def load_discovered_links(self):
        """Load previously discovered links from JSON file."""
        if not self.links_file.exists():
            return

        try:
            with open(self.links_file, 'r', encoding='utf-8') as f:
                links_data = json.load(f)

            for url, data in links_data.items():
                self.discovered_links[url] = data

            logger.info(f"Loaded {len(links_data)} discovered links from {self.links_file}")
        except Exception as e:
            logger.warning(f"Could not load discovered links: {e}")

    def add_to_queue(self, url, depth, parent_url=None):
        """
        Add URL to crawl queue.

        Args:
            url: URL to add
            depth: Current depth
            parent_url: URL of the parent page
        """
        normalized_url = self.normalize_url(url)

        # Skip if already visited
        if normalized_url in self.visited:
            return

        # Skip if max depth exceeded
        if self.max_depth is not None and depth > self.max_depth:
            return

        # Track discovered link
        if parent_url:
            if parent_url not in self.discovered_links[normalized_url]['found_on']:
                self.discovered_links[normalized_url]['found_on'].append(parent_url)

        if self.discovered_links[normalized_url]['depth'] is None:
            self.discovered_links[normalized_url]['depth'] = depth

        # Add to queue
        self.queue.append((normalized_url, depth, parent_url))

    def crawl(self):
        """Main crawling loop."""
        # Load previously discovered links if resuming
        self.load_discovered_links()

        # Add start URLs to queue
        for url in self.start_urls:
            self.add_to_queue(url, 0)

        logger.info(f"Starting crawl with {len(self.queue)} URLs")
        if self.max_depth is not None:
            logger.info(f"Max depth: {self.max_depth}")
        if self.allowed_domains:
            logger.info(f"Allowed domains: {', '.join(self.allowed_domains)}")

        while self.queue:
            url, depth, parent_url = self.queue.popleft()

            # Skip if already visited
            if url in self.visited:
                continue

            logger.info(f"[Depth {depth}] Crawling: {url}")
            if parent_url:
                logger.info(f"  Found on: {parent_url}")

            # Fetch page
            response = self.fetch_page(url)
            if not response:
                logger.error(f"Failed to fetch {url}")
                self.visited.add(url)
                continue

            # Mark as visited
            self.visited.add(url)

            # Save page
            self.save_page(url, response.text)

            # Extract links if we haven't reached max depth
            if self.max_depth is None or depth < self.max_depth:
                links = self.extract_links(response.text, url)
                logger.info(f"  Found {len(links)} links")

                # Add links to queue
                for link in links:
                    self.add_to_queue(link, depth + 1, url)

            # Save discovered links periodically
            if len(self.visited) % 10 == 0:
                self.save_discovered_links()

        # Final save of discovered links
        self.save_discovered_links()

        logger.info(f"Crawl complete! Visited {len(self.visited)} pages")
        logger.info(f"Discovered {len(self.discovered_links)} unique links")

    def _cleanup_browser(self):
        """Clean up Playwright browser resources."""
        if self._context:
            try:
                self._context.close()
                logger.info("Browser context closed")
            except Exception as e:
                logger.warning(f"Error closing context: {e}")
            self._context = None

        if self._browser:
            try:
                self._browser.close()
                logger.info("Browser closed")
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
        if self._playwright:
            try:
                self._playwright.stop()
                logger.info("Playwright stopped")
            except Exception as e:
                logger.warning(f"Error stopping Playwright: {e}")


def load_urls_from_file(file_path):
    """
    Load URLs from a file or JSON links file.

    Args:
        file_path: Path to file containing URLs

    Returns:
        List of URLs
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return []

    # Check if it's a JSONL file (JSON Lines format from list crawl)
    if file_path.suffix == '.jsonl':
        urls = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            # Extract URL from the JSON object
                            if isinstance(data, dict) and 'url' in data:
                                urls.append(data['url'])
                            else:
                                logger.warning(f"Line missing 'url' field: {line[:50]}...")
                        except json.JSONDecodeError:
                            logger.warning(f"Could not parse JSON line: {line[:50]}...")
            logger.info(f"Loaded {len(urls)} URLs from JSONL file")
            return urls
        except Exception as e:
            logger.error(f"Error reading JSONL file: {e}")
            return []

    # Check if it's a JSON file (discovered_links.json format)
    if file_path.suffix == '.json':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # If it's our discovered_links format
            if isinstance(data, dict) and all(isinstance(v, dict) for v in data.values()):
                urls = list(data.keys())
                logger.info(f"Loaded {len(urls)} URLs from JSON file")
                return urls
        except Exception as e:
            logger.warning(f"Could not parse as JSON: {e}")

    # Otherwise, treat as text file with one URL per line
    urls = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)

    logger.info(f"Loaded {len(urls)} URLs from file")
    return urls


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Generic web crawler with CloudFlare bypass',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Standard crawl mode
  python crawler.py --url https://example.com
  python crawler.py --file urls.txt

  # List crawl mode (recipe-driven)
  python crawler.py --mode list --recipe recipes/example_quotes.yaml
  python crawler.py --mode list --recipe recipes/example_quotes.yaml --dry-run
  python crawler.py --mode list --recipe recipes/example_quotes.yaml --force

  # Debug tools
  python crawler.py --mode list --recipe recipes/example.yaml --verbose-selectors
  python crawler.py --dump-html https://example.com
  python crawler.py --screenshot https://example.com
        """
    )

    # Mode selection
    parser.add_argument('--mode', choices=['crawl', 'list'], default='crawl',
                       help='Crawl mode: "crawl" (default) or "list" (recipe-driven)')

    # Recipe for list mode
    parser.add_argument('--recipe', help='Recipe YAML file for list mode')

    # Standard crawl mode arguments
    parser.add_argument('--url', help='Single URL to crawl')
    parser.add_argument('--urls', nargs='+', help='Multiple URLs to crawl')
    parser.add_argument('--file', help='File containing URLs (one per line, or JSON)')
    parser.add_argument('--max-depth', type=int, help='Maximum crawl depth')
    parser.add_argument('--domains', nargs='+', help='Allowed domains to crawl')
    parser.add_argument('--output', default='crawled_pages', help='Output directory')
    parser.add_argument('--links-file', default='discovered_links.json', help='File to save discovered links')

    # Browser options
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode')
    parser.add_argument('--visible', action='store_true', help='Run browser in visible mode')

    # Debug options
    parser.add_argument('--dry-run', action='store_true',
                       help='Print discovered links without saving (list mode)')
    parser.add_argument('--verbose-selectors', action='store_true',
                       help='Log match counts for CSS selectors (list mode)')
    parser.add_argument('--force', action='store_true',
                       help='Ignore seen pages and reprocess (list mode)')
    parser.add_argument('--dump-html', metavar='URL',
                       help='Dump HTML content for a URL and exit')
    parser.add_argument('--screenshot', metavar='URL',
                       help='Take screenshot of a URL and exit')

    args = parser.parse_args()

    # Determine headless mode
    headless = None
    if args.headless:
        headless = True
    elif args.visible:
        headless = False

    # Handle debug tools
    if args.dump_html:
        _dump_html(args.dump_html, headless)
        return

    if args.screenshot:
        _take_screenshot(args.screenshot, headless)
        return

    # Route to appropriate mode
    if args.mode == 'list':
        _run_list_mode(args, headless)
    else:
        _run_crawl_mode(args, headless)


def _run_crawl_mode(args, headless):
    """Run standard crawl mode."""
    # Collect start URLs from various sources
    start_urls = []

    if args.url:
        start_urls.append(args.url)

    if args.urls:
        start_urls.extend(args.urls)

    if args.file:
        start_urls.extend(load_urls_from_file(args.file))

    # If no URLs provided, use config
    if not start_urls:
        start_urls = crawler_config.START_URLS
        if not start_urls:
            logger.error("No URLs provided! Use --url, --urls, --file, or set START_URLS in crawler_config.py")
            sys.exit(1)

    # Create crawler
    crawler = WebCrawler(
        start_urls=start_urls,
        max_depth=args.max_depth,
        allowed_domains=args.domains,
        output_dir=args.output,
        links_file=args.links_file,
        headless=headless
    )

    try:
        crawler.crawl()
    finally:
        crawler._cleanup_browser()


def _run_list_mode(args, headless):
    """Run list crawl mode."""
    if not args.recipe:
        logger.error("List mode requires --recipe argument")
        sys.exit(1)

    # Import list crawler
    try:
        from list_crawler import run_list_crawl
    except ImportError as e:
        logger.error(f"Failed to import list_crawler: {e}")
        sys.exit(1)

    # Run list crawl
    run_list_crawl(
        recipe_path=args.recipe,
        headless=headless,
        dry_run=args.dry_run,
        verbose_selectors=args.verbose_selectors,
        force=args.force
    )


def _dump_html(url, headless):
    """Dump HTML content for a URL."""
    logger.info(f"Dumping HTML for: {url}")

    crawler = WebCrawler(start_urls=[], max_depth=0, headless=headless)
    try:
        response = crawler.fetch_page(url)
        if response:
            output_file = Path("debug_dump.html")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(response.text)
            logger.info(f"HTML saved to: {output_file}")
        else:
            logger.error("Failed to fetch page")
    finally:
        crawler._cleanup_browser()


def _take_screenshot(url, headless):
    """Take a screenshot of a URL."""
    logger.info(f"Taking screenshot of: {url}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not available for screenshots")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless if headless is not None else True)
        page = browser.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=60000)

        output_file = Path("debug_screenshot.png")
        page.screenshot(path=str(output_file), full_page=True)

        browser.close()
        logger.info(f"Screenshot saved to: {output_file}")


if __name__ == "__main__":
    main()
