# List Crawl Mode - Quick Start

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install
```

## 3-Step Workflow

### Step 1: Create a Recipe

Create `recipes/my_site.yaml`:

```yaml
start_urls:
  - "https://example.com/items"

list_scope_css: "div.item"
item_link_css: "a.item-link"

pagination:
  type: next
  next_css: "a.next"

limits:
  max_list_pages: 10
  max_items: 100

output:
  items_jsonl: "output/my_items.jsonl"
  pages_jsonl: "output/my_pages.jsonl"
```

### Step 2: Validate

```bash
python validate_recipe.py recipes/my_site.yaml
```

### Step 3: Run

```bash
# Dry run first (preview without saving)
python crawler.py --mode list --recipe recipes/my_site.yaml --dry-run

# Real run
python crawler.py --mode list --recipe recipes/my_site.yaml
```

## Common Commands

```bash
# List mode with visible browser (for debugging)
python crawler.py --mode list --recipe recipes/my_site.yaml --visible

# Debug selectors
python crawler.py --mode list --recipe recipes/my_site.yaml --verbose-selectors --dry-run

# Force reprocess (ignore seen pages)
python crawler.py --mode list --recipe recipes/my_site.yaml --force

# Dump HTML to inspect structure
python crawler.py --dump-html https://example.com/items

# Take screenshot
python crawler.py --screenshot https://example.com/items
```

## Pagination Types

### Next Button
```yaml
pagination:
  type: next
  next_css: "a.next"
```

### All Page Links
```yaml
pagination:
  type: all_links
  pagination_scope_css: "div.pagination"
```

### URL Template
```yaml
pagination:
  type: url_template
  page_param: "page"
  page_start: 1
  page_end: 10
```

## Output Files

- `output/items.jsonl` - Discovered item links (one JSON object per line)
- `output/pages.jsonl` - List page visit log
- `output/seen_list_pages.json` - State for resume
- `output/seen_item_links.json` - State for deduplication

## Examples

Three working examples are provided:

```bash
# Example 1: Next button pagination
python crawler.py --mode list --recipe recipes/example_quotes.yaml

# Example 2: All links pagination
python crawler.py --mode list --recipe recipes/example_all_links.yaml

# Example 3: URL template pagination
python crawler.py --mode list --recipe recipes/example_url_template.yaml
```

## Testing

```bash
# Run unit tests
python -m unittest tests.test_extractors -v

# Validate a recipe
python validate_recipe.py recipes/example_quotes.yaml
```

## Troubleshooting

**Selectors not matching?**
- Use `--dump-html` to save the page
- Use `--verbose-selectors` to see match counts
- Test selectors in browser DevTools

**Pagination not working?**
- Use `--dry-run` to see discovered pagination links
- Check that links are `<a>` tags with `href` attributes

**Browser not starting?**
- Run `playwright install`

## Full Documentation

See `LIST_CRAWL_GUIDE.md` for complete documentation.

