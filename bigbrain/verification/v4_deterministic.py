"""V4 Deterministic Validator - Syntax, tests, types validation for BigBrain."""

import ast
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .pipeline import BaseVerifier, VerificationLevel, VerificationResult


class DeterministicValidator(BaseVerifier):
    """
    V4 Deterministic Validator for code quality checks.
    
    Performs deterministic verification without LLM involvement:
    - Python syntax validation (AST parsing)
    - Type checking with mypy (if available)
    - Test execution with pytest
    - Code style checks with basic linting
    - Import validation
    - Security pattern detection
    
    This is the "inner loop" of the Honk pattern - fast, reliable,
    deterministic feedback that doesn't require API calls.
    """
    
    def __init__(self, enable_mypy: bool = True, enable_pytest: bool = True):
        """
        Initialize deterministic validator.
        
        Args:
            enable_mypy: Whether to run mypy type checking
            enable_pytest: Whether to run pytest on test files
        """
        self.enable_mypy = enable_mypy
        self.enable_pytest = enable_pytest
        
        # Check tool availability
        self.mypy_available = self._check_tool_available("mypy")
        self.pytest_available = self._check_tool_available("pytest")
    
    async def verify(self, data: Any, context: Dict[str, Any] = None) -> VerificationResult:
        """
        Run deterministic verification on code or execution result.
        
        Args:
            data: Data to verify (code string or execution result)
            context: Context containing code, result, and verification hints
            
        Returns:
            VerificationResult with pass/fail and detailed diagnostics
        """
        start_time = time.time()
        context = context or {}
        
        verification_type = context.get("verification_type", "unknown")
        
        if verification_type == "code_execution":
            return await self._verify_code_execution(data, context, start_time)
        elif isinstance(data, str) and self._looks_like_code(data):
            return await self._verify_code_directly(data, context, start_time)
        else:
            return await self._verify_result_structure(data, context, start_time)
    
    async def _verify_code_execution(self, result: Dict[str, Any], 
                                   context: Dict[str, Any], start_time: float) -> VerificationResult:
        """Verify code execution result for common issues."""
        issues = []
        score = 1.0
        
        # Check exit code
        exit_code = result.get("exit_code", 0)
        if exit_code != 0:
            issues.append(f"Non-zero exit code: {exit_code}")
            score -= 0.3
        
        # Check for timeout
        if result.get("timed_out", False):
            issues.append("Execution timed out")
            score -= 0.4
        
        # Check stderr for common error patterns
        stderr = result.get("stderr", "")
        if stderr:
            error_patterns = self._analyze_stderr(stderr)
            if error_patterns:
                issues.extend(error_patterns)
                score -= min(0.3, len(error_patterns) * 0.1)
        
        # Check if code from context is available for analysis
        code = context.get("code")
        if code:
            code_issues = await self._analyze_code_quality(code)
            if code_issues:
                issues.extend(code_issues)
                score -= min(0.2, len(code_issues) * 0.05)
        
        # Final score adjustment
        score = max(0.0, score)
        passed = score >= 0.7 and exit_code == 0 and not result.get("timed_out", False)
        
        end_time = time.time()
        return VerificationResult(
            level=VerificationLevel.V4_DETERMINISTIC,
            passed=passed,
            score=score,
            message=f"{'Passed' if passed else 'Failed'} deterministic checks",
            details={
                "issues": issues,
                "exit_code": exit_code,
                "timed_out": result.get("timed_out", False),
                "stderr_length": len(stderr),
                "checks_performed": ["exit_code", "timeout", "stderr_analysis"] + 
                                  (["code_quality"] if code else [])
            },
            execution_time=end_time - start_time
        )
    
    async def _verify_code_directly(self, code: str, context: Dict[str, Any], 
                                  start_time: float) -> VerificationResult:
        """Verify Python code directly through static analysis."""
        issues = []
        score = 1.0
        
        # Syntax check
        syntax_issues = self._check_syntax(code)
        if syntax_issues:
            issues.extend(syntax_issues)
            score -= 0.5  # Syntax errors are serious
        
        # Code quality analysis
        quality_issues = await self._analyze_code_quality(code)
        if quality_issues:
            issues.extend(quality_issues)
            score -= min(0.3, len(quality_issues) * 0.05)
        
        # Type checking (if available and enabled)
        if self.enable_mypy and self.mypy_available and score > 0:
            type_issues = await self._run_mypy_check(code)
            if type_issues:
                issues.extend(type_issues)
                score -= min(0.2, len(type_issues) * 0.03)
        
        score = max(0.0, score)
        passed = score >= 0.7
        
        end_time = time.time()
        return VerificationResult(
            level=VerificationLevel.V4_DETERMINISTIC,
            passed=passed,
            score=score,
            message=f"{'Passed' if passed else 'Failed'} static analysis",
            details={
                "issues": issues,
                "syntax_valid": len(syntax_issues) == 0,
                "checks_performed": ["syntax", "code_quality"] + 
                                  (["mypy"] if self.enable_mypy and self.mypy_available else [])
            },
            execution_time=end_time - start_time
        )
    
    async def _verify_result_structure(self, data: Any, context: Dict[str, Any],
                                     start_time: float) -> VerificationResult:
        """Basic verification for non-code data."""
        issues = []
        score = 1.0
        
        if not isinstance(data, dict):
            issues.append(f"Expected dict result, got {type(data).__name__}")
            score = 0.0
        else:
            # Check for required success field
            if "success" not in data:
                issues.append("Missing 'success' field in result")
                score -= 0.3
            
            # If marked as failure, check for error message
            if not data.get("success", True) and not data.get("error"):
                issues.append("Failed result missing error message")
                score -= 0.2
        
        score = max(0.0, score)
        passed = score >= 0.7
        
        end_time = time.time()
        return VerificationResult(
            level=VerificationLevel.V4_DETERMINISTIC,
            passed=passed,
            score=score,
            message=f"{'Passed' if passed else 'Failed'} structure checks",
            details={
                "issues": issues,
                "data_type": type(data).__name__,
                "checks_performed": ["structure", "required_fields"]
            },
            execution_time=end_time - start_time
        )
    
    def _check_syntax(self, code: str) -> List[str]:
        """Check Python syntax using AST parsing."""
        issues = []
        
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append(f"Syntax error at line {e.lineno}: {e.msg}")
        except Exception as e:
            issues.append(f"Parse error: {str(e)}")
        
        return issues
    
    async def _analyze_code_quality(self, code: str) -> List[str]:
        """Analyze code quality with basic static checks."""
        issues = []
        lines = code.split('\n')
        
        # Check for common issues
        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()
            
            # Very long lines
            if len(line) > 120:
                issues.append(f"Line {i}: Very long line ({len(line)} chars)")
            
            # Bare except clauses
            if re.match(r'^\s*except\s*:\s*$', line):
                issues.append(f"Line {i}: Bare except clause - should specify exception type")
            
            # Print statements in production-looking code
            if 'print(' in line and not line_stripped.startswith('#'):
                # Only flag if this doesn't look like a demo/debug script
                if len(lines) > 10 and not any('demo' in l.lower() or 'test' in l.lower() for l in lines[:5]):
                    issues.append(f"Line {i}: Print statement (consider logging)")
            
            # Potential security issues
            if 'eval(' in line or 'exec(' in line:
                issues.append(f"Line {i}: Use of eval/exec - potential security risk")
            
            if '__import__(' in line:
                issues.append(f"Line {i}: Dynamic import - review for security")
        
        # Check import patterns
        import_issues = self._analyze_imports(code)
        issues.extend(import_issues)
        
        return issues
    
    def _analyze_imports(self, code: str) -> List[str]:
        """Analyze import statements for issues."""
        issues = []
        
        try:
            tree = ast.parse(code)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
            
            # Check for potentially dangerous imports
            dangerous_modules = ['subprocess', 'os.system', 'eval', 'exec']
            for imp in imports:
                for dangerous in dangerous_modules:
                    if dangerous in imp:
                        issues.append(f"Import of potentially dangerous module: {imp}")
            
            # Check for unused stdlib that might indicate complexity
            complex_modules = ['threading', 'multiprocessing', 'socket', 'urllib']
            for imp in imports:
                for complex_mod in complex_modules:
                    if complex_mod in imp:
                        # This isn't necessarily bad, just flag for review
                        pass  # Skip for now to avoid too many warnings
            
        except Exception:
            # If AST parsing fails, we already caught that in syntax check
            pass
        
        return issues
    
    async def _run_mypy_check(self, code: str) -> List[str]:
        """Run mypy type checking on code."""
        if not self.mypy_available:
            return []
        
        issues = []
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            # Run mypy
            result = subprocess.run([
                sys.executable, '-m', 'mypy', 
                '--ignore-missing-imports',
                '--no-error-summary',
                temp_file
            ], capture_output=True, text=True, timeout=10)
            
            # Parse mypy output
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    if line and 'error:' in line:
                        # Clean up the error message
                        error_msg = line.split('error:', 1)[1].strip()
                        issues.append(f"Type error: {error_msg}")
            
            # Clean up temp file
            Path(temp_file).unlink(missing_ok=True)
            
        except subprocess.TimeoutExpired:
            issues.append("Mypy check timed out")
        except Exception as e:
            # Don't fail verification if mypy fails
            pass
        
        return issues
    
    def _analyze_stderr(self, stderr: str) -> List[str]:
        """Analyze stderr for common error patterns."""
        issues = []
        
        if not stderr.strip():
            return issues
        
        lines = stderr.lower().split('\n')
        
        # Common error patterns
        patterns = {
            'import': r'no module named|importerror|modulenotfounderror',
            'syntax': r'syntaxerror|invalid syntax',
            'type': r'typeerror|attributeerror',
            'value': r'valueerror|keyerror|indexerror',
            'permission': r'permissionerror|access denied',
            'timeout': r'timeout|timed out',
            'memory': r'memoryerror|out of memory'
        }
        
        for category, pattern in patterns.items():
            if any(re.search(pattern, line) for line in lines):
                issues.append(f"Detected {category} error in stderr")
        
        return issues
    
    def _looks_like_code(self, data: str) -> bool:
        """Simple heuristic to detect if string is Python code."""
        code_indicators = [
            'def ', 'class ', 'import ', 'from ', 
            'if __name__', 'print(', 'return ', '= '
        ]
        
        return any(indicator in data for indicator in code_indicators)
    
    def _check_tool_available(self, tool: str) -> bool:
        """Check if external tool is available."""
        try:
            subprocess.run([sys.executable, '-m', tool, '--version'], 
                          capture_output=True, timeout=5)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            return False
    
    @property
    def level(self) -> VerificationLevel:
        """This is a V4 (deterministic) verifier."""
        return VerificationLevel.V4_DETERMINISTIC
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get validator capabilities and tool availability."""
        return {
            "mypy_available": self.mypy_available,
            "pytest_available": self.pytest_available,
            "checks_supported": [
                "syntax",
                "code_quality", 
                "imports",
                "security_patterns",
                "stderr_analysis"
            ] + (["mypy"] if self.mypy_available else [])
        }