"""WebAppBrain — browser-first project generation, validation and preview.

This worker intentionally does not inherit PythonBrain.  Its task vocabulary,
validation rules and process lifecycle are web-specific so a browser
application can never be accepted because a Python process merely printed a
description of one.
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseBrain
from ..bus.message import BusMessage


class WebAppBrain(BaseBrain):
    """Generate dependency-free web files and serve verified previews."""

    _active_previews: Dict[int, asyncio.subprocess.Process] = {}
    _preview_ports = range(3200, 3300)

    def __init__(self, name, bus, workspace=None, *, work_dir: Path,
                 llm_provider=None):
        super().__init__(name, bus, workspace)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.llm_provider = llm_provider
        self._preview_process: Optional[asyncio.subprocess.Process] = None

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        payload = message.payload or {}
        task_type = payload.get("type")
        if task_type == "write_web_file":
            return await self._write_web_file(payload)
        if task_type in {"assemble_and_preview", "run_web_project"}:
            return await self._assemble_and_preview(payload)
        raise ValueError(f"Unknown WebAppBrain task type: {task_type}")

    async def handle_message(self, message: BusMessage) -> None:
        return None

    @staticmethod
    def _safe_relative(path: str) -> Path:
        candidate = Path(path)
        if (not path or candidate.is_absolute() or ".." in candidate.parts
                or any(part.startswith(".") for part in candidate.parts)):
            raise ValueError(f"Unsafe web project path: {path!r}")
        return candidate

    @classmethod
    def _safe_project_name(cls, value: str) -> Path:
        """Project identifiers are single folders, never relative paths."""
        candidate = cls._safe_relative(value)
        return Path(candidate.name)

    @staticmethod
    def _extract_code(raw: str) -> str:
        text = raw.strip()
        if text.startswith("```"):
            first = text.find("\n")
            last = text.rfind("```")
            if first >= 0 and last > first:
                text = text[first + 1:last].strip()
        return text + ("\n" if text and not text.endswith("\n") else "")

    @staticmethod
    def _workspace_relative(path: Path) -> str:
        try:
            from ..web.fs_api import workspace_root
            return path.resolve().relative_to(workspace_root().resolve()).as_posix()
        except (ImportError, ValueError):
            return path.name

    async def _write_web_file(self, payload: dict) -> Dict[str, Any]:
        if self.llm_provider is None:
            raise RuntimeError("WebAppBrain requires an LLM provider")
        project_name = self._safe_project_name(str(payload.get("project_name") or "web-app"))
        file_path = self._safe_relative(str(payload.get("file_path") or ""))
        target = (self.work_dir / project_name / file_path).resolve()
        project_dir = (self.work_dir / project_name).resolve()
        if project_dir not in target.parents:
            raise ValueError("Web file escapes its project directory")

        await self.send_progress({
            "stage": "writing_web_file", "path": str(file_path),
            "project_name": str(project_name),
        })
        prompt = f"""Create exactly one file for a browser-first web application.

User request: {payload.get('user_request', '')}
Project: {project_name}
File: {file_path}
Purpose: {payload.get('purpose', '')}

Architect contract:
{payload.get('architect_spec', '')}

