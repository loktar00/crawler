# Crawler Project — Claude Code Context

## Overview
Web crawler suite at `/opt/crawler/` on a Proxmox LXC container. Uses Playwright 1.58+ and curl-cffi for scraping with CloudFlare bypass. YAML recipe system for defining scraping targets. Integrated with n8n for scheduled runs via SSH.

## Environment
- **Python**: 3.11 (venv at `/opt/crawler/venv/`)
- **Node.js**: 22 LTS (for Playwright MCP server)
- **Display**: Xvfb on `:99` (for headless browser automation, VNC for auth)
- **Activate venv**: `source /opt/crawler/venv/bin/activate`

## Key Files

| File | Purpose |
|------|---------|
| `crawler.py` | Main crawler — supports `--mode list` for recipe-based list scraping |
| `list_crawler.py` | List-mode crawler implementation |
| `crawler_config.py` | Config: URLs, depth, domains, headless mode, rate limits |
| `recipe_loader.py` | Loads and validates YAML recipe files |
| `validate_recipe.py` | CLI tool to validate recipe YAML |
| `scrape_metrics.py` | Social media metrics scraper (Instagram, Facebook, YouTube, LinkedIn) |
| `browser_helper.py` | CLI for browser actions: navigate, click, type, screenshot, etc. |
| `api_server.py` | FastAPI HTTP API for sending tasks to Claude Code |
| `data_server.py` | HTTP file server for output data |

## Recipe System

Recipes are YAML files in `recipes/`. Template:

```yaml
start_urls:
  - "https://example.com/page"

list_scope_css: "div.item"       # CSS selector scoping each item
item_link_css: "a[href]"         # Link selector within each item

pagination:
  type: next                     # "next" or "url_template"
  next_css: "a.next-page"       # For type: next

limits:
  max_list_pages: 5
  max_items: 100

output:
  items_jsonl: "output/my_items.jsonl"
  pages_jsonl: "output/my_pages.jsonl"
```

**Workflow**: Create recipe → `python validate_recipe.py recipes/my_recipe.yaml` → `python crawler.py --mode list --recipe recipes/my_recipe.yaml --headless`

## Browser Helper

```bash
# Screenshot a page
python browser_helper.py screenshot https://example.com /tmp/test.png

# Navigate and get page info
python browser_helper.py navigate https://example.com --screenshot /tmp/nav.png

# Click an element
python browser_helper.py click https://example.com "button.submit"

# Fill form and submit
python browser_helper.py fill-and-submit https://example.com \
  --fields '{"#username": "user", "#password": "pass"}' \
  --submit "button[type=submit]"

# Dump all links as JSON
python browser_helper.py dump-links https://example.com

# Run JS and get result
python browser_helper.py evaluate https://example.com "document.title"
```

All commands output JSON to stdout. Use `--visible` for non-headless mode. Cookies are saved/loaded from `output/browser_session/cookies.json` by default.

## API Server (port 8080)

```bash
# Send a task
curl -X POST http://localhost:8080/task \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "List files in output/", "timeout": 60}'

# Continue a conversation
curl -X POST http://localhost:8080/task/continue \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "...", "prompt": "Now process those files"}'

# Open page for VNC login
curl -X POST http://localhost:8080/auth-prepare \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://facebook.com/login"}'

# Health check
curl http://localhost:8080/health
```

Service: `systemctl start claude-api`

## Data Server (port 8081)

```bash
curl http://localhost:8081/api/files          # List all output files as JSON
curl http://localhost:8081/files/cat-brown/facebook_posts.jsonl  # Download file
```

Browse at `http://<host>:8081/` for HTML directory listing.
Service: `systemctl start claude-data`

## n8n Integration
- SSH scripts: `run_cat_brown.sh`, `run_cat_brown_facebook.sh`, `run_cat_brown_metrics.sh`
- HTTP API: `POST http://<crawler-ip>:8080/task` with JSON body from n8n HTTP Request node
- Daily Facebook scrape at 6 AM, metrics at 8 PM

## Cookie/Session Management
- Cookies saved at `output/browser_session/cookies.json` (crawler) and `output/browser_session/metrics_cookies.json` (metrics)
- For authenticated sites (Facebook, etc.), first run with `--visible` flag and log in via VNC
- Or use `POST /auth-prepare` endpoint to open a login page on VNC display

## Conventions
- All output as JSONL (one JSON object per line) for items
- Recipes in `recipes/<project>/` subdirectories
- Python code uses the venv: `/opt/crawler/venv/bin/python`
- Always set `DISPLAY=:99` for browser operations
