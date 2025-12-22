# Web Crawler

A flexible web crawler with CloudFlare bypass capabilities

## Installation

```bash
pip install -r requirements.txt
playwright install
```

## Quick Start

```bash
# Crawl a single URL
python crawler.py --url https://example.com

# Crawl multiple URLs
python crawler.py --urls https://example.com https://example.org

# Crawl from a file
python crawler.py --file urls.txt

# Control depth
python crawler.py --url https://example.com --max-depth 2

# Restrict to specific domains
python crawler.py --url https://example.com --domains example.com

# Run in headless mode
python crawler.py --url https://example.com --headless
```

## Configuration

Edit `crawler_config.py`:

```python
START_URLS = ["https://example.com"]
MAX_DEPTH = 2
ALLOWED_DOMAINS = ["example.com"]
HEADLESS = False  # False = visible browser, True = background
RATE_LIMIT_DELAY = 2.5
```

Then run: `python crawler.py`

## Output

- **crawled_pages/** - Downloaded HTML pages organized by domain
- **discovered_links.json** - All discovered links with their source pages

## Resume Crawling

```bash
# Resume from previous crawl
python crawler.py --file discovered_links.json
```

## Features

- Multiple input methods (CLI, file, config)
- Link discovery and tracking
- Depth control (BFS crawling)
- Domain filtering
- CloudFlare bypass (curl_cffi + Playwright)
- Session persistence
- Resume capability

## Command Line Options

```
--url URL                Single URL to crawl
--urls URL [URL ...]     Multiple URLs to crawl
--file FILE              File containing URLs (or discovered_links.json)
--max-depth N            Maximum crawl depth
--domains DOMAIN [...]   Allowed domains to crawl
--output DIR             Output directory (default: crawled_pages)
--links-file FILE        Links file (default: discovered_links.json)
--headless               Run browser in headless mode
--visible                Run browser in visible mode
```

## Tips

- Start with `--max-depth 1` to see how many links exist
- Use `--domains` to avoid crawling the entire internet
- Set `HEADLESS = False` in config to watch CloudFlare challenges being solved
- The `discovered_links.json` file can be used to resume or extend crawls
