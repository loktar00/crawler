"""
Workflow Replay Engine — replays saved workflows using Playwright sync API.

No AI needed: reads the step list and executes each action sequentially
with human-like delays and anti-detection patterns.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, Page, BrowserContext

from workflow_models import Workflow, WorkflowStep

logger = logging.getLogger(__name__)

# Reuse browser_helper patterns
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

DEFAULT_COOKIES = Path("output/browser_session/cookies.json")

# Template pattern: {{input.field_name}}
_TEMPLATE_RE = re.compile(r"\{\{input\.(\w+)\}\}")


def interpolate(value: str, inputs: dict[str, str]) -> str:
    """Replace {{input.xxx}} placeholders with actual values."""
    def replacer(m: re.Match) -> str:
        key = m.group(1)
        return inputs.get(key, m.group(0))
    return _TEMPLATE_RE.sub(replacer, value)


def interpolate_params(params: dict[str, Any], inputs: dict[str, str]) -> dict[str, Any]:
    """Deep-interpolate all string values in a params dict."""
    result = {}
    for k, v in params.items():
        if isinstance(v, str):
            result[k] = interpolate(v, inputs)
        elif isinstance(v, dict):
            result[k] = interpolate_params(v, inputs)
        elif isinstance(v, list):
            result[k] = [
                interpolate(item, inputs) if isinstance(item, str) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


class WorkflowPlayer:
    """Replays a workflow using Playwright sync API."""

    def __init__(
        self,
        workflow: Workflow,
        inputs: dict[str, str] | None = None,
        headless: bool = True,
        cookies_file: Path | str | None = None,
    ):
        self.workflow = workflow
        self.inputs = inputs or {}
        self.headless = headless
        self.cookies_file = Path(cookies_file) if cookies_file else DEFAULT_COOKIES
        self.log_lines: list[str] = []

    def _log(self, msg: str):
        logger.info(msg)
        self.log_lines.append(msg)

    def run(self) -> dict:
        """Execute all steps. Returns {"status": ..., "log": [...]}."""
        self._log(f"Starting workflow: {self.workflow.name}")
        self._log(f"Steps: {len(self.workflow.steps)}, Headless: {self.headless}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, args=BROWSER_ARGS)

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

            # Load cookies
            if self.cookies_file.exists():
                try:
                    cookies = json.loads(self.cookies_file.read_text())
                    ctx.add_cookies(cookies)
                    self._log(f"Loaded {len(cookies)} cookies")
                except Exception as e:
                    self._log(f"Warning: could not load cookies: {e}")

            page = ctx.new_page()
            page.add_init_script(ANTI_DETECT_SCRIPT)

            status = "completed"
            try:
                for step in self.workflow.steps:
                    self._execute_step(page, ctx, step)
                    # Human-like delay between actions
                    time.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                self._log(f"ERROR at step {step.seq}: {e}")
                status = "failed"

            # Save cookies back
            try:
                self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
                cookies = ctx.cookies()
                self.cookies_file.write_text(json.dumps(cookies, indent=2))
                self._log(f"Saved {len(cookies)} cookies")
            except Exception as e:
                self._log(f"Warning: could not save cookies: {e}")

            browser.close()

        self._log(f"Workflow finished: {status}")
        return {"status": status, "log": self.log_lines}

    def _execute_step(self, page: Page, ctx: BrowserContext, step: WorkflowStep):
        """Execute a single workflow step."""
        params = interpolate_params(step.params, self.inputs)
        action = step.action
        self._log(f"[Step {step.seq}] {step.description or action}")

        if action == "navigate":
            url = params.get("url", "")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(random.uniform(1.0, 2.5))

        elif action == "click":
            locator = self._resolve_locator(page, params)
            locator.click(timeout=15000)

        elif action == "type":
            locator = self._resolve_locator(page, params)
            text = params.get("text", "")
            slowly = params.get("slowly", False)
            if slowly:
                locator.press_sequentially(text, delay=random.randint(50, 120))
            else:
                locator.fill(text, timeout=15000)
            if params.get("submit"):
                page.keyboard.press("Enter")

        elif action == "fill_form":
            fields = params.get("fields", [])
            for field in fields:
                ref_locator = page.locator(f'[data-ref="{field["ref"]}"]') if field.get("ref") else None
                if field.get("type") == "checkbox":
                    if ref_locator:
                        if field.get("value") == "true":
                            ref_locator.check()
                        else:
                            ref_locator.uncheck()
                else:
                    if ref_locator:
                        ref_locator.fill(field.get("value", ""))
                time.sleep(random.uniform(0.2, 0.5))

        elif action == "select_option":
            locator = self._resolve_locator(page, params)
            values = params.get("values", [])
            locator.select_option(values, timeout=15000)

        elif action == "press_key":
            key = params.get("key", "")
            page.keyboard.press(key)

        elif action == "hover":
            locator = self._resolve_locator(page, params)
            locator.hover(timeout=15000)

        elif action == "wait_for":
            if params.get("text"):
                page.get_by_text(params["text"]).wait_for(timeout=30000)
            elif params.get("textGone"):
                page.get_by_text(params["textGone"]).wait_for(state="hidden", timeout=30000)
            elif params.get("time"):
                time.sleep(float(params["time"]))

        elif action == "evaluate":
            fn = params.get("function", "")
            page.evaluate(fn)

        elif action == "navigate_back":
            page.go_back()

        elif action == "file_upload":
            paths = params.get("paths", [])
            page.set_input_files("input[type=file]", paths)

        elif action == "handle_dialog":
            # Dialog handling is tricky in replay; set up a listener
            accept = params.get("accept", True)
            page.on("dialog", lambda d: d.accept() if accept else d.dismiss())

        elif action == "drag":
            src = self._resolve_locator(page, {
                "ref": params.get("startRef"),
                "element": params.get("startElement"),
            })
            dst = self._resolve_locator(page, {
                "ref": params.get("endRef"),
                "element": params.get("endElement"),
            })
            src.drag_to(dst)

        elif action == "resize":
            w = params.get("width", 1280)
            h = params.get("height", 900)
            page.set_viewport_size({"width": w, "height": h})

        elif action == "tabs":
            tab_action = params.get("action", "list")
            if tab_action == "new":
                ctx.new_page()
            elif tab_action == "close":
                page.close()
            # select/list not easily replayable without AI context

        elif action == "close":
            pass  # Browser close handled at end

        else:
            self._log(f"  Unknown action: {action}, skipping")

    def _resolve_locator(self, page: Page, params: dict[str, Any]):
        """
        Resolve an element locator from params.
        Priority: selector > ref-based CSS > element description (text match).
        """
        # If there's a selector param, use it directly
        if params.get("selector"):
            return page.locator(params["selector"])

        # If there's a ref, try to use it as a snapshot ref (won't work in
        # replay without snapshot context). Fall back to element description.
        # The ref from recording is page-state-dependent, so we prefer element text.

        element = params.get("element", "")
        if element:
            # Try role-based locators first
            for role in ["button", "link", "textbox", "checkbox", "radio", "combobox"]:
                loc = page.get_by_role(role, name=element)
                if loc.count() > 0:
                    return loc.first
            # Fall back to text matching
            loc = page.get_by_text(element, exact=False)
            if loc.count() > 0:
                return loc.first
            # Last resort: use element description as label
            loc = page.get_by_label(element)
            if loc.count() > 0:
                return loc.first

        # Nothing matched — raise a useful error
        raise Exception(
            f"Could not locate element: selector={params.get('selector')}, "
            f"element={element}, ref={params.get('ref')}"
        )
