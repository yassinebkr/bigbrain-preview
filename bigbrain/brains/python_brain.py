"""PythonBrain - Python code execution brain with subprocess isolation."""

import asyncio
import os
import re
import signal
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseBrain
from ..bus.message import BusMessage, Priority


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
        
        # Preview server tracking (class-level shared across instances)
        self._preview_process: Optional[asyncio.subprocess.Process] = None
    
    # Port range for preview servers (shared across all PythonBrain instances)
    PREVIEW_PORT_MIN = 3100
    PREVIEW_PORT_MAX = 3199
    # Active previews: {port: process} — class-level so all workers share
    _active_previews: Dict[int, asyncio.subprocess.Process] = {}
    
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
        
        # Build dependency content section
        dep_content = ""
        if upstream_context:
            dep_parts = []
            for source, result in upstream_context.items():
                if isinstance(result, dict):
                    code = result.get("file_content", result.get("generated_code", ""))
                    fpath = result.get("file_path", source)
                    if code:
                        dep_parts.append(f"=== {fpath} ===\n{code[:2000]}")
            if dep_parts:
                dep_content = "\n\nContent of dependency files (import from these):\n" + "\n\n".join(dep_parts)
        
        # Build file tree overview
        file_tree = "\n".join(f"  - {f['path']}: {f.get('purpose', '')}" for f in all_files)
        
        prompt = f"""Write the file `{file_path}` for the project "{project_name}".

Overall project goal: {user_request}

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

        await self.send_progress({
            "stage": "writing_file",
            "file_path": file_path,
            "purpose": purpose,
        })
        
        generated = await self.llm_provider.complete(prompt, stream=False)
        code = self._extract_code(generated)
        
        if not code.strip():
            return {
                "success": False,
                "error": f"LLM returned empty content for {file_path}",
                "stdout": "", "stderr": "", "exit_code": -1,
                "file_path": file_path,
            }
        
        # Write the file to the project directory
        project_dir = self.work_dir / project_name
        project_dir.mkdir(exist_ok=True, parents=True)
        
        # Handle subdirectories in file path
        full_path = project_dir / file_path
        full_path.parent.mkdir(exist_ok=True, parents=True)
        full_path.write_text(code, encoding="utf-8")
        # NOTE: project files are NOT tracked as temp files — they persist
        # across restarts so preview servers can be restarted and projects
        # can be inspected after completion. Only script_*.py temp files
        # are tracked for cleanup.
        
        await self.send_progress({
            "stage": "file_written",
            "file_path": file_path,
            "lines": code.count("\n") + 1,
        })
        
        return {
            "success": True,
            "file_path": file_path,
            "file_content": code,
            "lines": code.count("\n") + 1,
            "stdout": f"Written {file_path} ({code.count(chr(10)) + 1} lines)",
            "stderr": "",
            "exit_code": 0,
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
            for source, result in upstream_context.items():
                if isinstance(result, dict):
                    content = result.get("file_content", "")
                    fp = result.get("file_path", "")
                    if fp and content and fp in missing:
                        full_path = project_dir / fp
                        full_path.parent.mkdir(exist_ok=True, parents=True)
                        full_path.write_text(content, encoding="utf-8")
                        written_files[fp] = content
                        missing.remove(fp)
        
        if missing:
            return {
                "success": False,
                "error": f"Missing project files: {', '.join(missing)}",
                "stdout": "", "stderr": f"Files not found: {missing}",
                "exit_code": -1,
            }
        
        # Find the entry point (main.py, app.py, or last file in the list)
        entry_point = None
        for f in all_files:
            path = f["path"]
            if path in ("main.py", "run.py", "server.py", "app.py"):
                entry_point = path
                break
        if not entry_point:
            # Use the last Python file
            py_files = [f["path"] for f in all_files if f["path"].endswith(".py")]
            entry_point = py_files[-1] if py_files else all_files[-1]["path"]
        
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
        
        # --- Regular script: run to completion ---
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(entry_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
                env=self._get_execution_env()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                stdout = b""
                stderr = f"Execution timed out after {timeout} seconds".encode()
                exit_code = -1
                
        except Exception as e:
            end_time = time.time()
            return {
                "success": False,
                "error": str(e),
                "stdout": "", "stderr": str(e), "exit_code": -2,
                "execution_time": end_time - start_time,
            }
        
        end_time = time.time()
        stdout_str = stdout.decode("utf-8", errors="replace")
        stderr_str = stderr.decode("utf-8", errors="replace")
        success = exit_code == 0
        
        # Build project summary
        file_summary = "\n".join(f"  {f['path']} ({len(written_files.get(f['path'], ''))} chars)"
                                  for f in all_files)
        
        result = {
            "success": success,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": exit_code,
            "execution_time": end_time - start_time,
            "entry_point": entry_point,
            "project_name": project_name,
            "files_written": list(written_files.keys()),
            "project_summary": file_summary,
        }
        
        if not success:
            result["error"] = f"Entry point {entry_point} failed with exit code {exit_code}"
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
        """Start a web app as a local preview server on a free port."""
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
        
        # Patch the entry point to use our port (inject PORT env var)
        env = self._get_execution_env()
        env["PORT"] = str(port)
        env["HOST"] = "0.0.0.0"
        
        # Also try to patch common port patterns in the entry file
        entry_code = entry_path.read_text(encoding="utf-8")
        patched = False
        
        # Patch uvicorn.run(..., port=XXXX) → use env PORT
        if "uvicorn.run" in entry_code and "os.environ" not in entry_code:
            patched_code = re.sub(
                r'(uvicorn\.run\([^)]*?)port\s*=\s*\d+',
                rf'\1port=int(os.environ.get("PORT", {port}))',
                entry_code
            )
            if patched_code != entry_code:
                if "import os" not in patched_code:
                    patched_code = "import os\n" + patched_code
                entry_path.write_text(patched_code, encoding="utf-8")
                patched = True
        
        # Patch Flask/generic .run(port=XXXX)
        if not patched and ".run(" in entry_code and "os.environ" not in entry_code:
            patched_code = re.sub(
                r'(\.run\([^)]*?)port\s*=\s*\d+',
                rf'\1port=int(os.environ.get("PORT", {port}))',
                entry_code
            )
            if patched_code != entry_code:
                if "import os" not in patched_code:
                    patched_code = "import os\n" + patched_code
                entry_path.write_text(patched_code, encoding="utf-8")
                patched = True
        
        await self.send_progress({
            "stage": "starting_server",
            "port": port,
            "entry_point": str(entry_path.name),
            "patched_port": patched,
        })
        
        # Install dependencies if requirements.txt exists
        requirements = project_dir / "requirements.txt"
        if requirements.exists():
            try:
                pip_proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "pip", "install", "-q",
                    "-r", str(requirements),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(project_dir),
                )
                await asyncio.wait_for(pip_proc.communicate(), timeout=60)
            except (asyncio.TimeoutError, Exception) as e:
                pass  # Best effort — server may still work
        
        # Start the server process
        try:
            self._preview_process = await asyncio.create_subprocess_exec(
                sys.executable, str(entry_path),
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
                    code = await self._generate_initial_code(user_request, upstream_context)
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

                # Check if execution succeeded
                has_output = bool(result.get("stdout", "").strip())
                no_errors = result.get("exit_code") == 0 and not result.get("stderr", "").strip()
                
                if no_errors and has_output:
                    # Clean success with output
                    result["success"] = True
                    await self.send_progress({
                        "stage": "succeeded",
                        "attempt": attempt,
                        "success": True,
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
                                     upstream_context: dict = None) -> str:
        """Generate initial code from natural language (attempt 1)."""
        # Build context from upstream brain results (e.g., researcher findings)
        context_section = ""
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
{context_section}
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
    
    async def _execute_code(self, code: str, timeout: int) -> Dict[str, Any]:
        """
        Execute Python code in subprocess with isolation.
        
        Creates a temporary Python file, executes it in a subprocess,
        and captures all output and exit status.
        """
        import time
        start_time = time.time()
        
        # Create temporary Python file
        script_file = self.work_dir / f"script_{int(start_time)}.py"
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
            # Execute using subprocess
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(script_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.work_dir),
                env=self._get_execution_env()
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                exit_code = process.returncode
                timed_out = False
                
            except asyncio.TimeoutError:
                # Kill the process on timeout
                process.kill()
                await process.wait()
                stdout = b""
                stderr = f"Execution timed out after {timeout} seconds".encode()
                exit_code = -1
                timed_out = True
                
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
        
        Inherits current environment but can be customized for security.
        """
        env = os.environ.copy()
        
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