Rules:
- Return ONLY the complete raw file contents, with no markdown fence.
- Implement real browser interaction; never print a textual imitation of UI.
- Use accessible semantic HTML and responsive CSS.
- Use only relative local assets and dependency-free JavaScript in this phase.
- No placeholders, TODOs, fake data presented as external/live data, or missing handlers.
- Keep contracts with the other planned files exactly as specified.
"""
        raw = await self.llm_provider.chat_complete(
            messages=[{"role": "system", "content": "You implement production-quality web application files."},
                      {"role": "user", "content": prompt}],
            stream=False, max_tokens=8192, temperature=0.2,
        )
        content = self._extract_code(raw)
        if not content.strip():
            raise ValueError(f"LLM returned an empty file for {file_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        await self.send_event("workspace.file_written", {
            "path": self._workspace_relative(target),
            "project_name": project_name.as_posix(),
        })
        return {"success": True, "path": self._workspace_relative(target),
                "file_path": file_path.as_posix(),
                "project_name": project_name.as_posix(), "bytes": len(content.encode())}

    @classmethod
    def validate_project(cls, project_dir: Path, all_files: list) -> Dict[str, Any]:
        planned = [cls._safe_relative(str(item.get("path") or "")) for item in all_files]
        missing = [p.as_posix() for p in planned if not (project_dir / p).is_file()]
        errors: list[str] = []
        if missing:
            errors.append("missing planned files: " + ", ".join(missing))
        for required in ("index.html", "styles.css", "app.js", "tests/acceptance.json"):
            if not (project_dir / required).is_file():
                errors.append(f"missing required web artifact: {required}")

        index_path = project_dir / "index.html"
        if index_path.is_file():
            html = index_path.read_text(encoding="utf-8", errors="replace")
            if not re.search(r"<main\b", html, re.I):
                errors.append("index.html must contain a semantic <main> region")
            for ref in re.findall(r'''(?:src|href)=["']([^"']+)["']''', html, re.I):
                if ref.startswith(("http://", "https://", "//", "#", "data:")):
                    continue
                local = ref.split("?", 1)[0].split("#", 1)[0].lstrip("/")
                if local and not (project_dir / local).is_file():
                    errors.append(f"index.html references missing local asset: {local}")

        acceptance_path = project_dir / "tests/acceptance.json"
        acceptance = None
        if acceptance_path.is_file():
            try:
                acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
                cases = None
                if isinstance(acceptance, dict):
                    cases = acceptance.get("cases") or acceptance.get("tests")
                if not isinstance(cases, list) or not cases:
                    errors.append("tests/acceptance.json must define non-empty cases or tests")
                elif any(not isinstance(case, dict)
                         or not (case.get("name") or case.get("title"))
                         or not case.get("assertions")
                         for case in cases):
                    errors.append("each acceptance case needs a name/title and assertions")
            except (OSError, json.JSONDecodeError):
                errors.append("tests/acceptance.json is not valid JSON")

        for path in project_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".html", ".css", ".js"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"\b(?:TODO|FIXME)\b", text):
                    errors.append(f"placeholder marker remains in {path.relative_to(project_dir)}")

        return {"passed": not errors, "errors": errors,
                "files": [p.as_posix() for p in planned], "acceptance": acceptance}

    @classmethod
    def _free_port(cls) -> Optional[int]:
        for port in cls._preview_ports:
            if port in cls._active_previews:
                continue
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError:
                    continue
            return port
        return None

    async def _assemble_and_preview(self, payload: dict) -> Dict[str, Any]:
        started = time.time()
        project_name = self._safe_project_name(str(payload.get("project_name") or "web-app"))
        project_dir = (self.work_dir / project_name).resolve()
        validation = self.validate_project(project_dir, payload.get("all_files") or [])
        project_path = self._workspace_relative(project_dir)
        if not validation["passed"]:
            return {"success": False, "runnable": False, "project_name": project_name.as_posix(),
                    "project_path": project_path, "entry_point": "index.html",
                    "deliverable_type": "web_app",
                    "error": "; ".join(validation["errors"]), "verification": validation}

        port = self._free_port()
        if port is None:
            raise RuntimeError("No preview port available in 3200-3299")
        if self._preview_process and self._preview_process.returncode is None:
            self._preview_process.terminate()
            try:
                await asyncio.wait_for(self._preview_process.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._preview_process.kill()
                await self._preview_process.wait()

        self._preview_process = await asyncio.create_subprocess_exec(
            "python3", "-m", "http.server", str(port), "--bind", "127.0.0.1",
            cwd=str(project_dir), stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_previews[port] = self._preview_process
        await asyncio.sleep(0.15)
        if self._preview_process.returncode is not None:
            error = (await self._preview_process.stderr.read()).decode(errors="replace")
            self._active_previews.pop(port, None)
            return {"success": False, "runnable": False, "error": error[:1000],
                    "verification": validation}

        manifest = {
            "name": project_name.name, "created": time.time(),
            "deliverable_type": "web_app", "interaction_mode": "browser",
            "entry_point": "index.html", "run": {"kind": "static_preview"},
            "verified": True,
        }
        (project_dir / ".project.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        url = f"http://127.0.0.1:{port}"
        await self.send_progress({"stage": "preview_ready", "url": url, "port": port})
        return {
            "success": True, "runnable": True, "project_name": project_name.name,
            "project_path": project_path, "entry_point": "index.html",
            "deliverable_type": "web_app",
            "files_written": validation["files"], "preview_url": url,
            "preview_port": port, "server_running": True,
            "server_pid": self._preview_process.pid, "verification": validation,
            "execution_time": time.time() - started,
        }

    async def cleanup(self) -> None:
        if self._preview_process and self._preview_process.returncode is None:
            self._preview_process.terminate()
            try:
                await asyncio.wait_for(self._preview_process.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._preview_process.kill()
                await self._preview_process.wait()
        for port, process in list(self._active_previews.items()):
            if process is self._preview_process:
                self._active_previews.pop(port, None)
        self._preview_process = None
