"""Playwright child process. Reads JSON on stdin, emits one bounded JSON report.

No scenario-supplied code is evaluated. Browser profiles are ephemeral and
network requests are restricted to the preview origin.
"""

from __future__ import annotations

import base64
import json
import sys
from urllib.parse import urlsplit


def run(request: dict) -> dict:
    try:
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        return {
            "status": "inconclusive",
            "error": "Install .[web] and run python -m playwright install chromium",
        }
    from ..brains.web_acceptance import normalize_acceptance

    acceptance = normalize_acceptance(request["acceptance"])
    if acceptance["schema_version"] != 2:
        return {
            "status": "inconclusive",
            "error": "Acceptance scenarios are descriptive; executable browser schema v2 is required",
        }
    url = request["url"]
    origin = urlsplit(url)
    if origin.scheme != "http" or origin.hostname != "127.0.0.1" or not origin.port:
        raise ValueError("browser runner requires a local HTTP preview")
    report = {
        "status": "passed",
        "cases": [],
        "console_errors": [],
        "network_errors": [],
        "blocked_requests": [],
    }
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:
            return {
                "status": "inconclusive",
                "error": f"Chromium unavailable: {str(exc)[:800]}. Run python -m playwright install chromium",
            }
        try:
            report["browser_version"] = browser.version
            for case in acceptance["cases"]:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    service_workers="block",
                    accept_downloads=False,
                )
                try:

                    def route_request(route):
                        target = urlsplit(route.request.url)
                        if (target.scheme, target.netloc) == (origin.scheme, origin.netloc):
                            route.continue_()
                        else:
                            if len(report["blocked_requests"]) < 50:
                                report["blocked_requests"].append(route.request.url[:300])
                            route.abort()

                    context.route("**/*", route_request)
                    context.add_init_script(
                        "window.WebSocket = class { constructor() { throw new Error('WebSocket disabled in verification'); } }; window.EventSource = window.WebSocket;"
                    )
                    page = context.new_page()
                    page.set_default_timeout(2500)
                    page.on(
                        "pageerror",
                        lambda error: (
                            report["console_errors"].append(str(error)[:1000])
                            if len(report["console_errors"]) < 50
                            else None
                        ),
                    )
                    page.on(
                        "console",
                        lambda msg: (
                            report["console_errors"].append(msg.text[:1000])
                            if msg.type == "error" and len(report["console_errors"]) < 50
                            else None
                        ),
                    )
                    page.on(
                        "response",
                        lambda response: (
                            report["network_errors"].append(
                                f"HTTP {response.status}: {response.url[:300]}"
                            )
                            if response.status >= 400 and len(report["network_errors"]) < 50
                            else None
                        ),
                    )
                    page.on("dialog", lambda dialog: dialog.dismiss())
                    outcome = {"name": case["name"], "status": "passed"}
                    try:
                        page.goto(url, wait_until="networkidle", timeout=8000)
                        expect(page.locator("main")).to_be_visible(timeout=2500)
                        for operation in case.get("steps", []) + case["assertions"]:
                            op = operation["op"]
                            selector = operation.get("selector")
                            locator = page.locator(selector) if selector else None
                            value = operation.get("value")
                            if op == "click":
                                locator.click()
                            elif op == "fill":
                                locator.fill(value)
                            elif op == "check":
                                locator.check()
                            elif op == "uncheck":
                                locator.uncheck()
                            elif op == "select":
                                locator.select_option(value)
                            elif op == "press":
                                locator.press(value)
                            elif op == "reload":
                                page.reload(wait_until="networkidle", timeout=8000)
                            elif op == "viewport":
                                page.set_viewport_size(
                                    {"width": operation["width"], "height": operation["height"]}
                                )
                            elif op == "visible":
                                expect(locator).to_be_visible(timeout=2500)
                            elif op == "text":
                                expect(locator).to_contain_text(value, timeout=2500)
                            elif op == "count":
                                expect(locator).to_have_count(value, timeout=2500)
                            elif op == "checked":
                                expect(locator).to_be_checked(checked=value, timeout=2500)
                            elif op == "value":
                                expect(locator).to_have_value(value, timeout=2500)
                            elif op == "storage_equals":
                                actual = page.evaluate(
                                    "key => localStorage.getItem(key)", operation["key"]
                                )
                                if actual != value:
                                    raise AssertionError(
                                        f"localStorage {operation['key']}: expected {value!r}, got {actual!r}"
                                    )
                            elif op == "no_overflow":
                                if page.evaluate(
                                    "document.documentElement.scrollWidth > innerWidth + 1"
                                ):
                                    raise AssertionError("Horizontal overflow")
                    except Exception as exc:
                        outcome.update(status="failed", error=str(exc)[:2000])
                        report["status"] = "failed"
                    finally:
                        # Fixed viewport bounds screenshot size; never capture an unbounded page.
                        try:
                            screenshot = page.screenshot(timeout=3000)
                            if len(screenshot) <= 700_000 and len(report["cases"]) < 3:
                                outcome["screenshot"] = base64.b64encode(screenshot).decode("ascii")
                            outcome["page_text"] = page.locator("body").inner_text(timeout=1000)[
                                :8000
                            ]
                        except Exception:
                            pass
                        report["cases"].append(outcome)
                finally:
                    context.close()
            if report["console_errors"] or report["network_errors"] or report["blocked_requests"]:
                report["status"] = "failed"
        finally:
            browser.close()
    return report


if __name__ == "__main__":
    try:
        result = run(json.loads(sys.stdin.read()))
    except Exception as exc:
        result = {"status": "failed", "error": str(exc)[:2000]}
    print(json.dumps(result))
