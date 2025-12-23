# List Crawl Mode - User Guide

## Overview

List crawl mode is a recipe-driven feature for extracting item links from paginated list pages. It's designed for scenarios where you want to:

1. Crawl through paginated list pages (e.g., product listings, article archives)
2. Extract links to individual items from each list page
3. Handle different pagination strategies (next button, page numbers, URL templates)
4. Maintain state for resume capability
5. Deduplicate discovered items

## Quick Start

### 1. Create a Recipe

Create a YAML file in the `recipes/` directory:

```yaml
start_urls:
  - "http://example.com/products"

list_scope_css: "div.product"
item_link_css: "a.product-link"

pagination:
  type: next
  next_css: "a.next-page"

limits:
  max_list_pages: 100
  max_items: 1000

output:
  items_jsonl: "output/items.jsonl"
  pages_jsonl: "output/pages.jsonl"
```

### 2. Validate Your Recipe

```bash
python validate_recipe.py recipes/your_recipe.yaml
```

### 3. Run the Crawler

```bash
python crawler.py --mode list --recipe recipes/your_recipe.yaml
```

## Recipe Schema

### Required Fields

- **start_urls**: List of URLs to start crawling from
- **list_scope_css**: CSS selector to identify individual items on the list page
- **item_link_css**: CSS selector for links within each item (default: `a[href]`)

### Optional Fields

#### Pagination

Three pagination strategies are supported:

**1. Next Button** (follow a "next page" link):
```yaml
pagination:
  type: next
  next_css: "a.next"
```

**2. All Links** (extract all page links from a container):
```yaml
pagination:
  type: all_links
  pagination_scope_css: "div.pagination"
```

**3. URL Template** (generate page URLs):
```yaml
pagination:
  type: url_template
  page_param: "page"
  page_start: 1
  page_end: 10
```

#### Limits

```yaml
limits:
  max_list_pages: 100  # Stop after visiting this many list pages
  max_items: 1000      # Stop after discovering this many items
```

#### Output

```yaml
output:
  items_jsonl: "output/items.jsonl"    # Where to save discovered items
  pages_jsonl: "output/pages.jsonl"    # Where to log list page visits
```

## CLI Options

### Basic Usage

```bash
# Run with a recipe
python crawler.py --mode list --recipe recipes/example.yaml

# Run in headless mode
python crawler.py --mode list --recipe recipes/example.yaml --headless

# Run with visible browser (useful for debugging)
python crawler.py --mode list --recipe recipes/example.yaml --visible
```

### Debug Options

```bash
# Dry run (don't save anything, just print what would be discovered)
python crawler.py --mode list --recipe recipes/example.yaml --dry-run

# Verbose selector logging (see how many elements each selector matches)
python crawler.py --mode list --recipe recipes/example.yaml --verbose-selectors

# Force reprocess (ignore seen pages)
python crawler.py --mode list --recipe recipes/example.yaml --force
```

### Debug Tools

```bash
# Dump HTML for a URL
python crawler.py --dump-html https://example.com

# Take a screenshot
python crawler.py --screenshot https://example.com
```

## Output Files

### items.jsonl

Each line is a JSON object representing a discovered item:

```json
{
  "url": "https://example.com/item/123",
  "text": "Item Title",
  "source_page": "https://example.com/products?page=1",
  "timestamp": "2025-12-22T10:30:00Z"
}
```

### list_pages.jsonl

Each line logs a visited list page:

```json
{
  "url": "https://example.com/products?page=1",
  "status": "success",
  "items_found": 20,
  "pagination_found": 1,
  "timestamp": "2025-12-22T10:30:00Z"
}
```

### State Files

- **seen_list_pages.json**: Set of visited list page URLs
- **seen_item_links.json**: Set of discovered item URLs

These enable resume capability - if the crawl is interrupted, it will skip already-seen pages on restart.

## Examples

### Example 1: Next Button Pagination

See `recipes/example_quotes.yaml` - crawls quotes.toscrape.com using the "Next" button.

```bash
python crawler.py --mode list --recipe recipes/example_quotes.yaml
```

### Example 2: All Links Pagination

See `recipes/example_all_links.yaml` - extracts all page links from a pagination container.

```bash
python crawler.py --mode list --recipe recipes/example_all_links.yaml
```

### Example 3: URL Template Pagination

See `recipes/example_url_template.yaml` - generates page URLs from a template.

```bash
python crawler.py --mode list --recipe recipes/example_url_template.yaml
```

## Tips and Best Practices

### 1. Start with Dry Run

Always test your recipe with `--dry-run` first:

```bash
python crawler.py --mode list --recipe recipes/new_recipe.yaml --dry-run
```

This shows you what would be discovered without actually saving anything.

### 2. Use Verbose Selectors for Debugging

If your selectors aren't matching correctly, use `--verbose-selectors`:

```bash
python crawler.py --mode list --recipe recipes/new_recipe.yaml --verbose-selectors --dry-run
```

This logs how many elements each CSS selector matches.

### 3. Test with Small Limits

When developing a recipe, use small limits:

```yaml
limits:
  max_list_pages: 2
  max_items: 10
```

### 4. Inspect HTML with Debug Tools

If you're unsure about selectors, dump the HTML:

```bash
python crawler.py --dump-html https://example.com/products
```

Then open `debug_dump.html` in your browser and inspect the structure.

### 5. Resume Capability

The crawler automatically saves state. If interrupted, just run the same command again - it will skip already-seen pages.

To force a fresh crawl, use `--force`:

```bash
python crawler.py --mode list --recipe recipes/example.yaml --force
```

## Common Gotchas

### JavaScript-Rendered Content

The crawler uses Playwright, so it handles JavaScript-rendered content. However, you may need to adjust selectors if content loads dynamically.

### Infinite Scroll

The current implementation doesn't handle infinite scroll. Use the `url_template` pagination strategy if the site has URL-based pagination.

### Login Required

If the site requires login, you may need to manually log in with `--visible` mode. The crawler will save cookies in `output/browser_session/cookies.json` for reuse.

### Rate Limiting

The crawler respects the `RATE_LIMIT_DELAY` setting in `crawler_config.py`. Increase this if you're getting blocked.

## Troubleshooting

### "No elements matched selector"

- Use `--verbose-selectors` to see match counts
- Use `--dump-html` to inspect the page structure
- Try the selector in your browser's DevTools console

### "Pagination not working"

- Check that pagination links are actual `<a>` tags with `href` attributes
- For JavaScript pagination, you may need to use `url_template` instead
- Use `--dry-run` to see what pagination links are discovered

### "Browser not starting"

Make sure Playwright browsers are installed:

```bash
playwright install
```

## Running Unit Tests

```bash
python -m unittest tests.test_extractors -v
```

All extraction functions are unit-tested with HTML fixtures.

