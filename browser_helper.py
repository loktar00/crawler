#!/usr/bin/env python3
"""
Browser Helper CLI

A CLI tool for browser interactions complementing the Playwright MCP server.
Reuses anti-detection patterns from crawler.py.

Usage:
    python browser_helper.py navigate <url> [--screenshot <path>] [--wait <ms>]
    python browser_helper.py screenshot <url> <output_path>
    python browser_helper.py click <url> <selector> [--screenshot-after <path>]
    python browser_helper.py type <url> <selector> <text>
    python browser_helper.py evaluate <url> <js_expression>
    python browser_helper.py dump-text <url>
    python browser_helper.py dump-links <url>
    python browser_helper.py fill-and-submit <url> --fields '{"sel": "val"}' --submit <selector>
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DEFAULT_COOKIES = "output/browser_session/cookies.json"

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--start-maximized",
]

ANTI_DETECT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
"""


def create_context(browser, cookies_file=None):
    """Create a browser context with anti-detection settings."""
    vw = 1920 + random.randint(-100, 100)
    vh = 1080 + random.randint(-100, 100)

    ctx = browser.new_context(
        viewport={"width": vw, "height": vh},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="America/New_York",
    )

    if cookies_file:
        cf = Path(cookies_file)
        if cf.exists():
            try:
                cookies = json.loads(cf.read_text())
                ctx.add_cookies(cookies)
            except Exception:
                pass

    return ctx


def open_page(ctx, url, wait_ms=0):
    """Open a page with anti-detection and optional wait."""
    page = ctx.new_page()
    page.add_init_script(ANTI_DETECT_SCRIPT)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(random.uniform(1.0, 2.5))
    if wait_ms > 0:
        page.wait_for_timeout(wait_ms)
    return page


def save_cookies(ctx, cookies_file):
    """Save context cookies to file."""
    if not cookies_file:
        return
    cf = Path(cookies_file)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cookies = ctx.cookies()
    cf.write_text(json.dumps(cookies, indent=2))


def output_json(data):
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# --- Commands ---


def cmd_navigate(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url, args.wait)

        result = {"url": page.url, "title": page.title()}

        if args.screenshot:
            page.screenshot(path=args.screenshot, full_page=True)
            result["screenshot"] = args.screenshot

        save_cookies(ctx, args.cookies_file)
        output_json(result)
        browser.close()


def cmd_screenshot(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)
        page.screenshot(path=args.output_path, full_page=True)
        output_json({"url": page.url, "screenshot": args.output_path})
        browser.close()


def cmd_click(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)
        page.click(args.selector, timeout=10000)
        time.sleep(random.uniform(0.5, 1.5))

        result = {"url": page.url, "title": page.title(), "clicked": args.selector}

        if args.screenshot_after:
            page.screenshot(path=args.screenshot_after, full_page=True)
            result["screenshot"] = args.screenshot_after

        save_cookies(ctx, args.cookies_file)
        output_json(result)
        browser.close()


def cmd_type(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)
        page.fill(args.selector, args.text, timeout=10000)

        result = {"url": page.url, "typed": args.text, "selector": args.selector}
        save_cookies(ctx, args.cookies_file)
        output_json(result)
        browser.close()


def cmd_evaluate(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)
        result = page.evaluate(args.expression)
        output_json({"url": page.url, "result": result})
        browser.close()


def cmd_dump_text(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)
        text = page.evaluate("document.body.innerText")
        output_json({"url": page.url, "title": page.title(), "text": text})
        browser.close()


def cmd_dump_links(args):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)
        links = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim().substring(0, 200),
                href: a.href
            }))
        """)
        output_json({"url": page.url, "links": links})
        browser.close()


def cmd_fill_and_submit(args):
    fields = json.loads(args.fields)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=BROWSER_ARGS)
        ctx = create_context(browser, args.cookies_file)
        page = open_page(ctx, args.url)

        for selector, value in fields.items():
            page.fill(selector, value, timeout=10000)
            time.sleep(random.uniform(0.3, 0.8))

        page.click(args.submit, timeout=10000)
        time.sleep(random.uniform(1.0, 3.0))
        page.wait_for_load_state("domcontentloaded")

        result = {"url": page.url, "title": page.title(), "fields_filled": len(fields)}

        if args.screenshot_after:
            page.screenshot(path=args.screenshot_after, full_page=True)
            result["screenshot"] = args.screenshot_after

        save_cookies(ctx, args.cookies_file)
        output_json(result)
        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Browser Helper CLI")
    parser.add_argument("--cookies-file", default=DEFAULT_COOKIES, help="Cookie file path")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--visible", action="store_true", help="Run with visible browser")

    sub = parser.add_subparsers(dest="command", required=True)

    # navigate
    p_nav = sub.add_parser("navigate")
    p_nav.add_argument("url")
    p_nav.add_argument("--screenshot", help="Screenshot output path")
    p_nav.add_argument("--wait", type=int, default=0, help="Extra wait in ms")

    # screenshot
    p_ss = sub.add_parser("screenshot")
    p_ss.add_argument("url")
    p_ss.add_argument("output_path")

    # click
    p_click = sub.add_parser("click")
    p_click.add_argument("url")
    p_click.add_argument("selector")
    p_click.add_argument("--screenshot-after", help="Screenshot after clicking")

    # type
    p_type = sub.add_parser("type")
    p_type.add_argument("url")
    p_type.add_argument("selector")
    p_type.add_argument("text")

    # evaluate
    p_eval = sub.add_parser("evaluate")
    p_eval.add_argument("url")
    p_eval.add_argument("expression")

    # dump-text
    p_dt = sub.add_parser("dump-text")
    p_dt.add_argument("url")

    # dump-links
    p_dl = sub.add_parser("dump-links")
    p_dl.add_argument("url")

    # fill-and-submit
    p_fs = sub.add_parser("fill-and-submit")
    p_fs.add_argument("url")
    p_fs.add_argument("--fields", required=True, help='JSON: {"selector": "value"}')
    p_fs.add_argument("--submit", required=True, help="Submit button selector")
    p_fs.add_argument("--screenshot-after", help="Screenshot after submit")

    args = parser.parse_args()

    if args.visible:
        args.headless = False

    commands = {
        "navigate": cmd_navigate,
        "screenshot": cmd_screenshot,
        "click": cmd_click,
        "type": cmd_type,
        "evaluate": cmd_evaluate,
        "dump-text": cmd_dump_text,
        "dump-links": cmd_dump_links,
        "fill-and-submit": cmd_fill_and_submit,
    }

    try:
        commands[args.command](args)
    except Exception as e:
        output_json({"error": str(e), "command": args.command})
        sys.exit(1)


if __name__ == "__main__":
    main()
