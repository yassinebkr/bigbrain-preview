"""Risk classification system for BigBrain operations."""

import logging
import re
from enum import Enum
from typing import Any, Dict

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels for BigBrain operations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def classify_risk(payload: Dict[str, Any]) -> RiskLevel:
    """
    Classify the risk level of a task payload.
    
    Classification rules:
    - LOW: read-only operations, code generation without execution
    - MEDIUM: file writes, code execution in sandbox
    - HIGH: network access, system commands, file deletion
    
    Args:
        payload: Task payload to classify
        
    Returns:
        RiskLevel enum value
    """
    if not payload:
        return RiskLevel.LOW
    
    task_type = payload.get("type", "")
    
    # HIGH risk operations
    high_risk_patterns = [
        # Network operations
        r"network", r"http", r"url", r"download", r"upload", r"api", r"request",
        # System operations
        r"system", r"shell", r"command", r"subprocess", r"exec",
        # File operations that modify system
        r"delete", r"remove", r"unlink", r"rmdir", r"rm\s",
        # Security-sensitive operations
        r"sudo", r"admin", r"root", r"password", r"auth", r"token",
        # Process operations
        r"kill", r"terminate", r"signal"
    ]
    
    # MEDIUM risk operations
    medium_risk_patterns = [
        # File writing
        r"write", r"create", r"modify", r"edit", r"save",
        # Code execution
        r"execute", r"run", r"compile", r"build",
        # Database operations
        r"database", r"sql", r"db", r"insert", r"update"
    ]
    
    # Check task type against patterns
    risk_indicators = []
    
    # Analyze task type
    if task_type:
        risk_indicators.append(task_type.lower())
    
    # Analyze payload content
    content_to_check = []
    for key, value in payload.items():
        if isinstance(value, str):
            content_to_check.append(value.lower())
        elif isinstance(value, dict):
            # Recursively check nested dictionaries
            nested_risk = classify_risk(value)
            if nested_risk == RiskLevel.HIGH:
                return RiskLevel.HIGH
            elif nested_risk == RiskLevel.MEDIUM:
                risk_indicators.append("nested_medium_risk")
    
    # Join all text for pattern matching
    text_content = " ".join(risk_indicators + content_to_check)
    
    # Check for HIGH risk patterns
    for pattern in high_risk_patterns:
        if re.search(pattern, text_content, re.IGNORECASE):
            logger.debug("HIGH risk detected: pattern '%s' in payload", pattern)
            return RiskLevel.HIGH
    
    # Check for MEDIUM risk patterns
    for pattern in medium_risk_patterns:
        if re.search(pattern, text_content, re.IGNORECASE):
            logger.debug("MEDIUM risk detected: pattern '%s' in payload", pattern)
            return RiskLevel.MEDIUM
    
    # Default to LOW risk for read-only operations
    logger.debug("LOW risk: no risky patterns detected")
    return RiskLevel.LOW


def get_risk_description(risk_level: RiskLevel) -> str:
    """Get human-readable description of risk level."""
    descriptions = {
        RiskLevel.LOW: "Read-only operations, safe code generation",
        RiskLevel.MEDIUM: "File writes, sandboxed code execution", 
        RiskLevel.HIGH: "Network access, system commands, file deletion"
    }
    return descriptions.get(risk_level, "Unknown risk level")


def should_require_approval(risk_level: RiskLevel) -> bool:
    """Determine if a risk level should require human approval."""
    return risk_level == RiskLevel.HIGH


def get_recommended_timeout(risk_level: RiskLevel) -> int:
    """Get recommended timeout in seconds based on risk level."""
    timeouts = {
        RiskLevel.LOW: 30,     # Quick operations
        RiskLevel.MEDIUM: 60,  # File operations, code execution
        RiskLevel.HIGH: 120    # Network operations, complex tasks
    }
    return timeouts.get(risk_level, 60)