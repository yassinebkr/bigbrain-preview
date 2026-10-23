"""WebAppBrain — browser-first project generation, validation and preview.

This worker intentionally does not inherit PythonBrain.  Its task vocabulary,
validation rules and process lifecycle are web-specific so a browser
application can never be accepted because a Python process merely printed a
description of one.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseBrain
from .web_acceptance import ACCEPTANCE_CONTRACT, normalize_acceptance
from ..bus.message import BusMessage


class WebAppBrain(BaseBrain):
    """Generate dependency-free web files and serve verified previews."""
    project_kind = 'web_app'

    _active_previews: Dict[int, asyncio.subprocess.Process] = {}
    _preview_ports = range(3200, 3300)

    def __init__(self, name, bus, workspace=None, *, work_dir: Path,
                 llm_provider=None, model: str | None = None):
        super().__init__(name, bus, workspace)
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.llm_provider = llm_provider
        self.model = model
        self._preview_process: Optional[asyncio.subprocess.Process] = None

    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        with self.execution_scope(message.payload or {}) as payload:
            return await self._handle_task_in_scope(payload)

    async def _handle_task_in_scope(self, payload: dict) -> Dict[str, Any]:
        task_type = payload.get("type")
        if task_type == 'maintain_project':
            if payload.get('deliverable_type') != 'web_app':
                raise ValueError('WebAppBrain maintains browser projects only')
            return await self.maintain_project(payload)
        if task_type == "write_web_file":
            return await self._write_web_file(payload)
        if task_type in {"assemble_and_preview", "run_web_project"}:
            try:
                return await self._assemble_and_preview(payload)
            except asyncio.CancelledError:
                await self.cleanup()
                raise
        raise ValueError(f"Unknown WebAppBrain task type: {task_type}")

    async def handle_message(self, message: BusMessage) -> None:
        return None

    async def maintenance_diagnose(self, payload):
        from ..maintenance import ProjectTools
        result = await self.maintenance_verify({**payload, '_diagnostic_only': True}, ProjectTools(self._directory_context.get()))
        evidence = result.get('verification', {})
        status = evidence.get('verdict') or ('failed' if evidence.get('passed') is False else 'inconclusive')
        return {'status': status, **result}

    async def maintenance_prepare(self, payload):
        return {'status': 'ready', 'reason': 'The browser diagnostic pipeline provisions the declared web toolchain'}

    async def maintenance_verify(self, payload, tools):
        return await self._assemble_and_preview({**payload, '_maintenance_mode': True,
            'all_files': [{'path': p} for p in sorted(set(tools.inventory()) |
                         {f['path'] for f in payload.get('all_files', [])})],
            '_editable_paths': sorted(tools.changed)})

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

    def _project_dir(self, project_name: Path) -> Path:
        """Resolve a planned project without nesting it in another project."""
        if self._directory_context.get() is not None:
            return self.project_directory(str(project_name))
        manifest_path = self.work_dir / ".project.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            manifest = {}
        if manifest.get("sandbox") is True:
            base = self.work_dir
        elif manifest_path.is_file():
            selected_name = str(manifest.get("name") or self.work_dir.name)
            if project_name.name == selected_name:
                return self.work_dir.resolve()
            base = self.work_dir.parent
        else:
            base = self.work_dir
        return (base / project_name).resolve()

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
        if payload.get('_existing_source'):
            return await self.edit_inspected_file(payload, model=os.getenv('BIGBRAIN_WEB_MODEL', self.model or 'default'))
        if self.llm_provider is None:
            raise RuntimeError("WebAppBrain requires an LLM provider")
        project_name = self._safe_project_name(str(payload.get("project_name") or "web-app"))
        file_path = self._safe_relative(str(payload.get("file_path") or ""))
        if self._directory_context.get():
            self._directory_context.get().file(file_path.as_posix())
        project_dir = self._project_dir(project_name)
        target = (project_dir / file_path).resolve()
        if project_dir not in target.parents:
            raise ValueError("Web file escapes its project directory")

        await self.send_progress({
            "stage": "writing_web_file", "path": str(file_path),
            "project_name": str(project_name),
        })
        from .web_stack import REACT_FILES
        scaffold = REACT_FILES.get(file_path.as_posix()) if payload.get("web_stack") == "react_vite" else None
        dependency_sources = []
        for dependency in (payload.get("dependencies") or [])[:12]:
            source = project_dir / self._safe_relative(str(dependency))
            if source.is_file() and project_dir in source.resolve().parents:
                dependency_sources.append(f"### {dependency}\n{source.read_text(encoding='utf-8')[:12000]}")
        prompt = f"""Create exactly one file for a browser-first web application.

