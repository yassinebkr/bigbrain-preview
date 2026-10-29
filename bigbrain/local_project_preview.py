"""Leased interactive previews rendered by a local browser with scoped HTTP access."""

import asyncio
import base64
from dataclasses import dataclass, field
import secrets
import tempfile
import time
from urllib.parse import urlsplit

from .local_projects import ProjectAccessError
from .local_project_web import run_web_tests


@dataclass
class Preview:
    project_id: str
    revision: int
    ready: object
    close: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    page: object = None
    task: object = None
    touched: float = field(default_factory=time.monotonic)
    blocked_requests: int = 0


class ProjectPreviews:
    """Own bounded browser lifetimes independently of project source folders."""

    def __init__(self, registry):
        self.registry = registry
        self.sessions = {}

    async def open(self, project_id, revision, entry_point, web_stack='static'):
        if len(self.sessions) >= 3:
            raise ProjectAccessError('Close an existing local preview before opening another')
        identifier = secrets.token_urlsafe(32)
        session = Preview(project_id, revision, asyncio.get_running_loop().create_future())
        self.sessions[identifier] = session

        async def browser(url, acceptance):
            from playwright.async_api import async_playwright
            origin = urlsplit(url)
            with tempfile.TemporaryDirectory(prefix='bigbrain-preview-browser-') as home:
                async with async_playwright() as driver:
                    instance = await driver.chromium.launch(chromium_sandbox=True,
                        env={'PATH': '/usr/bin:/bin', 'HOME': home},
                        args=['--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                              '--disable-features=WebTransport'])
                    try:
                        context = await instance.new_context(viewport={'width': 1280, 'height': 800},
                            service_workers='block', accept_downloads=False)
                        async def route(request):
                            target = urlsplit(request.request.url)
                            if (target.scheme, target.netloc) == (origin.scheme, origin.netloc):
                                await request.continue_()
                            else:
                                session.blocked_requests += 1
                                await request.abort()
                        await context.route('**/*', route)
                        await context.add_init_script("window.WebSocket = class { constructor() { throw new Error('External connections disabled in preview'); } }; window.EventSource = window.WebSocket; window.RTCPeerConnection = window.WebSocket; window.webkitRTCPeerConnection = window.WebSocket; window.WebTransport = window.WebSocket;")
                        session.page = await context.new_page()
                        async def close_popup(page):
                            if page is not session.page:
                                await page.close()
                        context.on('page', close_popup)
                        session.page.on('dialog', lambda dialog: dialog.dismiss())
                        await session.page.goto(url, wait_until='networkidle', timeout=8000)
                        session.ready.set_result(True)
                        while not session.close.is_set() and time.monotonic() - session.touched < 90:
                            try:
                                await asyncio.wait_for(session.close.wait(), timeout=1)
                            except TimeoutError:
                                pass
                        return {'status': 'closed', 'cases': []}
                    finally:
                        await instance.close()

        async def run():
            try:
                result = await run_web_tests(self.registry, project_id, revision, entry_point,
                    web_stack=web_stack, browser_operation=browser)
                if not session.ready.done():
                    session.ready.set_exception(ProjectAccessError(result.get('reason') or result.get('diagnostic_output') or 'Preview startup failed'))
            except Exception as exc:
                if not session.ready.done():
                    session.ready.set_exception(ProjectAccessError(str(exc)))
            finally:
                self.sessions.pop(identifier, None)
        session.task = asyncio.create_task(run())
        try:
            await asyncio.wait_for(asyncio.shield(session.ready), timeout=150)
            return {'previewId': identifier, 'width': 1280, 'height': 800,
                    'projectId': project_id, 'revision': revision, 'network': 'http_preview_origin_only'}
        except BaseException:
            await self.close(identifier)
            if not session.ready.done():
                session.ready.cancel()
            raise

    async def frame(self, identifier, project_id, revision, action=None):
        session = self.sessions.get(identifier)
        if session is None or (session.project_id, session.revision) != (project_id, revision):
            raise ProjectAccessError('Local preview expired; open it again')
        with self.registry.access(project_id, revision, 'execute'):
            pass
        session.touched = time.monotonic()
        async with session.lock:
            page = session.page
            action = action or {'type': 'frame'}
            kind = action.get('type')
            if kind == 'click':
                x, y = action.get('x'), action.get('y')
                if type(x) not in (int, float) or type(y) not in (int, float) or not (0 <= x < 1280 and 0 <= y < 800):
                    raise ProjectAccessError('Preview coordinates are outside the viewport')
                await page.mouse.click(x, y)
            elif kind == 'text':
                text = action.get('text')
                if not isinstance(text, str) or not 1 <= len(text) <= 1000:
                    raise ProjectAccessError('Preview text must contain 1 to 1000 characters')
                await page.keyboard.insert_text(text)
            elif kind == 'key':
                key = action.get('key')
                if key not in {'Enter', 'Tab', 'Backspace', 'Delete', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'}:
                    raise ProjectAccessError('Unsupported preview key')
                await page.keyboard.press(key)
            elif kind == 'scroll':
                delta = action.get('delta')
                if type(delta) not in (int, float) or not -1000 <= delta <= 1000:
                    raise ProjectAccessError('Preview scroll exceeds limit')
                await page.mouse.wheel(0, delta)
            elif kind == 'reload':
                await page.reload(wait_until='networkidle', timeout=8000)
            elif kind != 'frame':
                raise ProjectAccessError('Unsupported preview interaction')
            screenshot = await page.screenshot(type='png', timeout=3000)
            if len(screenshot) > 2_000_000:
                raise ProjectAccessError('Preview frame exceeds image budget')
            return {'image': base64.b64encode(screenshot).decode(), 'width': 1280, 'height': 800,
                    'blockedRequests': session.blocked_requests}

    async def close(self, identifier):
        session = self.sessions.get(identifier)
        if session:
            session.close.set()
            session.task.cancel()
            await asyncio.gather(session.task, return_exceptions=True)

    async def cleanup(self):
        await asyncio.gather(*(self.close(identifier) for identifier in list(self.sessions)))
