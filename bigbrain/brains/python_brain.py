"""PythonBrain - Python code execution brain with subprocess isolation."""

import asyncio
import json
import logging
import os
import re
import signal
import socket
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseBrain
from ..bus.message import BusMessage, Priority

logger = logging.getLogger(__name__)


class PythonBrain(BaseBrain):
    """
    Python code execution brain with subprocess isolation.
    
    Executes Python code in isolated subprocess environments with:
    - Timeout protection
    - Cross-platform compatibility (uses sys.executable)
    - Temporary file management
    - stdout/stderr capture
    - Exit code handling
    
    Implements the Honk pattern inner loop:
    - Receive code to execute
    - Run in subprocess sandbox
    - Capture output and errors
    - Return structured results
    
    Security Note: This is a preview implementation without full sandboxing.
    Production use requires proper isolation (bubblewrap, Docker, etc.).
    """
    
    def __init__(self, name: str = "python_brain", bus=None, workspace: str = None,
                 timeout: int = 60, work_dir: Path = None, llm_provider=None):
        """
        Initialize Python execution brain.
        
        Args:
            name: Brain identifier
            bus: MessageBus instance
            workspace: Workspace this brain belongs to
            timeout: Default execution timeout in seconds
            work_dir: Working directory for code execution
            llm_provider: LLM provider for code generation (optional)
        """
        super().__init__(name, bus, workspace)
        self.timeout = timeout
        self.llm_provider = llm_provider
        if work_dir:
            # Explicit work_dir: use as-is (shared pool directory)
            self.work_dir = Path(work_dir)
        else:
            # Default: per-brain isolated directory
            self.work_dir = Path(tempfile.gettempdir()) / f"bigbrain_python_{name}"
        self.work_dir.mkdir(exist_ok=True, parents=True)
        
        # Track created temp files for cleanup
        self._temp_files: set[Path] = set()

        # Deterministic evidence gate (harness P2) — set False to disable
        # recording without touching the execution flow.
        self._evidence_enabled = os.environ.get("BIGBRAIN_EVIDENCE", "1") != "0"
        
        # Preview server tracking (class-level shared across instances)
        self._preview_process: Optional[asyncio.subprocess.Process] = None

    async def _write_and_notify(self, full_path: Path, content: str) -> None:
        """Write a file inside the shared workspace and notify the UI.

        All agent file writes land under the workspace root served by the
        FS API, so they are visible in the web file explorer; the
        workspace.file_written event lets the explorer auto-refresh.
        """
        full_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(full_path.write_text, content, encoding="utf-8")
        await self._notify_workspace_write(full_path)

    async def _notify_workspace_write(self, full_path: Path) -> None:
        from ..web.fs_api import workspace_root

        try:
            rel = full_path.relative_to(workspace_root())
        except ValueError:
            return  # outside the shared workspace: not UI-visible
        try:
            from ..bus.message import BusMessage, MessageType

            await self.bus.send(BusMessage(
                type=MessageType.EVENT,
                source=self.name,
                target="morphable_ui",
                payload={
                    "event": "workspace.file_written",
                    "path": rel.as_posix(),
                    "brain": self.name,
                },
            ))
        except Exception:
            pass  # notification must never break the write path
    
    async def _notify_verification(self, manifest, verdict: str,
                                   attempt: int | None = None) -> None:
        """Broadcast the gate verdict to the UI (verification.run_recorded).

        Harness P4: the run panel shows per-stage pills and the verdict;
        the event must never break the run — broadcast is best effort.
        """
        try:
            from ..bus.message import BusMessage, MessageType

            await self.bus.send(BusMessage(
                type=MessageType.EVENT,
                source=self.name,
                target="morphable_ui",
                payload={
                    "event": "verification.run_recorded",
                    "run_id": manifest.run_id,
                    "verdict": verdict,
                    "attempt": attempt,
                    "stages": [
                        {"name": s.name, "status": s.status}
                        for s in manifest.stages
                    ],
                },
            ))
        except Exception:
            pass  # the UI surface must never break the run

    # Port range for preview servers (shared across all PythonBrain instances)
    PREVIEW_PORT_MIN = 3100
    PREVIEW_PORT_MAX = 3199
    # Active previews: {port: process} — class-level so all workers share
    _active_previews: Dict[int, asyncio.subprocess.Process] = {}

    # Environment variables stripped from child processes (security)
    _SENSITIVE_ENV_PREFIXES = (
        "OPENCLAW_", "PROTECLAW_", "BIGBRAIN_", "LITELLM_",
        "RESEND_", "CLOUDFLARE_",
    )
    _SENSITIVE_ENV_KEYS = {
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN",
        "SSH_AUTH_SOCK", "SSH_AGENT_PID", "NPM_TOKEN",
    }

    async def _setup_project_venv(self, project_dir: Path) -> Path:
        """Create a per-project venv and return the venv python path.

        Each project gets its own isolated virtual environment so that
        ``pip install`` never touches the system Python or other projects.
        Re-uses existing venvs on retry/restart.
        """
        venv_dir = project_dir / ".venv"
        venv_python = venv_dir / "bin" / "python"

        if venv_python.exists():
            return venv_python  # already created

        await self.send_progress({
            "stage": "creating_venv",
            "project_dir": project_dir.name,
        })

        # Use stdlib venv — runs in-process, fast, no subprocess needed
        builder = venv.EnvBuilder(with_pip=True, upgrade_deps=False)
        # venv creation is synchronous; run in executor to avoid blocking
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, builder.create, str(venv_dir))

        if not venv_python.exists():
            raise RuntimeError(f"venv creation succeeded but {venv_python} not found")

        return venv_python

    async def _install_in_venv(
        self, venv_python: Path, project_dir: Path, packages: List[str],
        *, from_requirements: bool = False, timeout: int = 120,
    ) -> bool:
        """Install packages into the project venv.

        Args:
            venv_python: Path to the venv's python binary
            project_dir: Project root (for cwd)
            packages: List of package specs OR empty when from_requirements=True
            from_requirements: If True, install from requirements.txt
            timeout: pip timeout in seconds

        Returns:
            True if install succeeded, False on error (best-effort).
        """
        cmd = [str(venv_python), "-m", "pip", "install", "-q"]
        if from_requirements:
            req_file = project_dir / "requirements.txt"
            if not req_file.exists():
                return False
            cmd += ["-r", str(req_file)]
        else:
            if not packages:
                return True
            cmd += packages

        await self.send_progress({
            "stage": "installing_deps",
            "packages": packages if not from_requirements else ["(from requirements.txt)"],
            "venv": True,
        })

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
                env=self._get_execution_env(),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode == 0
        except (asyncio.TimeoutError, Exception) as e:
            await self.send_progress({
                "stage": "install_warning",
                "error": str(e),
            })
            return False
    
    @classmethod
    def _find_free_preview_port(cls) -> Optional[int]:
        """Find an available port in the preview range."""
        for port in range(cls.PREVIEW_PORT_MIN, cls.PREVIEW_PORT_MAX + 1):
            if port in cls._active_previews:
                continue
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        return None
    
    @classmethod
    def _is_web_project(cls, written_files: Dict[str, str]) -> bool:
        """Detect if the project is a web server (FastAPI, Flask, etc.)."""
        web_patterns = [
            r"from\s+fastapi\s+import",
            r"from\s+flask\s+import",
            r"from\s+starlette",
            r"from\s+sanic\s+import",
            r"import\s+uvicorn",
            r"import\s+gunicorn",
            r"\.run\s*\(.*host\s*=",
            r"\.run\s*\(.*port\s*=",
            r"app\.listen\(",
            r"socketio",
            r"websocket",
        ]
        all_code = "\n".join(written_files.values())
        return any(re.search(p, all_code, re.IGNORECASE) for p in web_patterns)
    
    async def handle_task(self, message: BusMessage) -> Dict[str, Any]:
        """
        Execute Python code from task message.
        
        Expected task payload:
        {
            "type": "execute_code",
            "code": "print('Hello, world!')",
            "timeout": 10,  # optional override
            "files": {      # optional additional files to create
                "data.txt": "some data content"
            }
        }
        
        Returns:
        {
            "stdout": "captured stdout",
            "stderr": "captured stderr", 
            "exit_code": 0,
            "execution_time": 1.23,
            "files_created": ["output.txt"],
            "success": true
        }
        """
        payload = message.payload
        task_type = payload.get("type")
        
        if task_type == "generate_and_execute":
            # LLM generates code from natural language, then we execute it
            return await self._generate_and_execute(payload)
        elif task_type == "write_project_file":
            # Write a single file as part of a multi-file project
            return await self._write_project_file(payload)
        elif task_type == "assemble_and_run":
            # Assemble all project files and run the entry point
            return await self._assemble_and_run(payload)
        elif task_type == "batch_write_files":
            # Write multiple files concurrently
            return await self._batch_write_files(payload)
        elif task_type == "edit_file":
            # Edit existing file using diff-based approach
            return await self._edit_file(payload)
        elif task_type == "search_project":
            # Search across project files using regex or glob patterns
            return await self._search_project(payload)
        elif task_type == "run_file":
            # Execute an EXISTING file from the work_dir (no generation)
            return await self._run_existing_file(payload)
        elif task_type == "execute_code":
            code = payload.get("code")
            if not code:
                raise ValueError("No code provided in task")
            timeout = payload.get("timeout", self.timeout)
            await self._create_task_files(payload.get("files", {}))
            return await self._execute_code(code, timeout)
        else:
            raise ValueError(f"Unknown task type: {task_type}")
    
    # --- Project Mode: Write individual files ---

    async def _write_project_file(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Write a single file as part of a multi-file project.
        
        The Orchestrator has already planned the file structure. This method
        generates code for ONE specific file based on its purpose, exports,
        and dependencies (content of upstream files).
        """
        if not self.llm_provider:
            return {"success": False, "error": "No LLM provider", "stdout": "", "stderr": "", "exit_code": -1}
        
        project_name = payload.get("project_name", "project")
        file_path = payload.get("file_path", "main.py")
        purpose = payload.get("purpose", "")
        exports = payload.get("exports", [])
        dependencies = payload.get("dependencies", [])
        all_files = payload.get("all_files", [])
        user_request = payload.get("user_request", "")
        
        # Get upstream context (completed dependency files)
        upstream_context = payload.get("upstream_context", {})
        
        # Build dependency content section from ACTUAL completed code
        # (not just architect spec — the real code that was generated)
        dep_content = ""
        if upstream_context:
            dep_parts = []
            for source, result in upstream_context.items():
                if isinstance(result, dict):
                    code = result.get("file_content", result.get("generated_code", ""))
                    fpath = result.get("file_path", source)
                    if code:
                        # Show full code up to 8000 chars — enough for most files.
                        # Truncation was 2000 before, causing workers to miss
                        # critical parts of dependency implementations.
                        truncated = code[:8000]
                        if len(code) > 8000:
                            truncated += f"\n... (truncated, {len(code)} total chars)"
                        dep_parts.append(f"=== {fpath} ===\n{truncated}")
            if dep_parts:
                dep_content = "\n\nActual code of completed dependency files (import from these):\n" + "\n\n".join(dep_parts)
        
        # Build file tree overview
        file_tree = "\n".join(f"  - {f['path']}: {f.get('purpose', '')}" for f in all_files)
        
        # Use architect spec if available (rich context with interfaces + data models)
        architect_spec = payload.get("architect_spec", "")
        implementation_notes = payload.get("implementation_notes", "")
        edge_cases = payload.get("edge_cases", [])

        # Both architect and legacy prompts use these sections.
        task_state_section = ""
        if "_task_state" in payload:
            task_state_section = f"\n\n## Current Project Progress\n{payload['_task_state']}\n"
        user_interjection_section = ""
        if "_user_interjection" in payload:
            user_message = payload["_user_interjection"]
            user_interjection_section = f'\n\n## User Message (Mid-Task)\nThe user just said: "{user_message}"\nTake this into account when writing this file.\n'

        if architect_spec:
            # Architect-powered prompt: rich context with exact interfaces
            edge_cases_text = ""
            if edge_cases:
                edge_cases_text = "\n\nEdge cases to handle:\n" + "\n".join(f"- {ec}" for ec in edge_cases)

            # When actual dependency code is available, it takes priority
            # over the architect spec's interface descriptions
            actual_code_note = ""
            if dep_content:
                actual_code_note = """

IMPORTANT: The "Actual code" section below shows the REAL implementation
of your dependencies (written by other workers). Use these exact class names,
function signatures, and import paths. If the actual code differs from the
architect spec above, follow the ACTUAL CODE — it's what will be on disk."""

            prompt = f"""Write the file `{file_path}` for the project "{project_name}".

Overall project goal: {user_request}
{user_interjection_section}{task_state_section}
## Architect Specification for this file:
{architect_spec}
{actual_code_note}
{dep_content}
{edge_cases_text}

Rules:
- Output ONLY the file content, no explanation before or after
- Write ONLY this file — do not include other files
- Implement ALL exports listed in the spec with EXACT signatures
- Import from dependencies using the EXACT names from their actual code
- If this is an HTML file, output the full HTML (not Python)
- Include proper error handling for all edge cases listed
- Add docstrings to all public functions and classes
- Make the code production-quality, not a sketch"""
        else:
            # Legacy prompt (no architect spec available)
            prompt = f"""Write the file `{file_path}` for the project "{project_name}".

Overall project goal: {user_request}
{user_interjection_section}{task_state_section}
Project file structure:
{file_tree}

THIS FILE's purpose: {purpose}
THIS FILE must export: {', '.join(exports) if exports else 'N/A (entry point or template)'}
THIS FILE depends on: {', '.join(dependencies) if dependencies else 'nothing'}
{dep_content}

Rules:
- Output ONLY the file content, no explanation before or after
- Write ONLY this file — do not include other files
- If this file depends on other files, import from them correctly
- Use Python standard library only (no numpy, pandas, etc.)
- Make the code clean, well-structured, with docstrings
- If this is an HTML file, output the full HTML (not Python)
- Include proper error handling"""

        # --- Generate → Verify → Fix loop (up to MAX_FILE_RETRIES) ---
        # For Python files: syntax check after each generation.
        # If syntax error: feed error back to LLM for fix.
        # For non-Python files (HTML, CSS, etc.): no syntax check needed.
        MAX_FILE_RETRIES = 4  # 1 initial + up to 3 fix/continuation attempts
        is_python_file = file_path.endswith(".py")
        
        project_dir = self.work_dir / project_name
        project_dir.mkdir(exist_ok=True, parents=True)
        full_path = project_dir / file_path
        full_path.parent.mkdir(exist_ok=True, parents=True)

        attempt_history = []
        code = ""

        for attempt in range(1, MAX_FILE_RETRIES + 1):
            await self.send_progress({
                "stage": "writing_file",
                "file_path": file_path,
                "purpose": purpose,
                "attempt": attempt,
                "max_attempts": MAX_FILE_RETRIES,
            })

            if attempt == 1:
                # First attempt: use the original prompt
                generated = await self.llm_provider.complete(
                    prompt, stream=False, max_tokens=8192
                )
            else:
                last_error = attempt_history[-1]["error"] if attempt_history else ""
                is_truncation = self._is_truncation_error(last_error, code)
                
                if is_truncation and code.strip():
                    # Truncation: don't rewrite — continue from where it stopped
                    cont_prompt = self._build_continuation_prompt(
                        file_path, project_name, code
                    )
                    continuation = await self.llm_provider.complete(
                        cont_prompt, stream=False, max_tokens=4096
                    )
                    new_code = self._extract_code(continuation)
                    if new_code.strip():
                        code = code.rstrip() + "\n" + new_code
                        generated = code  # skip extract_code below
                    else:
                        generated = code  # keep trying with fix prompt
                else:
                    # Real syntax error: fix prompt
                    fix_prompt = self._build_file_fix_prompt(
                        file_path, project_name, user_request,
                        code, attempt_history, prompt,
                    )
                    generated = await self.llm_provider.complete(
                        fix_prompt, stream=False, max_tokens=8192
                    )

            code = self._extract_code(generated)

            if not code.strip():
                attempt_history.append({
                    "attempt": attempt,
                    "error": "LLM returned empty content",
                })
                if attempt == MAX_FILE_RETRIES:
                    return {
                        "success": False,
                        "error": f"LLM returned empty content for {file_path} after {attempt} attempts",
                        "stdout": "", "stderr": "", "exit_code": -1,
                        "file_path": file_path,
                        "attempt_history": attempt_history,
                    }
                continue

            # Syntax check for Python files
            if is_python_file:
                syntax_error = self._check_syntax(code, file_path)
                if syntax_error:
                    attempt_history.append({
                        "attempt": attempt,
                        "error": syntax_error,
                        "code_snippet": code[:500],
                    })
                    await self.send_progress({
                        "stage": "syntax_error",
                        "file_path": file_path,
                        "attempt": attempt,
                        "error": syntax_error[:200],
                    })
                    if attempt < MAX_FILE_RETRIES:
                        continue  # Retry with fix prompt
                    # Final attempt still has syntax error — write anyway
                    # (assembler may still be able to use it)

            # Code is good (or non-Python) — write it
            break

        await self._write_and_notify(full_path, code)
        # NOTE: project files are NOT tracked as temp files — they persist
        # across restarts so preview servers can be restarted and projects
        # can be inspected after completion.
        
        await self.send_progress({
            "stage": "file_written",
            "file_path": file_path,
            "lines": code.count("\n") + 1,
            "attempts": attempt,
            "had_errors": len(attempt_history) > 0,
        })
        
        return {
            "success": True,
            "file_path": file_path,
            "file_content": code,
            "lines": code.count("\n") + 1,
            "stdout": f"Written {file_path} ({code.count(chr(10)) + 1} lines)",
            "stderr": "",
            "exit_code": 0,
            "attempts": attempt,
            "attempt_history": attempt_history if attempt_history else None,
        }
    
    async def _batch_write_files(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write multiple files concurrently using asyncio.gather.
        
        This is for when the orchestrator knows multiple files can be written
        simultaneously without dependencies between them.
        
        Expected payload:
        {
            "type": "batch_write_files",
            "files": [
                {"path": "file1.py", "content": "print('file1')"},
                {"path": "file2.py", "content": "print('file2')"}
            ]
        }
        
        Returns:
        {
            "success": True,
            "results": [
                {"path": "file1.py", "success": True, "bytes_written": 18},
                {"path": "file2.py", "success": False, "error": "Permission denied"}
            ]
        }
        """
        files_to_write = payload.get("files", [])
        if not files_to_write:
            return {
                "success": False, 
                "error": "No files provided",
                "results": []
            }
        
        # Progress update
        await self.send_progress({
            "stage": "batch_write_start",
            "total_files": len(files_to_write)
        })
        
        async def write_single_file(file_spec: Dict[str, str]) -> Dict[str, Any]:
            """Write a single file and return result."""
            file_path = file_spec.get("path", "")
            content = file_spec.get("content", "")
            
            if not file_path:
                return {
                    "path": file_path,
                    "success": False,
                    "error": "No file path provided"
                }
            
            try:
                # Reject absolute paths and traversal before writing.
                root = self.work_dir.resolve()
                full_path = (root / file_path).resolve()
                try:
                    full_path.relative_to(root)
                except ValueError:
                    return {
                        "path": file_path,
                        "success": False,
                        "error": "File path escapes the working directory",
                    }
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Use asyncio.to_thread for the actual I/O to avoid blocking
                await self._write_and_notify(full_path, content)
                
                return {
                    "path": file_path,
                    "success": True,
                    "bytes_written": len(content.encode("utf-8")),
                    "lines": content.count("\n") + 1 if content else 0
                }
            except Exception as e:
                return {
                    "path": file_path,
                    "success": False,
                    "error": str(e)
                }
        
        # Write all files concurrently
        try:
            results = await asyncio.gather(
                *[write_single_file(file_spec) for file_spec in files_to_write],
                return_exceptions=True
            )
            
            # Handle any exceptions that weren't caught by write_single_file
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        "path": files_to_write[i].get("path", f"file_{i}"),
                        "success": False,
                        "error": str(result)
                    })
                else:
                    processed_results.append(result)
            
            # Calculate overall success
            successful_writes = [r for r in processed_results if r.get("success")]
            total_bytes = sum(r.get("bytes_written", 0) for r in successful_writes)
            
            await self.send_progress({
                "stage": "batch_write_complete",
                "successful": len(successful_writes),
                "failed": len(processed_results) - len(successful_writes),
                "total_bytes": total_bytes
            })
            
            return {
                "success": len(successful_writes) == len(processed_results),
                "results": processed_results,
                "summary": {
                    "total_files": len(files_to_write),
                    "successful": len(successful_writes),
                    "failed": len(processed_results) - len(successful_writes),
                    "total_bytes": total_bytes
                },
                "stdout": f"Batch write: {len(successful_writes)}/{len(files_to_write)} files written",
                "stderr": "",
                "exit_code": 0 if len(successful_writes) == len(processed_results) else 1
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Batch write failed: {str(e)}",
                "results": [],
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1
            }
    
    async def _edit_file(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Edit an existing file using LLM-generated SEARCH/REPLACE diffs.
        
        Falls back to full rewrite if diff application fails.
        
        Expected payload:
        {
            "type": "edit_file",
            "file_path": "path/to/file.py",
            "instructions": "Add error handling to the parse_config function",
            "project_name": "my_project"  # optional
        }
        
        Returns:
        {
            "success": True,
            "file_path": "path/to/file.py",
            "file_content": "updated content...",
            "method": "diff" | "rewrite",
            "diff_summary": "Applied 3 changes: added try-catch, updated docstring, fixed typo"
        }
        """
        if not self.llm_provider:
            return {
                "success": False, 
                "error": "No LLM provider available for editing",
                "stdout": "", "stderr": "", "exit_code": -1
            }
        
        file_path = payload.get("file_path", "")
        instructions = payload.get("instructions", "")
        project_name = payload.get("project_name", "")
        
        if not file_path or not instructions:
            return {
                "success": False,
                "error": "file_path and instructions are required",
                "stdout": "", "stderr": "", "exit_code": -1
            }
        
        # Determine full path
        if project_name:
            project_dir = self.work_dir / project_name
            full_path = project_dir / file_path
        else:
            full_path = self.work_dir / file_path
        
        if not full_path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "stdout": "", "stderr": "", "exit_code": -1
            }
        
        # Read existing file content
        try:
            original_content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "success": False,
                "error": f"Could not read file: {str(e)}",
                "stdout": "", "stderr": "", "exit_code": -1
            }
        
        await self.send_progress({
            "stage": "editing_file",
            "file_path": file_path,
            "instructions": instructions[:100],
            "original_lines": original_content.count("\n") + 1
        })
        
        # First attempt: Generate SEARCH/REPLACE diffs
        diff_result = await self._try_diff_edit(full_path, original_content, instructions, payload)
        
        if diff_result["success"]:
            return diff_result
        
        await self.send_progress({
            "stage": "diff_failed_fallback",
            "file_path": file_path,
            "diff_error": diff_result.get("error", "unknown"),
        })
        
        # Fallback: Full rewrite
        rewrite_result = await self._try_full_rewrite(full_path, original_content, instructions, payload)
        return rewrite_result
    
    async def _try_diff_edit(self, full_path: Path, original_content: str, 
                            instructions: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to edit file using LLM-generated SEARCH/REPLACE diffs."""
        
        # Check for task state injection
        task_state_section = ""
        if "_task_state" in payload:
            task_state = payload["_task_state"]
            task_state_section = f"\n\n## Current Project Progress\n{task_state}\n"
        
        # Check for user interjection
        user_interjection_section = ""
        if "_user_interjection" in payload:
            user_message = payload["_user_interjection"]
            user_interjection_section = f"\n\n## User Message (Mid-Task)\nThe user just said: \"{user_message}\"\nConsider this when editing the file.\n"
        
        # Number the lines for precise references
        numbered_content = "\n".join(
            f"{i+1:4d} | {line}" for i, line in enumerate(original_content.split("\n"))
        )
        
        prompt = f"""Edit the file using SEARCH/REPLACE blocks.

Instructions: {instructions}
{user_interjection_section}{task_state_section}
Current file content (numbered):
{numbered_content}

Generate SEARCH/REPLACE blocks to make the requested changes:
- Use EXACT text from the file (including whitespace)
- Make minimal changes to achieve the goal
- Provide multiple blocks if needed
- Include line numbers for context

Format:
SEARCH
exact text to find
REPLACE
new text to replace it with

Be precise with indentation and whitespace."""

        try:
            response = await self.llm_provider.complete(
                prompt, stream=False, max_tokens=4096, temperature=0.2
            )
            
            # Apply the search/replace operations
            updated_content, changes = self._apply_search_replace(original_content, response)
            
            if not changes:
                return {
                    "success": False,
                    "error": "No valid SEARCH/REPLACE blocks found in LLM response",
                    "method": "diff"
                }
            
            # Write the updated content
            await self._write_and_notify(full_path, updated_content)
            
            diff_summary = f"Applied {len(changes)} change(s): {', '.join(changes[:3])}"
            if len(changes) > 3:
                diff_summary += f" (and {len(changes) - 3} more)"
            
            return {
                "success": True,
                "file_path": str(full_path.name),
                "file_content": updated_content,
                "method": "diff",
                "diff_summary": diff_summary,
                "changes_applied": len(changes),
                "stdout": f"Applied {len(changes)} diff changes to {full_path.name}",
                "stderr": "",
                "exit_code": 0
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Diff edit failed: {str(e)}",
                "method": "diff"
            }
    
    async def _try_full_rewrite(self, full_path: Path, original_content: str,
                               instructions: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback: Generate completely new file content."""
        
        # Check for task state injection
        task_state_section = ""
        if "_task_state" in payload:
            task_state = payload["_task_state"]
            task_state_section = f"\n\n## Current Project Progress\n{task_state}\n"
        
        # Check for user interjection
        user_interjection_section = ""
        if "_user_interjection" in payload:
            user_message = payload["_user_interjection"]
            user_interjection_section = f"\n\n## User Message (Mid-Task)\nThe user just said: \"{user_message}\"\nConsider this when rewriting the file.\n"
        
        prompt = f"""Rewrite the entire file to incorporate the requested changes.

Instructions: {instructions}
{user_interjection_section}{task_state_section}
Original file content:
{original_content}

Rules:
- Output the COMPLETE file content with the requested changes
- Preserve existing functionality while making the requested modifications
- Maintain the same code style and structure
- Output ONLY the file content, no explanations"""

        try:
            new_content = await self.llm_provider.complete(
                prompt, stream=False, max_tokens=8192, temperature=0.3
            )
            
            # Extract code if wrapped in markdown
            new_content = self._extract_code(new_content)
            
            if not new_content.strip():
                return {
                    "success": False,
                    "error": "LLM returned empty content for file rewrite",
                    "method": "rewrite",
                    "stdout": "", "stderr": "", "exit_code": -1
                }
            
            # Write the new content
            await self._write_and_notify(full_path, new_content)
            
            return {
                "success": True,
                "file_path": str(full_path.name),
                "file_content": new_content,
                "method": "rewrite",
                "diff_summary": "Complete file rewrite",
                "lines": new_content.count("\n") + 1,
                "stdout": f"Rewrote {full_path.name} ({new_content.count(chr(10)) + 1} lines)",
                "stderr": "",
                "exit_code": 0
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"File rewrite failed: {str(e)}",
                "method": "rewrite",
                "stdout": "", "stderr": str(e), "exit_code": -1
            }

    async def _run_existing_file(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an existing file from the work_dir — no LLM, no generation.

        "Run hello.py" from the chat must run what is on disk, not
        regenerate it. The work_dir tracks the selected project (or the
        sandbox in global mode), so the file runs in the same layout the
        agent wrote it in.
        """
        import time

        filename = str(payload.get("file") or payload.get("filename") or "").strip()
        if not filename:
            raise ValueError("No file provided in run_file task")
        if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("."):
            raise ValueError("run_file accepts a plain filename inside the project")

        target = self.work_dir / filename
        timeout = payload.get("timeout", self.timeout)
        start = time.time()

        if not target.is_file():
            return {
                "success": False,
                "error": f"File not found: {filename}",
                "stdout": "",
                "stderr": f"File not found: {filename}",
                "exit_code": -1,
                "files_created": [],
                "execution_time": 0.0,
                "file": filename,
            }

        try:
            stdout_str, stderr_str, exit_code, timed_out = (
                await self._exec_streamed(
                    [sys.executable, "-u", str(target)],
                    cwd=self.work_dir,
                    env=self._get_execution_env(),
                    timeout=timeout))
            if timed_out:
                stderr_str += (f"Execution timed out after {timeout}"
                               " seconds")
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e),
                "exit_code": -2,
                "files_created": [],
                "execution_time": time.time() - start,
                "file": filename,
            }

        result = {
            "success": exit_code == 0 and not timed_out,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": exit_code,
            "files_created": [],
            "execution_time": time.time() - start,
            "file": filename,
        }

        # Evidence record (harness P2) — same gate, best effort.
        if self._evidence_enabled:
            try:
                import platform as _platform

                from ..verification.evidence import default_repository
                from ..verification.gate import RunGate

                manifest, verdict = await RunGate(default_repository()).evaluate_attempt(
                    user_request=f"run existing file {filename}",
                    code=target.read_text(encoding="utf-8", errors="replace"),
                    execution=result,
                    work_dir=self.work_dir,
                    requested_file=filename,
                    persisted_file=filename,
                    toolchain={"python": _platform.python_version(),
                               "brain": self.name},
                    filename=filename,
                )
                result["verification"] = {
                    "run_id": manifest.run_id,
                    "verdict": verdict,
                    "stages": [{"name": s.name, "status": s.status}
                               for s in manifest.stages],
                }
                await self._notify_verification(manifest, verdict)
            except Exception:
                pass  # recording must never break the run

        return result

    async def _search_project(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search across project files using regex or glob patterns.
        
        Expected payload:
        {
            "type": "search_project",
            "pattern": "def\\s+\\w+\\(",  # regex pattern
            "mode": "regex",  # "regex" or "glob"
            "project_dir": "path/to/project",  # optional, defaults to work_dir
            "file_extensions": [".py", ".txt"]  # optional, defaults to common extensions
        }
        
        Returns:
        {
            "success": True,
            "matches": [
                {
                    "file": "module.py",
                    "line": 15,
                    "match": "def my_function(param):",
                    "context": "    def my_function(param):\n        return param * 2"
                }
            ],
            "total_matches": 3,
            "files_searched": 12
        }
        """
        pattern = payload.get("pattern", "")
        mode = payload.get("mode", "regex")
        project_dir_path = payload.get("project_dir", "")
        file_extensions = payload.get("file_extensions", [".py", ".js", ".html", ".css", ".txt", ".md"])
        
        if not pattern:
            return {
                "success": False,
                "error": "No search pattern provided",
                "matches": [],
                "total_matches": 0,
                "files_searched": 0
            }
        
        # Determine search directory
        if project_dir_path:
            search_dir = Path(project_dir_path)
        else:
            search_dir = self.work_dir
        
        if not search_dir.exists():
            return {
                "success": False,
                "error": f"Search directory not found: {search_dir}",
                "matches": [],
                "total_matches": 0,
                "files_searched": 0
            }
        
        await self.send_progress({
            "stage": "searching",
            "pattern": pattern[:50],
            "mode": mode,
            "directory": str(search_dir)
        })
        
        if mode == "regex":
            return await self._search_regex(search_dir, pattern, file_extensions)
        elif mode == "glob":
            return await self._search_glob(search_dir, pattern, file_extensions)
        else:
            return {
                "success": False,
                "error": f"Unknown search mode: {mode}",
                "matches": [],
                "total_matches": 0,
                "files_searched": 0
            }
    
    async def _search_regex(self, search_dir: Path, pattern: str, file_extensions: List[str]) -> Dict[str, Any]:
        """Search files using regex pattern."""
        import re
        
        try:
            compiled_pattern = re.compile(pattern, re.MULTILINE)
        except re.error as e:
            return {
                "success": False,
                "error": f"Invalid regex pattern: {str(e)}",
                "matches": [],
                "total_matches": 0,
                "files_searched": 0
            }
        
        matches = []
        files_searched = 0
        
        # Search all files with matching extensions
        for file_path in search_dir.rglob("*"):
            if not file_path.is_file():
                continue
                
            # Skip hidden files and .checkpoints
            if any(part.startswith('.') for part in file_path.parts):
                continue
                
            # Check file extension
            if file_extensions and file_path.suffix not in file_extensions:
                continue
                
            files_searched += 1
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                
                # Find all matches in the file
                for match in compiled_pattern.finditer(content):
                    line_num = content[:match.start()].count('\n') + 1
                    
                    # Get context (line containing the match + surrounding lines)
                    lines = content.split('\n')
                    start_line = max(0, line_num - 2)
                    end_line = min(len(lines), line_num + 1)
                    context_lines = lines[start_line:end_line]
                    context = '\n'.join(context_lines)
                    
                    match_info = {
                        "file": str(file_path.relative_to(search_dir)),
                        "line": line_num,
                        "match": match.group(),
                        "context": context,
                        "start": match.start(),
                        "end": match.end()
                    }
                    matches.append(match_info)
                    
            except (UnicodeDecodeError, PermissionError):
                # Skip files that can't be read
                continue
        
        return {
            "success": True,
            "matches": matches,
            "total_matches": len(matches),
            "files_searched": files_searched,
            "pattern": pattern,
            "mode": "regex"
        }
    
    async def _search_glob(self, search_dir: Path, pattern: str, file_extensions: List[str]) -> Dict[str, Any]:
        """Search files using glob pattern."""
        from pathlib import Path
        
        matches = []
        files_searched = 0
        
        try:
            # Use glob pattern to find matching files
            for file_path in search_dir.rglob(pattern):
                if not file_path.is_file():
                    continue
                    
                # Check file extension if specified
                if file_extensions and file_path.suffix not in file_extensions:
                    continue
                
                files_searched += 1
                
                # For glob mode, we return file matches rather than content matches
                match_info = {
                    "file": str(file_path.relative_to(search_dir)),
                    "line": 1,  # No line-specific match for glob
                    "match": file_path.name,
                    "context": f"File: {file_path.name}",
                    "size": file_path.stat().st_size if file_path.exists() else 0
                }
                matches.append(match_info)
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Glob search failed: {str(e)}",
                "matches": [],
                "total_matches": 0,
                "files_searched": 0
            }
        
        return {
            "success": True,
            "matches": matches,
            "total_matches": len(matches),
            "files_searched": files_searched,
            "pattern": pattern,
            "mode": "glob"
        }
    
    async def _assemble_and_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Assemble all project files and run the entry point.
        
        This is the final step after all individual files have been written.
        It verifies all files exist, then runs the main entry point.
        """
        project_name = payload.get("project_name", "project")
        all_files = payload.get("all_files", [])
        user_request = payload.get("user_request", "")
        upstream_context = payload.get("upstream_context", {})
        
        project_dir = self.work_dir / project_name
        
        # Clean stale files from previous runs that aren't in the current plan.
        # This prevents old broken files from poisoning new builds.
        if project_dir.exists():
            expected_paths = {f["path"] for f in all_files}
            for existing in project_dir.glob("*.py"):
                rel = existing.name
                if rel not in expected_paths and rel != "run_preview.py":
                    existing.unlink(missing_ok=True)
                    logger.info("Cleaned stale file: %s", rel)
        
        await self.send_progress({
            "stage": "assembling",
            "project_name": project_name,
            "total_files": len(all_files),
        })
        
        # Verify all files exist
        missing = []
        written_files = {}
        for f in all_files:
            fpath = project_dir / f["path"]
            if fpath.exists():
                written_files[f["path"]] = fpath.read_text(encoding="utf-8")
            else:
                missing.append(f["path"])
        
        if missing:
            # Some files are missing — they might be in upstream_context
            # Collect files to write concurrently
            files_to_write = []
            for source, result in upstream_context.items():
                if isinstance(result, dict):
                    content = result.get("file_content", "")
                    fp = result.get("file_path", "")
                    if fp and content and fp in missing:
                        files_to_write.append((fp, content))
            
            if files_to_write:
                # Write missing files concurrently using asyncio.gather
                async def write_missing_file(file_path: str, content: str) -> tuple[str, bool]:
                    try:
                        full_path = project_dir / file_path
                        full_path.parent.mkdir(exist_ok=True, parents=True)
                        await self._write_and_notify(full_path, content)
                        return file_path, True
                    except Exception:
                        return file_path, False
                
                # Write all missing files concurrently
                write_results = await asyncio.gather(
                    *[write_missing_file(fp, content) for fp, content in files_to_write],
                    return_exceptions=True
                )
                
                # Process results
                for i, result in enumerate(write_results):
                    if isinstance(result, tuple):
                        fp, success = result
                        if success:
                            written_files[fp] = files_to_write[i][1]  # content
                            missing.remove(fp)
                    # If result is an exception, file remains missing
        
        if missing:
            return {
                "success": False,
                "error": f"Missing project files: {', '.join(missing)}",
                "stdout": "", "stderr": f"Files not found: {missing}",
                "exit_code": -1,
            }
        
        # Syntax-check all Python files before running
        syntax_errors = []
        for fpath, content in written_files.items():
            if fpath.endswith(".py"):
                try:
                    compile(content, fpath, "exec")
                except SyntaxError as e:
                    syntax_errors.append(f"{fpath}:{e.lineno}: {e.msg}")
        
        if syntax_errors:
            error_list = "\n".join(syntax_errors)
            return {
                "success": False,
                "error": f"Syntax errors in {len(syntax_errors)} file(s):\n{error_list}",
                "stdout": "",
                "stderr": error_list,
                "exit_code": -4,
                "files_with_errors": syntax_errors,
            }
        
        # The architect owns the entry point contract. A non-executable
        # deliverable is allowed only through its explicit structured flag.
        executable = payload.get("executable", True) is not False
        if not executable:
            import time
            project_manifest = {
                "name": project_name,
                "created": time.time(),
                "executable": False,
                "entry_point": None,
            }
            (project_dir / ".project.json").write_text(
                json.dumps(project_manifest, indent=2), encoding="utf-8")
            await self.send_progress({
                "stage": "completed",
                "success": True,
                "files_verified": len(written_files),
                "runnable": False,
            })
            return {
                "success": True,
                "stdout": "",
                "stderr": "",
                "exit_code": None,
                "project_name": project_name,
                "entry_point": None,
                "runnable": False,
                "files_written": list(written_files.keys()),
            }

        # Never guess by running the last file: that turned passive modules
        # into false successes.
        entry_point = str(payload.get("entry_point") or "main.py")
        if entry_point not in written_files:
            return {
                "success": False,
                "error": f"Declared entry point is missing: {entry_point}",
                "stdout": "",
                "stderr": f"{entry_point} is not present in the project plan",
                "exit_code": -5,
                "entry_point": entry_point,
                "project_name": project_name,
                "files_written": list(written_files.keys()),
            }
        
        # Detect if this is a web server project
        is_web = self._is_web_project(written_files)
        
        await self.send_progress({
            "stage": "running",
            "entry_point": entry_point,
            "files_verified": len(written_files),
            "is_web_app": is_web,
        })
        
        entry_path = project_dir / entry_point
        timeout = payload.get("timeout", self.timeout)
        
        import time
        start_time = time.time()
        
        if is_web:
            # --- Web app: start as background preview server ---
            return await self._start_preview_server(
                project_dir, entry_path, project_name, all_files,
                written_files, start_time
            )
        
        # --- Regular script: run to completion (in venv) ---
        try:
            venv_python = await self._setup_project_venv(project_dir)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create venv: {e}",
                "stdout": "", "stderr": str(e), "exit_code": -3,
                "execution_time": 0,
            }

        run_env = self._get_execution_env()
        run_env["VIRTUAL_ENV"] = str(project_dir / ".venv")
        venv_bin = str(project_dir / ".venv" / "bin")
        run_env["PATH"] = f"{venv_bin}:{run_env.get('PATH', '')}"

        try:
            # Multi-file projects use the same line streaming path as
            # single-file executions. -u disables Python child buffering.
            stdout_str, stderr_str, exit_code, timed_out = await self._exec_streamed(
                [str(venv_python), "-u", str(entry_path)],
                cwd=str(project_dir),
                env=run_env,
                timeout=timeout,
            )
                
        except Exception as e:
            end_time = time.time()
            return {
                "success": False,
                "error": str(e),
                "stdout": "", "stderr": str(e), "exit_code": -2,
                "execution_time": end_time - start_time,
            }
        
        end_time = time.time()
        success = exit_code == 0 and bool(stdout_str.strip())
        if exit_code == 0 and not stdout_str.strip():
            exit_code = -6
            stderr_str = (
                stderr_str.rstrip() + "\n" if stderr_str.strip() else ""
            ) + (
                "Entry point exited successfully but produced no output. "
                "A runnable project must provide a non-interactive demo/result."
            )
        
        # Build project summary
        file_summary = "\n".join(f"  {f['path']} ({len(written_files.get(f['path'], ''))} chars)"
                                  for f in all_files)
        
        result = {
            "success": success,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": exit_code,
            "execution_time": end_time - start_time,
            "timed_out": timed_out,
            "entry_point": entry_point,
            "project_name": project_name,
            "files_written": list(written_files.keys()),
            "project_summary": file_summary,
        }

        if success:
            project_manifest = {
                "name": project_name,
                "created": time.time(),
                "entry_point": entry_point,
                "run": ["python", entry_point],
            }
            (project_dir / ".project.json").write_text(
                json.dumps(project_manifest, indent=2), encoding="utf-8")

        # Project evidence covers the complete planned file set, not only
        # the entry point. Nested tests are discovered from the project root.
        if self._evidence_enabled:
            try:
                import platform as _platform
                from ..verification.evidence import default_repository
                from ..verification.gate import RunGate

                planned_files = [f["path"] for f in all_files]
                manifest, verdict = await RunGate(default_repository()).evaluate_attempt(
                    user_request=user_request or f"assemble project {project_name}",
                    code=written_files[entry_point],
                    execution=result,
                    work_dir=project_dir,
                    requested_files=planned_files,
                    persisted_files=list(written_files),
                    toolchain={"python": _platform.python_version(), "brain": self.name},
                    filename=entry_point,
                )
                result["verification"] = {
                    "run_id": manifest.run_id,
                    "verdict": verdict,
                    "stages": [{"name": s.name, "status": s.status}
                               for s in manifest.stages],
                }
                await self._notify_verification(manifest, verdict)
                if verdict != "passed":
                    success = False
                    result["success"] = False
                    result["runnable"] = False
                    (project_dir / ".project.json").unlink(missing_ok=True)
                    result["error"] = (
                        f"Project verification {verdict}; it is not deliverable"
                    )
            except Exception as gate_error:
                result["verification"] = {
                    "verdict": None, "error": str(gate_error)[:200]}

        
        if not success:
            result["error"] = f"Project is not runnable via {entry_point} (exit {exit_code})"
            if stderr_str:
                result["error"] += f": {stderr_str[:200]}"
        
        await self.send_progress({
            "stage": "completed",
            "success": success,
            "entry_point": entry_point,
            "exit_code": exit_code,
            "execution_time": end_time - start_time,
        })
        
        return result
    
    async def _start_preview_server(
        self, project_dir: Path, entry_path: Path, project_name: str,
        all_files: list, written_files: dict, start_time: float,
    ) -> Dict[str, Any]:
        """Start a web app as a local preview server on a free port.

        Security model:
        - Each project gets its own venv (no system pip pollution)
        - Sensitive env vars are stripped (API keys, tokens, etc.)
        - Server binds to 127.0.0.1 only (Cloudflare tunnel for external)
        """
        import time

        port = self._find_free_preview_port()
        if port is None:
            return {
                "success": False,
                "error": "No free preview ports available (3100-3199 all in use)",
                "stdout": "", "stderr": "", "exit_code": -1,
                "execution_time": time.time() - start_time,
            }

        # Kill any previous preview from this brain
        if self._preview_process and self._preview_process.returncode is None:
            try:
                self._preview_process.terminate()
                await asyncio.wait_for(self._preview_process.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    self._preview_process.kill()
                except ProcessLookupError:
                    pass

        # --- Create per-project venv ---
        try:
            venv_python = await self._setup_project_venv(project_dir)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create venv: {e}",
                "stdout": "", "stderr": str(e), "exit_code": -3,
                "execution_time": time.time() - start_time,
            }

        # Patch the entry point to use our port (inject PORT env var)
        env = self._get_execution_env()
        env["PORT"] = str(port)
        env["HOST"] = "0.0.0.0"
        # Point VIRTUAL_ENV so child processes know they're in a venv
        env["VIRTUAL_ENV"] = str(project_dir / ".venv")
        # Prepend venv bin to PATH so pip-installed console_scripts work
        venv_bin = str(project_dir / ".venv" / "bin")
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"

        # Patch the entry file to use our PORT env var.
        # Strategy: replace port= in .run() calls — handles both literal numbers
        # (port=5000) and variable references (port=port, port=args.port).
        entry_code = entry_path.read_text(encoding="utf-8")
        patched = False
        env_port_expr = f'int(os.environ.get("PORT", {port}))'

        # Patch uvicorn.run(..., port=...) → use env PORT
        if "uvicorn.run" in entry_code and f'os.environ.get("PORT"' not in entry_code:
            patched_code = re.sub(
                r'(uvicorn\.run\([^)]*?)port\s*=\s*[^,\)]+',
                rf'\1port={env_port_expr}',
                entry_code
            )
            if patched_code != entry_code:
                if "import os" not in patched_code:
                    patched_code = "import os\n" + patched_code
                entry_path.write_text(patched_code, encoding="utf-8")
                patched = True

        # Patch socketio.run(..., port=...) → use env PORT
        if not patched and "socketio.run" in entry_code and f'os.environ.get("PORT"' not in entry_code:
            patched_code = re.sub(
                r'(socketio\.run\([^)]*?)port\s*=\s*[^,\)]+',
                rf'\1port={env_port_expr}',
                entry_code
            )
            if patched_code != entry_code:
                if "import os" not in patched_code:
                    patched_code = "import os\n" + patched_code
                entry_path.write_text(patched_code, encoding="utf-8")
                patched = True

        # Patch Flask/generic .run(..., port=...) → use env PORT
        if not patched and ".run(" in entry_code and f'os.environ.get("PORT"' not in entry_code:
            patched_code = re.sub(
                r'(\.run\([^)]*?)port\s*=\s*[^,\)]+',
                rf'\1port={env_port_expr}',
                entry_code
            )
            if patched_code != entry_code:
                if "import os" not in patched_code:
                    patched_code = "import os\n" + patched_code
                entry_path.write_text(patched_code, encoding="utf-8")
                patched = True

        # Fallback: if argparse sets port default, patch the default too
        if not patched and "argparse" in entry_code and "default=" in entry_code:
            patched_code = re.sub(
                r"(--port['\"].*?default\s*=\s*)\d+",
                rf"\g<1>{port}",
                entry_code
            )
            if patched_code != entry_code:
                entry_path.write_text(patched_code, encoding="utf-8")
                patched = True

        await self.send_progress({
            "stage": "starting_server",
            "port": port,
            "entry_point": str(entry_path.name),
            "patched_port": patched,
            "venv": True,
        })

        # --- Install dependencies into venv ---
        requirements = project_dir / "requirements.txt"
        if requirements.exists():
            await self._install_in_venv(
                venv_python, project_dir, [], from_requirements=True
            )
        else:
            # Auto-detect common web framework imports
            all_code = "\n".join(written_files.values())
            auto_deps = []
            dep_map = {
                r"from\s+fastapi\b|import\s+fastapi": "fastapi uvicorn",
                r"from\s+flask\b|import\s+flask": "flask",
                r"from\s+flask_socketio\b|import\s+flask_socketio": "flask-socketio",
                r"import\s+socketio|from\s+socketio\b": "python-socketio",
                r"import\s+uvicorn": "uvicorn",
                r"from\s+starlette\b": "starlette",
                r"import\s+aiohttp|from\s+aiohttp\b": "aiohttp",
                r"from\s+aiohttp_session\b": "aiohttp-session",
                r"from\s+pydantic\b": "pydantic",
                r"import\s+jwt|from\s+jose\b": "python-jose[cryptography]",
                r"from\s+passlib\b": "passlib[bcrypt]",
                r"import\s+bcrypt|from\s+bcrypt\b": "bcrypt",
                r"from\s+sqlalchemy\b": "sqlalchemy",
                r"import\s+peewee|from\s+peewee\b": "peewee",
                r"from\s+jinja2\b": "jinja2",
                r"import\s+websockets|from\s+websockets\b": "websockets",
                r"from\s+motor\b": "motor",
                r"import\s+pymongo|from\s+pymongo\b": "pymongo",
                r"import\s+redis|from\s+redis\b": "redis",
                r"from\s+cryptography\b": "cryptography",
                r"import\s+httpx|from\s+httpx\b": "httpx",
                r"from\s+tortoise\b": "tortoise-orm",
                r"from\s+databases\b": "databases",
            }
            for pattern, packages in dep_map.items():
                if re.search(pattern, all_code):
                    auto_deps.extend(packages.split())
            
            # Generic fallback: catch remaining third-party imports
            # by scanning for ModuleNotFoundError-prone patterns
            stdlib_modules = {
                "os", "sys", "json", "re", "time", "datetime", "pathlib",
                "asyncio", "typing", "dataclasses", "hashlib", "secrets",
                "uuid", "logging", "collections", "functools", "itertools",
                "contextlib", "abc", "enum", "sqlite3", "http", "html",
                "urllib", "base64", "hmac", "struct", "io", "math",
                "random", "string", "textwrap", "copy", "shutil",
                "tempfile", "glob", "fnmatch", "stat", "socket",
                "email", "mimetypes", "csv", "configparser", "argparse",
                "subprocess", "threading", "multiprocessing", "signal",
                "traceback", "inspect", "importlib", "pkgutil",
            }
            import_re = re.compile(
                r"(?:from\s+(\w+)|import\s+(\w+))"
            )
            for m in import_re.finditer(all_code):
                mod = m.group(1) or m.group(2)
                if mod and mod not in stdlib_modules and mod not in auto_deps:
                    # Convert underscores to dashes (common PyPI convention)
                    pkg = mod.replace("_", "-")
                    if pkg not in auto_deps:
                        auto_deps.append(pkg)

            if auto_deps:
                auto_deps = list(dict.fromkeys(auto_deps))  # deduplicate
                await self._install_in_venv(venv_python, project_dir, auto_deps)

        # --- Start the server using venv python ---
        try:
            self._preview_process = await asyncio.create_subprocess_exec(
                str(venv_python), str(entry_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
                env=env,
            )
            PythonBrain._active_previews[port] = self._preview_process
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to start server: {e}",
                "stdout": "", "stderr": str(e), "exit_code": -2,
                "execution_time": time.time() - start_time,
            }
        
        # Wait a few seconds for the server to start, then check if it's alive
        await asyncio.sleep(2)
        
        if self._preview_process.returncode is not None:
            # Server crashed on startup
            stdout = await self._preview_process.stdout.read()
            stderr = await self._preview_process.stderr.read()
            PythonBrain._active_previews.pop(port, None)
            return {
                "success": False,
                "error": f"Server crashed on startup (exit {self._preview_process.returncode})",
                "stdout": stdout.decode("utf-8", errors="replace")[:2000],
                "stderr": stderr.decode("utf-8", errors="replace")[:2000],
                "exit_code": self._preview_process.returncode,
                "execution_time": time.time() - start_time,
            }
        
        # Verify port is responding
        server_up = False
        for _ in range(5):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                try:
                    s.connect(("127.0.0.1", port))
                    server_up = True
                    break
                except (ConnectionRefusedError, OSError):
                    await asyncio.sleep(1)
        
        file_summary = "\n".join(
            f"  {f['path']} ({len(written_files.get(f['path'], ''))} chars)"
            for f in all_files
        )
        
        local_url = f"http://127.0.0.1:{port}"
        
        result = {
            "success": server_up,
            "preview_url": local_url,
            "preview_port": port,
            "server_running": True,
            "server_pid": self._preview_process.pid,
            "entry_point": entry_path.name,
            "project_name": project_name,
            "files_written": list(written_files.keys()),
            "project_summary": file_summary,
            "execution_time": time.time() - start_time,
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }
        
        if not server_up:
            result["success"] = False
            result["error"] = f"Server started (PID {self._preview_process.pid}) but port {port} not responding after 7s"
        
        await self.send_progress({
            "stage": "server_running" if server_up else "server_failed",
            "port": port,
            "url": local_url,
            "pid": self._preview_process.pid,
        })
        
        return result

    # --- Honk Pattern: Inner Loop (generate → execute → verify → fix → repeat) ---

    MAX_RETRIES = 5  # Inner loop iterations before giving up

    async def _persist_requested_file(self, user_request: str, code: str) -> str | None:
        """Save generated code under the filename the user asked for.

        The execution itself runs in a temp file the user never sees; when
        the request names a file (\"crée un script hello.py\"), the code must
        land at that exact path in the workspace so the claim is true and
        the explorer shows it (workspace.file_written).
        """
        from ..verification.executors import extract_requested_file

        file_name = extract_requested_file(user_request)
        if not file_name:
            return None
        try:
            await self._write_and_notify(self.work_dir / file_name, code)
            return file_name
        except Exception:
            return None

    async def _generate_and_execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generate code via LLM, execute, and retry on failure (Honk inner loop).

        Spotify Honk pattern:
        1. Generate code from natural language request
        2. Execute in subprocess
        3. If it fails → feed errors back to LLM with Reflexion memory
        4. LLM fixes the code (seeing previous errors, NOT repeating them)
        5. Repeat up to MAX_RETRIES times
        6. Return final result with full attempt history
        """
        if not self.llm_provider:
            return {
                "success": False,
                "error": "No LLM provider configured — cannot generate code. Provide code directly.",
                "stdout": "", "stderr": "", "exit_code": -1,
            }

        user_request = payload.get("user_request", payload.get("query", ""))
        if not user_request:
            return {"success": False, "error": "No request provided", "stdout": "", "stderr": "", "exit_code": -1}

        # Upstream context from other brains (e.g., researcher results)
        upstream_context = payload.get("upstream_context", {})

        max_retries = payload.get("max_retries", self.MAX_RETRIES)
        timeout = payload.get("timeout", self.timeout)

        # Reflexion memory — tracks errors across attempts so LLM doesn't repeat them
        attempt_history: list[dict] = []
        # Evidence chain: each attempt's manifest links to the previous one.
        last_run_id = None

        for attempt in range(1, max_retries + 1):
            await self.send_progress({
                "stage": "generating_code",
                "attempt": attempt,
                "max_attempts": max_retries,
                "request": user_request[:100],
            })

            try:
                # Generate (or fix) code
                if attempt == 1:
                    code = await self._generate_initial_code(user_request, upstream_context, payload)
                else:
                    code = await self._fix_code(user_request, attempt_history)

                if not code.strip():
                    attempt_history.append({
                        "attempt": attempt,
                        "error": "LLM returned empty code",
                        "code": "",
                    })
                    continue

                await self.send_progress({
                    "stage": "executing",
                    "attempt": attempt,
                    "code_lines": code.count("\n") + 1,
                })

                # Execute
                result = await self._execute_code(code, timeout)
                result["generated_code"] = code
                result["attempt"] = attempt
                result["total_attempts"] = attempt
                result["attempt_history"] = attempt_history

                has_output = bool(result.get("stdout", "").strip())
                no_errors = result.get("exit_code") == 0 and not result.get("stderr", "").strip()

                # Deterministic gate (harness P2): record evidence for this
                # attempt and derive a conservative verdict. The gate must
                # never break generation — on internal error we degrade to
                # the legacy behavior (verdict None).
                saved_as = None
                if no_errors:
                    # Persist BEFORE the gate: the contracts stage checks
                    # that the requested file exists in the workspace.
                    saved_as = await self._persist_requested_file(user_request, code)
                verdict, verification = None, None
                if self._evidence_enabled:
                    try:
                        import platform as _platform

                        from ..verification.evidence import default_repository
                        from ..verification.gate import RunGate

                        manifest, verdict = await RunGate(default_repository()).evaluate_attempt(
                            user_request=user_request,
                            code=code,
                            execution=result,
                            work_dir=self.work_dir,
                            persisted_file=saved_as,
                            attempt=attempt,
                            parent_run_id=last_run_id,
                            toolchain={"python": _platform.python_version(),
                                       "brain": self.name},
                        )
                        last_run_id = manifest.run_id
                        verification = {
                            "run_id": manifest.run_id,
                            "verdict": verdict,
                            "stages": [{"name": s.name, "status": s.status}
                                       for s in manifest.stages],
                        }
                        await self._notify_verification(manifest, verdict,
                                                        attempt=attempt)
                    except Exception as gate_error:
                        verification = {"verdict": None,
                                        "error": str(gate_error)[:200]}
                if verification is not None:
                    result["verification"] = verification

                if no_errors and has_output and verdict == "failed":
                    # The gate rejected a clean execution (e.g. the requested
                    # file never landed in the workspace). Fixable: feed the
                    # failed stage details back to the LLM like any error.
                    failed = [f"{s['name']}={s['status']}"
                              for s in verification["stages"]
                              if s["status"] == "failed"]
                    error_info = {
                        "attempt": attempt,
                        "code": code,
                        "exit_code": 0,
                        "stderr": ("DETERMINISTIC GATE FAILED — " + "; ".join(failed)
                                   + ". The verification stages listed as failed must pass."),
                        "stdout": "",
                    }
                    attempt_history.append(error_info)
                    if attempt < max_retries:
                        await self.send_progress({
                            "stage": "retrying",
                            "attempt": attempt,
                            "error": error_info["stderr"][:100],
                            "next_attempt": attempt + 1,
                        })
                        continue
                    result["success"] = False
                    result["error"] = error_info["stderr"]
                    await self.send_progress({
                        "stage": "failed_after_retries",
                        "attempts": attempt,
                    })
                    return result

                if no_errors and has_output:
                    # Clean success with output
                    result["success"] = True
                    if saved_as:
                        result["saved_as"] = saved_as
                    if verdict == "inconclusive":
                        # The script ran; a mandatory stage could not produce
                        # evidence (e.g. tests present, pytest missing). Never
                        # claimed as verified — labelled explicitly instead.
                        result["warning"] = "Executed, but not fully verified: " + "; ".join(
                            f"{s['name']}={s['status']}"
                            for s in verification["stages"]
                            if s["status"] == "inconclusive")
                    await self.send_progress({
                        "stage": "succeeded",
                        "attempt": attempt,
                        "success": True,
                        **({"saved_as": saved_as} if saved_as else {}),
                    })
                    return result
                
                if no_errors and not has_output:
                    # Code ran but produced no stdout — treat as fixable failure.
                    # This is the #1 cause of "empty Python tab" in the UI.
                    error_info = {
                        "attempt": attempt,
                        "code": code,
                        "exit_code": 0,
                        "stderr": "CODE PRODUCED NO OUTPUT. The script ran successfully but never called print(). You MUST add print() statements that display the results, statistics, or key values. A script with no printed output is useless.",
                        "stdout": "",
                    }
                    attempt_history.append(error_info)
                    
                    if attempt < max_retries:
                        await self.send_progress({
                            "stage": "retrying",
                            "attempt": attempt,
                            "error": "No stdout output — adding print statements",
                            "next_attempt": attempt + 1,
                        })
                        continue
                    else:
                        # Final attempt still no output — return what we have
                        result["total_attempts"] = attempt
                        result["attempt_history"] = attempt_history
                        result["success"] = True  # Code did run, just no output
                        result["warning"] = "Code executed successfully but produced no printed output"
                        return result

                # Execution failed — record for Reflexion and retry
                error_info = {
                    "attempt": attempt,
                    "code": code,
                    "exit_code": result.get("exit_code"),
                    "stderr": result.get("stderr", "")[:500],
                    "stdout": result.get("stdout", "")[:200],
                }
                attempt_history.append(error_info)

                if attempt < max_retries:
                    await self.send_event("brain.retry", {
                        "brain": self.name,
                        "attempt": attempt,
                        "max_attempts": max_retries,
                        "error": error_info["stderr"][:100],
                    })
                    await self.send_progress({
                        "stage": "retrying",
                        "attempt": attempt,
                        "error": error_info["stderr"][:100],
                        "next_attempt": attempt + 1,
                    })
                else:
                    # Final attempt failed — return the best result we have
                    result["total_attempts"] = attempt
                    result["attempt_history"] = attempt_history
                    await self.send_progress({
                        "stage": "failed_after_retries",
                        "attempts": attempt,
                    })
                    return result

            except Exception as e:
                attempt_history.append({
                    "attempt": attempt,
                    "error": str(e),
                    "code": "",
                })
                if attempt == max_retries:
                    return {
                        "success": False,
                        "error": f"Code generation failed after {attempt} attempts: {e}",
                        "stdout": "", "stderr": str(e), "exit_code": -1,
                        "total_attempts": attempt,
                        "attempt_history": attempt_history,
                    }

        # Should not reach here, but safety return
        return {
            "success": False,
            "error": f"All {max_retries} attempts failed",
            "stdout": "", "stderr": "", "exit_code": -1,
            "attempt_history": attempt_history,
        }

    async def _generate_initial_code(self, user_request: str, 
                                     upstream_context: dict = None,
                                     payload: dict = None) -> str:
        """Generate initial code from natural language (attempt 1)."""
        # Build context from upstream brain results (e.g., researcher findings)
        context_section = ""
        
        # Check for task state from orchestrator's TaskTracker
        task_state_section = ""
        if payload and "_task_state" in payload:
            task_state = payload["_task_state"]
            task_state_section = f"\n\n## Current Project Progress\n{task_state}\n"
        
        # Check for user interjection
        user_interjection_section = ""
        if payload and "_user_interjection" in payload:
            user_message = payload["_user_interjection"]
            user_interjection_section = f"\n\n## User Message (Mid-Task)\nThe user just said: \"{user_message}\"\nTake this into account when generating the code.\n"
        
        if upstream_context:
            context_parts = []
            for source, result in upstream_context.items():
                if isinstance(result, dict):
                    data = result.get("data", result)
                    # Extract useful text from research results
                    summary = data.get("summary", data.get("answer", ""))
                    if summary:
                        context_parts.append(f"From {source}:\n{str(summary)[:500]}")
                    else:
                        context_parts.append(f"From {source}:\n{str(data)[:300]}")
                else:
                    context_parts.append(f"From {source}:\n{str(result)[:300]}")
            if context_parts:
                context_section = "\n\nContext from other brains (use this information):\n" + "\n\n".join(context_parts) + "\n"

        prompt = f"""Write a Python script that does the following:

{user_request}
{user_interjection_section}{task_state_section}{context_section}
Rules:
- Output ONLY the Python code, no explanation before or after
- The code must be self-contained and runnable as a script
- No external dependencies beyond the standard library (no numpy, scipy, matplotlib, etc.)
- Keep execution time under 30 seconds — limit iterations/grid sizes to stay fast
- Include error handling where appropriate
- For f-strings with dict access, use double quotes outside and bracket notation: f"{{d['key']}}" or use variables: val = d['key']; f"{{val}}"
- Ensure all strings are properly closed on the same line

⚠️ CRITICAL — PRINT OUTPUT IS MANDATORY:
The script's stdout is the ONLY way results reach the user.
If the script produces no printed output, it is considered BROKEN.
You MUST include print() calls that show:
- The actual results/answer to the user's request
- Key statistics, values, or insights
- A summary at the end
A script that computes something but never prints it is USELESS."""

        generated = await self.llm_provider.complete(prompt, stream=False)
        return self._extract_code(generated)

    async def _fix_code(self, user_request: str, attempt_history: list[dict]) -> str:
        """Fix code based on Reflexion memory of previous errors.

        Uses diff/patch approach for efficiency:
        - Small errors (syntax, typos): LLM outputs SEARCH/REPLACE blocks
        - Large errors (logic, redesign): LLM outputs full corrected code
        - Falls back to full code if diff application fails
        """
        last = attempt_history[-1]
        last_code = last.get("code", "")
        last_error = last.get("stderr", "") or last.get("error", "")

        # Build concise error summary from ALL attempts
        error_summary = []
        for entry in attempt_history:
            err = entry.get("stderr", "") or entry.get("error", "")
            if err:
                error_summary.append(f"  Attempt {entry['attempt']}: {err[:200]}")
        errors_text = "\n".join(error_summary)

        # Analyze error patterns for targeted hints
        hints = []
        error_lower = last_error.lower()
        if "syntaxerror" in error_lower and "f-string" in error_lower:
            hints.append("- The f-string syntax is broken. Extract dict values to variables BEFORE the f-string.")
        if "syntaxerror" in error_lower and "unterminated" in error_lower:
            hints.append("- A string literal is not properly closed. Check all quotes match.")
        if "modulenotfounderror" in error_lower or "no module named" in error_lower:
            hints.append("- External module missing. Use ONLY standard library (no numpy, scipy, matplotlib, pandas).")
        if "indentationerror" in error_lower:
            hints.append("- Fix indentation. Use consistent 4-space indentation.")
        hints_text = "\n".join(hints) if hints else "- Carefully analyze the error and fix the root cause."

        # Number the lines for precise diff references
        numbered_code = "\n".join(
            f"{i+1:4d} | {line}" for i, line in enumerate(last_code.split("\n"))
        )

        prompt = f"""Fix this Python script using SEARCH/REPLACE blocks.

The numbered code that failed:
{numbered_code}

Error:
{last_error[:500]}

All errors so far (do NOT repeat ANY of these):
{errors_text}

Fix instructions:
{hints_text}

Output your fix as one or more SEARCH/REPLACE blocks. Each block looks like:

<<<< SEARCH
exact lines to find (copy from the code above, WITHOUT line numbers)
====
replacement lines
>>>> REPLACE

Rules:
- SEARCH text must match the original code EXACTLY (without the line numbers)
- Only include the lines that need to change (plus enough context to be unique)
- If the fix requires rewriting most of the file, output the FULL corrected code in a ```python block instead
- No external dependencies beyond the standard library
- Use print() to show results
- Original request: {user_request}"""

        generated = await self.llm_provider.complete(prompt, stream=False)

        # Try to apply diff/patch first
        patched = self._apply_search_replace(last_code, generated)
        if patched is not None:
            return patched

        # Fallback: extract full code block
        return self._extract_code(generated)

    @staticmethod
    def _apply_search_replace(original: str, llm_output: str) -> str | None:
        """Apply SEARCH/REPLACE blocks to original code.
        
        Returns patched code, or None if no valid blocks found or application fails.
        """
        import re
        
        # Find all SEARCH/REPLACE blocks
        pattern = r'<{4}\s*SEARCH\n(.*?)\n={4}\n(.*?)\n>{4}\s*REPLACE'
        matches = re.findall(pattern, llm_output, re.DOTALL)
        
        if not matches:
            return None
        
        result = original
        applied = 0
        
        for search_text, replace_text in matches:
            search_text = search_text.strip('\n')
            replace_text = replace_text.strip('\n')
            
            if search_text in result:
                result = result.replace(search_text, replace_text, 1)
                applied += 1
            else:
                # Try fuzzy match — strip leading whitespace differences
                search_stripped = "\n".join(l.strip() for l in search_text.split("\n"))
                lines = result.split("\n")
                
                # Sliding window search
                search_lines = search_stripped.split("\n")
                found = False
                for i in range(len(lines) - len(search_lines) + 1):
                    window = "\n".join(l.strip() for l in lines[i:i+len(search_lines)])
                    if window == search_stripped:
                        # Preserve original indentation of first line
                        indent = len(lines[i]) - len(lines[i].lstrip())
                        indent_str = " " * indent
                        replace_lines = replace_text.split("\n")
                        indented_replace = [indent_str + l if l.strip() else l for l in replace_lines]
                        lines[i:i+len(search_lines)] = indented_replace
                        result = "\n".join(lines)
                        applied += 1
                        found = True
                        break
                
                if not found:
                    # This block failed to apply — bail to full regeneration
                    return None
        
        return result if applied > 0 else None
    
    @staticmethod
    @staticmethod
    def _check_syntax(code: str, filename: str = "<code>") -> Optional[str]:
        """Check Python code for syntax errors.
        
        Returns None if syntax is valid, or an error message string if not.
        """
        try:
            compile(code, filename, "exec")
            return None
        except SyntaxError as e:
            parts = [f"SyntaxError in {filename}"]
            if e.lineno:
                parts.append(f"line {e.lineno}")
            if e.msg:
                parts.append(e.msg)
            if e.text:
                parts.append(f"  {e.text.rstrip()}")
                if e.offset:
                    parts.append(f"  {' ' * (e.offset - 1)}^")
            return "\n".join(parts)

    @staticmethod
    def _is_truncation_error(error: str, code: str) -> bool:
        """Detect if a syntax error is caused by truncated LLM output.
        
        Truncation signs: unexpected EOF, unclosed brackets/quotes at the
        very end of the file, or the error is on the last line.
        """
        if not error or not code:
            return False
        error_lower = error.lower()
        truncation_markers = [
            "unexpected eof",
            "eof while scanning",
            "was never closed",
            "unexpected end of input",
            "expected an indented block",
        ]
        if any(marker in error_lower for marker in truncation_markers):
            return True
        # Error on the very last line is often truncation
        lines = code.strip().split("\n")
        if lines:
            try:
                # Extract line number from error
                for part in error.split("\n"):
                    if "line " in part.lower():
                        import re as _re
                        m = _re.search(r"line\s+(\d+)", part, _re.IGNORECASE)
                        if m:
                            err_line = int(m.group(1))
                            if err_line >= len(lines) - 2:
                                return True
            except (ValueError, AttributeError):
                pass
        return False

    def _build_continuation_prompt(
        self, file_path: str, project_name: str, truncated_code: str,
    ) -> str:
        """Build a prompt to continue truncated code from where it stopped.
        
        Sends the last 80 lines and asks the LLM to write ONLY the
        remaining code — not the whole file again.
        """
        lines = truncated_code.split("\n")
        # Show last 80 lines for context
        context_start = max(0, len(lines) - 80)
        context = "\n".join(lines[context_start:])
        
        return f"""The file `{file_path}` in project "{project_name}" was truncated.
Here are the last {len(lines) - context_start} lines (of {len(lines)} total):

```python
{context}
```

Continue writing from EXACTLY where it stopped. Output ONLY the remaining
code that completes this file. Do NOT repeat any of the code above.
Do NOT include the opening ``` fence. Just the raw Python code that comes next.
Make sure to close ALL open brackets, strings, and function definitions."""

    def _build_file_fix_prompt(
        self,
        file_path: str,
        project_name: str,
        user_request: str,
        previous_code: str,
        attempt_history: list,
        original_prompt: str,
    ) -> str:
        """Build a fix prompt for a file that failed syntax check.
        
        Includes the original spec, the broken code, and the errors —
        following the Reflexion pattern from the Honk loop.
        """
        error_summary = "\n".join(
            f"Attempt {h['attempt']}: {h['error']}" for h in attempt_history
        )

        return f"""Fix the file `{file_path}` for project "{project_name}".

The previous version had errors. Here is what went wrong:

{error_summary}

Previous broken code:
```
{previous_code[:4000]}
```

{original_prompt}

CRITICAL: Fix ALL syntax errors. Do not repeat the same mistakes.
Output ONLY the corrected file content, no explanation."""

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extract Python code from LLM response (handles markdown fences)."""
        # If wrapped in ```python ... ``` or ``` ... ```
        if "```" in text:
            lines = text.split("\n")
            code_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.strip() == "```" and in_block:
                    in_block = False
                    continue
                elif in_block:
                    code_lines.append(line)
            if code_lines:
                return "\n".join(code_lines)
        
        # No fences — return as-is
        return text
    
    async def _create_task_files(self, files: Dict[str, str]) -> None:
        """Create additional files requested by the task."""
        for filename, content in files.items():
            file_path = self.work_dir / filename
            file_path.write_text(content, encoding='utf-8')
            self._temp_files.add(file_path)
    
    async def _exec_streamed(self, args: list, *, cwd,
                             env=None, timeout: int) -> tuple:
        """Run a subprocess and stream its output line by line.

        Every stdout/stderr line is broadcast as an `execution.output`
        bus event (brain + subtask_id + stream + delta) so the UI shows
        what the agent is doing WHILE it works — the user is no longer
        blind during a run. Best effort: an event failure never breaks
        the execution. `-u` keeps the child from block-buffering.

        Returns (stdout_str, stderr_str, exit_code, timed_out); partial
        output collected before a timeout is preserved.
        """
        from ..bus.message import Priority

        # stdin = DEVNULL: an input() or sys.stdin.read() gets an
        # immediate EOF instead of hanging the run until its timeout.
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            env=env,
        )
        subtask_id = None
        if self._current_task and self._current_task.payload:
            subtask_id = self._current_task.payload.get("_subtask_id")

        out_buf: list = []
        err_buf: list = []

        async def pump(stream, name: str, buf: list) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace")
                buf.append(text)
                try:
                    await self.send_event("execution.output", {
                        "brain": self.name,
                        "subtask_id": subtask_id,
                        "stream": name,
                        "delta": text,
                    })
                except Exception:
                    pass  # streaming must never break the execution

        try:
            await asyncio.wait_for(asyncio.gather(
                pump(process.stdout, "out", out_buf),
                pump(process.stderr, "err", err_buf),
            ), timeout=timeout)
            await process.wait()
            return ("".join(out_buf), "".join(err_buf),
                    process.returncode, False)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
            return ("".join(out_buf), "".join(err_buf), -1, True)

    async def _execute_code(self, code: str, timeout: int) -> Dict[str, Any]:
        """
        Execute Python code in subprocess with isolation.
        
        Creates a temporary Python file, executes it in a subprocess,
        and captures all output and exit status.
        """
        import time
        import uuid
        start_time = time.time()

        # Temp execution scripts live in a hidden .exec/ subfolder of the
        # work_dir so the user-visible workspace only contains real
        # generated files (script_<timestamp>.py used to clutter the
        # project folder — sandbox/, project dirs).
        exec_dir = self.work_dir / ".exec"
        exec_dir.mkdir(exist_ok=True)
        # Unique per execution: int(start_time) alone collided for
        # concurrent tasks started within the same second — all workers
        # then executed the LAST written script (caught by the edge-case
        # pass; the uuid fragment keeps names debuggable AND unique).
        script_file = exec_dir / f"script_{int(start_time)}_{uuid.uuid4().hex[:8]}.py"
        script_file.write_text(code, encoding='utf-8')
        self._temp_files.add(script_file)
        
        # Track files before execution
        files_before = set(self.work_dir.glob("*"))
        
        await self.send_progress({
            "stage": "executing",
            "script": str(script_file),
            "timeout": timeout
        })
        
        try:
            # Execute using subprocess — output STREAMS to the UI while
            # the program runs (execution.output events per line).
            stdout_str, stderr_str, exit_code, timed_out = (
                await self._exec_streamed(
                    [sys.executable, "-u", str(script_file)],
                    cwd=self.work_dir,
                    env=self._get_execution_env(),
                    timeout=timeout))
            stdout = stdout_str.encode("utf-8", errors="replace")
            stderr = stderr_str.encode("utf-8", errors="replace")

            if timed_out:
                # Kill happened inside _exec_streamed; report + notify.
                stderr_str = stderr_str.rstrip() + (
                    f"\nExecution timed out after {timeout} seconds"
                    if stderr_str else
                    f"Execution timed out after {timeout} seconds")
                stderr = stderr_str.encode("utf-8", errors="replace")
                await self.send_event("brain.timeout", {
                    "brain": self.name,
                    "timeout": timeout,
                    "script": str(script_file)
                }, priority=Priority.HIGH)
        
        except Exception as e:
            # Execution setup failed
            end_time = time.time()
            await self.send_event("brain.execution_error", {
                "brain": self.name,
                "error": str(e),
                "script": str(script_file)
            }, priority=Priority.HIGH)
            
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -2,
                "execution_time": end_time - start_time,
                "files_created": [],
                "success": False,
                "error": str(e),
                "timed_out": False
            }
        
        end_time = time.time()
        
        # Check for new files created during execution
        files_after = set(self.work_dir.glob("*"))
        new_files = [str(f.name) for f in files_after - files_before 
                    if f != script_file]
        
        # Decode output
        stdout_str = stdout.decode('utf-8', errors='replace')
        stderr_str = stderr.decode('utf-8', errors='replace')
        
        # Determine success
        success = exit_code == 0 and not timed_out
        
        result = {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": exit_code,
            "execution_time": end_time - start_time,
            "files_created": new_files,
            "success": success,
            "timed_out": timed_out
        }
        
        # Add error field if execution failed
        if not success:
            if timed_out:
                result["error"] = f"Execution timed out after {timeout} seconds"
            elif exit_code != 0:
                result["error"] = f"Process exited with code {exit_code}"
                if stderr_str:
                    result["error"] += f": {stderr_str}"
        
        await self.send_progress({
            "stage": "completed",
            "success": success,
            "exit_code": exit_code,
            "execution_time": end_time - start_time
        })
        
        return result
    
    def _get_execution_env(self) -> Dict[str, str]:
        """
        Get environment variables for code execution.

        Inherits current environment but strips sensitive keys/prefixes
        so generated code can never exfiltrate API tokens, SSH agent
        sockets, or internal service credentials.
        """
        env = os.environ.copy()

        # --- Strip sensitive variables ---
        for key in list(env.keys()):
            if key in self._SENSITIVE_ENV_KEYS:
                del env[key]
            elif any(key.startswith(p) for p in self._SENSITIVE_ENV_PREFIXES):
                del env[key]

        # Add Python path for any modules we want accessible
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{self.work_dir}:{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = str(self.work_dir)

        # Disable bytecode generation for cleaner temp dir
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        # Set UTF-8 encoding for consistent output
        env["PYTHONIOENCODING"] = "utf-8"

        return env
    
    async def cleanup(self) -> None:
        """Clean up temporary files, preview servers, and working directory."""
        # Kill preview server if running
        if self._preview_process and self._preview_process.returncode is None:
            try:
                self._preview_process.terminate()
                await asyncio.wait_for(self._preview_process.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    self._preview_process.kill()
                except ProcessLookupError:
                    pass
            # Remove from active previews
            for port, proc in list(PythonBrain._active_previews.items()):
                if proc is self._preview_process:
                    del PythonBrain._active_previews[port]
                    break
            self._preview_process = None
        
        # Remove tracked temp files
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass  # Best effort cleanup
        
        # Try to remove work directory if empty
        try:
            if self.work_dir.exists():
                remaining_files = list(self.work_dir.glob("*"))
                if not remaining_files:
                    exec_dir = self.work_dir / ".exec"
                    if exec_dir.is_dir():
                        try:
                            exec_dir.rmdir()
                        except Exception:
                            pass
                    self.work_dir.rmdir()
                else:
                    # Log remaining files for debugging
                    await self.send_event("brain.cleanup_warning", {
                        "brain": self.name,
                        "remaining_files": [str(f) for f in remaining_files],
                        "work_dir": str(self.work_dir)
                    }, priority=Priority.LOW)
        except Exception:
            pass  # Best effort cleanup
        
        self._temp_files.clear()
    
    async def handle_message(self, message: BusMessage) -> None:
        """Handle non-task messages specific to Python brain."""
        if message.type == "query" and message.payload.get("type") == "capabilities":
            # Respond with brain capabilities
            await self.send_result({
                "brain_type": "python",
                "python_version": sys.version,
                "python_executable": sys.executable,
                "work_directory": str(self.work_dir),
                "default_timeout": self.timeout,
                "features": [
                    "code_execution",
                    "file_creation",
                    "subprocess_isolation",
                    "timeout_protection",
                    "output_capture"
                ]
            }, message.id)
        
        else:
            # Let base class handle other messages
            await super().handle_message(message)
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed Python brain status."""
        base_status = super().get_status()
        return {
            **base_status,
            "brain_type": "python",
            "python_version": sys.version_info[:3],
            "work_dir": str(self.work_dir),
            "timeout": self.timeout,
            "temp_files_count": len(self._temp_files)
        }