User request: {payload.get('user_request', '')}
Project: {project_name}
File: {file_path}
Purpose: {payload.get('purpose', '')}
Stack: {payload.get('web_stack', 'static')}

Architect contract:
{payload.get('architect_spec', '')}

Approved acceptance criteria (authoritative):
{json.dumps(payload.get('acceptance_contracts', []), ensure_ascii=False)}
Tests must assert these exact behaviours, not invent incompatible interfaces or replace existing expectations.

Implementation notes:
{payload.get('implementation_notes', '')}

Acceptance protocol (mandatory when writing tests/acceptance.json):
{ACCEPTANCE_CONTRACT}

Existing dependency source (use exact exports, selectors and storage keys):
{chr(10).join(dependency_sources)[:45000]}

Rules:
- Return ONLY the complete raw file contents, with no markdown fence.
- Implement real browser interaction; never print a textual imitation of UI.
- Use accessible semantic HTML and responsive CSS.
- For static: local HTML/CSS/JS only. For react_vite: React 19 + TypeScript + Vite, lucide-react icons and authored CSS; no other dependencies. The entry module is src/main.tsx, styles src/styles.css, App default-exported from src/App.tsx. Design a polished responsive interface with deliberate spacing/typography, accessible states and genuine interactions.
- No placeholders, TODOs, fake data presented as external/live data, or missing handlers.
- Keep contracts with the other planned files exactly as specified.
"""
        raw = scaffold if scaffold is not None else await self.complete_with_memory(
            messages=[{"role": "system", "content": "You implement production-quality web application files."},
                      {"role": "user", "content": prompt}],
            model=os.getenv("BIGBRAIN_WEB_MODEL", self.model or "default"),
            stream=False, max_tokens=8192, temperature=0.2,
        )
        content = self._extract_code(raw)
        if not content.strip():
            raise ValueError(f"LLM returned an empty file for {file_path}")
        if file_path.as_posix() == "tests/acceptance.json":
            try:
                content = json.dumps(normalize_acceptance(json.loads(content)),
                                     ensure_ascii=False, indent=2) + "\n"
            except (ValueError, TypeError) as exc:
                raise ValueError(f"tests/acceptance.json: {exc}") from exc
        binding = self._directory_context.get()
        if binding is not None:
            binding.file(target.relative_to(binding.directory).as_posix())
        if not binding:
            target.parent.mkdir(parents=True, exist_ok=True)
        if payload.get('_create_only') and target.exists():
            raise ValueError(f'{file_path}: create cannot overwrite an existing file')
        if binding:
            from ..project_transaction import write_text
            write_text(binding, target.relative_to(binding.directory).as_posix(), content)
        else:
            target.write_text(content, encoding="utf-8")
        await self.send_event("workspace.file_written", {
            "path": self._workspace_relative(target),
            "project_name": project_name.as_posix(),
        })
        return {"success": True, "path": self._workspace_relative(target),
                "file_path": file_path.as_posix(),
                "project_name": project_name.as_posix(), "bytes": len(content.encode())}

    @classmethod
    def validate_project(cls, project_dir: Path, all_files: list, web_stack: str = "static") -> Dict[str, Any]:
        planned = [cls._safe_relative(str(item.get("path") or "")) for item in all_files]
        missing = [p.as_posix() for p in planned if not (project_dir / p).is_file()]
        errors: list[str] = []
        if missing:
            errors.append("missing planned files: " + ", ".join(missing))
        required_files = (("index.html", "src/main.tsx", "src/App.tsx", "src/styles.css", "tests/acceptance.json")
                          if web_stack == "react_vite" else ("index.html", "styles.css", "app.js", "tests/acceptance.json"))
        for required in required_files:
            if not (project_dir / required).is_file():
                errors.append(f"missing required web artifact: {required}")

        index_path = project_dir / "index.html"
        if index_path.is_file():
            html = index_path.read_text(encoding="utf-8", errors="replace")
            if web_stack == "static" and not re.search(r"<main\b", html, re.I):
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
                acceptance = normalize_acceptance(json.loads(
                    acceptance_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"tests/acceptance.json: {exc}")

        for path in project_dir.rglob("*"):
            if any(part in {"node_modules", "dist"} or part.startswith(".") for part in path.relative_to(project_dir).parts):
                continue
            if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".ts", ".tsx"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"\b(?:TODO|FIXME)\b", text):
                    errors.append(f"placeholder marker remains in {path.relative_to(project_dir)}")

        return {"passed": not errors, "errors": errors,
                "files": [p.as_posix() for p in planned], "acceptance": acceptance,
                "scope": "static_artifacts", "browser_tests_executed": False}

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
        target = self._directory_context.get()
        if target and target.mode == 'new' and not payload.get('_maintenance_mode'):
            return await self.repair_project(payload, mode='new')
        from ..verification.web_gate import browser_report, record_attempt as record_web_attempt, failure_summary
        def record_attempt(*args, **kwargs):
            return record_web_attempt(*args, **kwargs, contract_revision=payload.get('contract_revision'))
        started = time.time()
        project_name = self._safe_project_name(str(payload.get("project_name") or "web-app"))
        project_dir = self._project_dir(project_name)
        web_stack = payload.get("web_stack", "static")
        validation = self.validate_project(project_dir, payload.get("all_files") or [], web_stack)
        previous_manifest = project_dir / ".project.json"
        if previous_manifest.is_file():
            previous = json.loads(previous_manifest.read_text())
            previous["verified"] = False
            binding = self._directory_context.get()
            if binding:
                from ..project_transaction import write_text
                write_text(binding, '.project.json', json.dumps(previous, indent=2))
            else:
                previous_manifest.write_text(json.dumps(previous, indent=2))
        project_path = self._workspace_relative(project_dir)
        if not validation["passed"]:
            evidence = record_attempt(project_dir, payload.get("user_request") or project_name.name,
                validation, {"status": "skipped"}, brain=self.name, attempt=1)
            await self._publish_browser_evidence(evidence)
            return {"success": False, "runnable": False, "project_name": project_name.as_posix(),
                    "project_path": project_path, "entry_point": "index.html",
                    "deliverable_type": "web_app",
                    "error": "; ".join(validation["errors"]),
                    "verification": {"run_id": evidence.run_id, "verdict": evidence.verdict,
                        "failures": [{"stage": s.name, "status": s.status, "details": s.details}
                                     for s in evidence.stages if s.status not in {'passed', 'not_applicable'}]}}

        build_stages = []
        parent_run_id = payload.get('_verification_parent_run_id')
        repair_count = payload.get('_verification_attempt', 1) - 1
        if web_stack == "react_vite":
            from .web_stack import build_react
            while True:
                await self.send_progress({"stage": "web_build", "project_name": project_name.name,
                                          "attempt": repair_count + 1})
                build_stages = await build_react(project_dir)
                if all(stage["status"] == "passed" for stage in build_stages):
                    break
                report = {"status": "skipped", "build_stages": build_stages}
                evidence = record_attempt(project_dir, payload.get("user_request") or project_name.name,
                    validation, report, brain=self.name, attempt=repair_count + 1, parent_run_id=parent_run_id)
                await self._publish_browser_evidence(evidence)
                parent_run_id = evidence.run_id
                return {"success": False, "runnable": False, "error": build_stages[-1]["output"],
                        "verification": {"run_id": evidence.run_id, "verdict": evidence.verdict,
                            "failures": [{"stage": s.name, "status": s.status, "details": s.details}
                                         for s in evidence.stages if s.status not in {'passed', 'not_applicable'}]}}
        preview_dir = project_dir / "dist" if web_stack == "react_vite" else project_dir
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
        for old_port, old_process in list(self._active_previews.items()):
            if old_process is self._preview_process:
                self._active_previews.pop(old_port, None)

        self._preview_process = await asyncio.create_subprocess_exec(
            "python3", "-m", "http.server", str(port), "--bind", "127.0.0.1",
            cwd=str(preview_dir), stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._active_previews[port] = self._preview_process
        await asyncio.sleep(0.15)
        if self._preview_process.returncode is not None:
            error = (await self._preview_process.stderr.read()).decode(errors="replace")
            self._active_previews.pop(port, None)
            return {"success": False, "runnable": False, "error": error[:1000],
                    "verification": {**validation, 'verdict': 'inconclusive', 'failures': [
                        {'stage': 'preview_environment', 'status': 'inconclusive', 'details': {
                            'cause': 'environment_blocked', 'next_action': 'stop',
                            'reason': 'Preview server could not start', 'diagnostic': error[:1000]}}]}}

        url = f"http://127.0.0.1:{port}"
        acceptance = validation["acceptance"]
        try:
            for attempt in [repair_count + 1]:
                await self.send_progress({"stage": "browser_testing", "attempt": attempt,
                                          "project_name": project_name.name})
                report = await browser_report(url, acceptance)
                report["build_stages"] = build_stages
                if report.get('status') == 'passed' and payload.get('contract_revision') and not payload.get('_diagnostic_only'):
                    from ..verification.semantics import review_semantics
                    sources = {item['path']: (project_dir / item['path']).read_text()
                               for item in payload.get('all_files', [])}
                    semantic = await review_semantics(self.llm_provider,
                        request=payload.get('user_request', ''), contracts=payload.get('business_contracts'),
                        sources=sources, tests={'status': report['status'],
                            'passed_cases': [case['name'] for case in report.get('cases', []) if case['status'] == 'passed']},
                        progressive=bool(payload.get('_maintenance_mode')),
                        runtime_evidence=payload.get('_maintenance_runtime_evidence'))
                    report['semantic_review'] = semantic.model_dump(mode='json')
                evidence = record_attempt(project_dir, payload.get("user_request") or project_name.name,
                    validation, report, brain=self.name, attempt=repair_count + 1, parent_run_id=parent_run_id)
                await self._publish_browser_evidence(evidence)
                parent_run_id = evidence.run_id
                if evidence.verdict == "passed":
                    break
                if evidence.verdict != 'passed':
                    await self.cleanup()
                    return {"success": False, "runnable": False, "project_name": project_name.name,
                            "project_path": project_path, "entry_point": "index.html",
                            "deliverable_type": "web_app", "error": failure_summary(report),
                            **({'browser_report': report} if payload.get('_maintenance_mode') else {}),
                            "verification": {"verdict": evidence.verdict, "run_id": evidence.run_id,
                                "failures": [{"stage": s.name, "status": s.status, "details": s.details}
                                             for s in evidence.stages if s.status not in {'passed', 'not_applicable'}]}}
        except BaseException:
            await self.cleanup()
            raise

        if payload.get('_diagnostic_only'):
            await self.cleanup()
            return {'success': evidence.verdict == 'passed', 'verification': {'verdict': evidence.verdict,
                    'run_id': evidence.run_id}, 'browser_report': report}

        manifest = {
            "name": project_name.name, "created": time.time(),
            "deliverable_type": "web_app", "interaction_mode": "browser",
            "entry_point": "index.html", "run": {"kind": "static_preview"},
            "verified": True,
            "verification_scope": "static_and_browser",
            "browser_tests_executed": True,
            "verification_run_id": evidence.run_id,
            "web_stack": web_stack,
            "preview_dir": "dist" if web_stack == "react_vite" else ".",
        }
        binding = self._directory_context.get()
        if binding:
            from ..project_transaction import write_text
            write_text(binding, '.project.json', json.dumps(manifest, indent=2))
        else:
            (project_dir / '.project.json').write_text(json.dumps(manifest, indent=2))
        from ..project_transaction import active_transaction, ProjectTransaction
        if active_transaction.get():
            ProjectTransaction(active_transaction.get()).seal_build_tree(project_dir)
        await self.cleanup()
        await self.send_progress({"stage": "preview_ready"})
        return {
            "success": True, "runnable": True, "project_name": project_name.name,
            "project_path": project_path, "entry_point": "index.html",
            "deliverable_type": "web_app",
            "files_written": validation["files"], "server_running": False,
            "verification": {"verdict": evidence.verdict, "run_id": evidence.run_id,
                             "browser_tests_executed": True},
            "execution_time": time.time() - started,
        }

    async def _publish_browser_evidence(self, manifest) -> None:
        await self.send_event("verification.run_recorded", {
            "run_id": manifest.run_id, "verdict": manifest.verdict,
            "attempt": manifest.metadata["attempt"],
            "stages": [{"name": stage.name, "status": stage.status} for stage in manifest.stages],
        })

    async def _repair_browser_failure(self, project_dir: Path, report: dict, payload: dict) -> None:
        if payload.get('_editable_paths') is not None:
            raise ValueError('Browser verification failed; existing projects require a new targeted repair plan, not automatic whole-file replacements')
        """Allow two bounded code repairs; acceptance scenarios remain frozen."""
        from ..verification.web_gate import failure_summary
        files = {path.relative_to(project_dir).as_posix(): path.read_text(encoding="utf-8")
                 for path in project_dir.rglob("*")
                 if path.is_file() and path.suffix.lower() in {".html", ".css", ".js", ".ts", ".tsx"}
                 and not path.is_symlink() and project_dir.resolve() in path.resolve().parents
                 and path.name != "vite.config.ts"
                 and not any(part.startswith(".") or part in {"tests", "node_modules", "dist"}
                             for part in path.relative_to(project_dir).parts)}
        prompt = ("Repair this static web application to pass the frozen browser scenarios. "
                  "Return ONLY JSON {\"files\":[{\"path\":\"existing file\",\"content\":\"full replacement\"}]}. "
                  "Modify only existing HTML/CSS/JS. Never alter tests, hide errors, or fake results.\n"
                  f"User request: {payload.get('user_request', '')}\n"
                  f"Browser errors:\n{failure_summary(report)}\n"
                  f"Actual DOM text:\n{str([c.get('page_text', '') for c in report.get('cases', [])])[:8000]}\n"
                  f"Frozen tests:\n{(project_dir / 'tests/acceptance.json').read_text()[:16000]}\n"
                  f"Files:\n{json.dumps(files, ensure_ascii=False)[:50000]}")
        raw = await self.llm_provider.chat_complete(
            messages=[{"role": "user", "content": prompt}],
            model=os.getenv("BIGBRAIN_WEB_MODEL", self.model or "default"),
            stream=False, max_tokens=12000, temperature=0.2)
        replacements = json.loads(self._extract_code(raw)).get("files")
        if not isinstance(replacements, list) or not replacements or len(replacements) > 12:
            raise ValueError("Browser repair must return 1 to 12 code files")
        for replacement in replacements:
            if (not isinstance(replacement, dict) or replacement.get("path") not in files
                    or not isinstance(replacement.get("content"), str) or not replacement["content"].strip()):
                raise ValueError("Browser repair attempted an unauthorized or empty file replacement")
            target = project_dir / replacement["path"]
            resolved = target.resolve()
            if (target.is_symlink() or project_dir.resolve() not in resolved.parents
                    or "tests" in resolved.relative_to(project_dir.resolve()).parts):
                raise ValueError("Browser repair target escapes the editable source files")
        for replacement in replacements:
            target = project_dir / replacement["path"]
            target.write_text(replacement["content"], encoding="utf-8")
            await self.send_event("workspace.file_written", {"path": self._workspace_relative(target)})

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
