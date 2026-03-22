"""PythonBrain - Python code execution brain with subprocess isolation."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

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
                 timeout: int = 30, work_dir: Path = None):
        """
        Initialize Python execution brain.
        
        Args:
            name: Brain identifier
            bus: MessageBus instance
            workspace: Workspace this brain belongs to
            timeout: Default execution timeout in seconds
            work_dir: Working directory for code execution
        """
        super().__init__(name, bus, workspace)
        self.timeout = timeout
        self.work_dir = Path(work_dir or tempfile.gettempdir()) / f"bigbrain_python_{name}"
        self.work_dir.mkdir(exist_ok=True, parents=True)
        
        # Track created temp files for cleanup
        self._temp_files: set[Path] = set()
    
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
        
        if task_type != "execute_code":
            raise ValueError(f"Unknown task type: {task_type}")
        
        code = payload.get("code")
        if not code:
            raise ValueError("No code provided in task")
        
        # Use task-specific timeout if provided
        timeout = payload.get("timeout", self.timeout)
        
        # Create any additional files requested
        await self._create_task_files(payload.get("files", {}))
        
        # Execute the code
        return await self._execute_code(code, timeout)
    
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
        """Clean up temporary files and working directory."""
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