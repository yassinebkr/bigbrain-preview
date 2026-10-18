"""Deterministic Chromium lifecycle check against the real built UI/server.

Run after `cd web-ui && npm run build`:
  .venv/bin/python -m tools.check_ui_lifecycle
All data/events are isolated TEST fixtures. No LLM, real task dispatch or
external provider probe. This is NOT a live generated-product campaign.
"""

import asyncio
import json
import os
import tempfile
import aiohttp
from pathlib import Path
from unittest.mock import AsyncMock, patch

from playwright.async_api import async_playwright

from bigbrain.bus.bus import MessageBus
from bigbrain.web.server import WebServer, WEBUI_DIST


async def check(root: Path):
    for setting, name in {
        "BIGBRAIN_SESSIONS_DIR": "sessions", "BIGBRAIN_WORKSPACE_DIR": "workspace",
        "BIGBRAIN_EVIDENCE_ROOT": "evidence", "BIGBRAIN_MEMORY_DIR": "memory",
        "BIGBRAIN_SOUL_FILE": "soul.json", "BIGBRAIN_ATTACHMENTS_DIR": "attachments",
        "BIGBRAIN_TASKS_FILE": "tasks.json",
    }.items():
        os.environ[setting] = str(root / name)
    os.environ.pop("BIGBRAIN_WEB_PASSWORD", None)
    project = root / 'workspace' / 'sandbox' / 'preview-demo'
    project.mkdir(parents=True)
    (project / 'index.html').write_text('<h1>Isolated preview fixture</h1>')
    (project / '.project.json').write_text(json.dumps({
        'deliverable_type': 'web_app', 'entry_point': 'index.html', 'verified': True}))
    assert (WEBUI_DIST / "index.html").is_file(), "Build web-ui first"
    bus = MessageBus(root / "logs", auth=None)
    server = WebServer(bus, host="127.0.0.1", port=0)
    server._sessions.append_message("sess-demo", "user", "Build running tracker")
    server._sessions.append_message("sess-demo", "assistant", "Je prépare le projet de running.")
    async def emit(event, task_id, **data):
        await bus.broadcast_event(source="lifecycle_test", event_type=event,
            payload={"session_id": "sess-demo", "task_id": task_id, **data})
    await server.start()
    try:
        await emit("task.routing", "web", description="Running tracker")
        await emit("task.received", "web")
        await emit("subtask.started", "web", subtask_id="web-file", brain="web_app_brain_0", description="Write App")
        await emit("task.routing", "board", description="Laundry task")
        await emit("task.received", "board")
        await emit("subtask.started", "board", subtask_id="board-task", brain="taskboard", description="Add task")
        server._replay_buffer.clear()
        port = server._site._server.sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(viewport={"width": 1280, "height": 900})
            # A cold reload: no locally cached transcript or run state.
            state = json.dumps({"state": {"activeSessionKey": "sess-demo", "view": "chat"}, "version": 0})
            await context.add_init_script(
                "localStorage.setItem('aplot_auth_token','isolated-browser-test');"
                f"localStorage.setItem('aplot-ai-storage', {json.dumps(state)});")
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                await page.goto(url)
                await page.get_by_text("Je prépare le projet de running.", exact=True).wait_for()
                await page.get_by_label("Conversation activities").wait_for()
                await emit("subtask.complete", "board", subtask_id="board-task")
                # Deliberately stale project fields verify the defensive UI guard.
                await emit("task.complete", "board", result_kind="taskboard", project_path="sandbox/unrelated",
                           entry_point="main.py", runnable=True)
                await page.get_by_role("button", name="Open taskboard", exact=True).wait_for()
                assert await page.get_by_role("button", name="Run project", exact=True).count() == 0
                await page.get_by_role("button", name="Open taskboard", exact=True).click()
                await page.get_by_role("button", name="Return to ongoing activity", exact=True).wait_for()
                await page.get_by_role("button", name="Workspace", exact=True).first.click()
                await page.get_by_role("button", name="Return to ongoing activity", exact=True).wait_for()
                await page.get_by_role("button", name="Return to ongoing activity", exact=True).click()
                await page.get_by_text("Je prépare le projet de running.", exact=True).wait_for()
                await page.reload()
                await page.get_by_role("button", name="Open taskboard", exact=True).wait_for()
                await page.get_by_text("web_app_brain_0 — Write App", exact=True).wait_for()
                # Opening a second tab recovers the same independently tracked work.
                second = await context.new_page()
                second.on("pageerror", lambda error: errors.append(str(error)))
                await second.goto(url)
                await second.get_by_role("button", name="Open taskboard", exact=True).wait_for()
                await emit("subtask.complete", "web", subtask_id="web-file")
                await emit("task.complete", "web", deliverable_type='web_app', runnable=True,
                    project_path='sandbox/preview-demo', entry_point='index.html',
                    preview_url='http://127.0.0.1:3200')
                await page.get_by_text("Run complete — Running tracker", exact=True).wait_for()
                await second.get_by_text("Run complete — Running tracker", exact=True).wait_for()
                await page.reload()
                await page.get_by_text("Run complete — Running tracker", exact=True).wait_for()
                assert await page.get_by_label("Stop generation").count() == 0
                frame = page.locator('iframe[title^="Aperçu de"]')
                await frame.wait_for()
                await page.frame_locator('iframe[title^="Aperçu de"]').get_by_text('Isolated preview fixture').wait_for()
                preview_url = await frame.get_attribute('src')
                assert preview_url != 'http://127.0.0.1:3200'
                await second.close()
                await page.get_by_role('button', name='Workspace', exact=True).first.click()
                async with aiohttp.ClientSession() as client:
                    for attempt in range(30):
                        try:
                            async with client.get(preview_url):
                                pass
                        except aiohttp.ClientConnectionError:
                            break
                        await asyncio.sleep(0.1)
                    else:
                        raise AssertionError('Preview port remained open after leaving chat')
                await page.reload()
                await page.get_by_role('button', name='Open project', exact=True).first.click()
                preview_button = page.get_by_role('button', name='Preview', exact=True).first
                await preview_button.wait_for()
                assert await page.locator('iframe').count() == 0
                await preview_button.click()
                await page.frame_locator('iframe').get_by_text('Isolated preview fixture').wait_for()
                workspace_url = await page.locator('iframe').get_attribute('src')
                await page.get_by_role('button', name='Code', exact=True).click()
                assert await page.locator('iframe').count() == 0
                async with aiohttp.ClientSession() as client:
                    for attempt in range(30):
                        try:
                            async with client.get(workspace_url):
                                pass
                        except aiohttp.ClientConnectionError:
                            break
                        await asyncio.sleep(0.1)
                    else:
                        raise AssertionError('Workspace preview port remained open in Code mode')
                assert not errors, errors
                print(json.dumps({"cold_history": True, "parallel_runs": True,
                    "taskboard_action": True, "navigation": True, "reload": True,
                    "two_tabs": True, "terminal_docking": True,
                    "preview_reacquired": True, "preview_released": True,
                    "workspace_lazy_preview": True, "page_errors": errors}))
            finally:
                await context.close()
                await browser.close()
    finally:
        await server.stop()
        await bus.close()


async def main():
    with tempfile.TemporaryDirectory(prefix="bigbrain-ui-lifecycle-") as directory:
        with patch("bigbrain.llm.model_registry.verify_all", new=AsyncMock(return_value={})):
            await check(Path(directory))


if __name__ == "__main__":
    asyncio.run(main())
