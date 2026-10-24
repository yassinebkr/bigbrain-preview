"""V1 Schema Validator - Pydantic schema validation for BigBrain."""

import time
from typing import Any, Dict, Type, Union

from pydantic import BaseModel, ValidationError

from .pipeline import BaseVerifier, VerificationLevel, VerificationResult


class TaskResultSchema(BaseModel):
    """Default schema for task results."""
    success: bool
    data: Any = None
    error: str = None
    execution_time: float = None
    
    class Config:
        extra = "allow"  # Allow additional fields


class CodeExecutionSchema(BaseModel):
    """Schema for Python brain code execution results."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    files_created: list[str] = []
    timed_out: bool = False
    error: str = None
    
    class Config:
        extra = "allow"


class ResearchResultSchema(BaseModel):
    """Schema for research brain results."""
    success: bool
    query: str
    sources: list[Dict[str, Any]] = []
    summary: str = ""
    confidence: float | None = None
    search_time: float = 0.0
    error: str | None = None
    
    class Config:
        extra = "allow"


class SchemaValidator(BaseVerifier):
    """
    V1 Schema Validator using Pydantic.
    
    Validates that brain outputs conform to expected structured schemas.
    This catches type errors, missing required fields, and malformed data
    before results are processed by other components.
    
    Key Features:
    - Pydantic-based validation with detailed error messages
    - Multiple predefined schemas for common brain types
    - Support for custom schemas per task
    - Graceful handling of validation errors
    - Performance optimized for high throughput
    """
    
    def __init__(self):
        """Initialize schema validator with built-in schemas."""
        self.schemas = {
            "task_result": TaskResultSchema,
            "code_execution": CodeExecutionSchema, 
            "research_result": ResearchResultSchema
        }
    
    async def verify(self, data: Any, context: Dict[str, Any] = None) -> VerificationResult:
        """
        Validate data against appropriate Pydantic schema.
        
        Args:
            data: Data to validate (typically a dict)
            context: Context containing schema hints
            
        Returns:
            VerificationResult with validation pass/fail
        """
        start_time = time.time()
        context = context or {}
        
        try:
            # Determine which schema to use
            schema_class = self._get_schema_for_context(context)
            
            if not schema_class:
                # No schema specified - do basic structure validation
                return await self._validate_basic_structure(data, start_time)
            
            # Validate against specific schema
            try:
                # Parse and validate using Pydantic
                validated_instance = schema_class.model_validate(data)
                
                end_time = time.time()
                return VerificationResult(
                    level=VerificationLevel.V1_SCHEMA,
                    passed=True,
                    score=1.0,
                    message=f"Valid {schema_class.__name__}",
                    details={
                        "schema": schema_class.__name__,
                        "validated_fields": list(validated_instance.model_dump().keys()),
                        "extra_fields": self._get_extra_fields(data, validated_instance)
                    },
                    execution_time=end_time - start_time
                )
                
            except ValidationError as e:
                # Detailed validation error
                end_time = time.time()
                return VerificationResult(
                    level=VerificationLevel.V1_SCHEMA,
                    passed=False,
                    score=0.0,
                    message=f"Schema validation failed: {e}",
                    details={
                        "schema": schema_class.__name__,
                        "validation_errors": self._format_validation_errors(e),
                        "raw_data": data if isinstance(data, dict) else str(data)
                    },
                    execution_time=end_time - start_time
                )
                
        except Exception as e:
            # Unexpected error in validator
            end_time = time.time()
            return VerificationResult(
                level=VerificationLevel.V1_SCHEMA,
                passed=False,
                score=0.0,
                message=f"Validator error: {str(e)}",
                details={
                    "exception": type(e).__name__,
                    "context": context
                },
                execution_time=end_time - start_time
            )
    
    def _get_schema_for_context(self, context: Dict[str, Any]) -> Type[BaseModel]:
        """Determine appropriate schema based on context."""
        # Check for explicit schema in context
        expected_schema = context.get("expected_schema")
        if expected_schema and isinstance(expected_schema, type) and issubclass(expected_schema, BaseModel):
            return expected_schema
        
        # Infer schema from context
        verification_type = context.get("verification_type")
        if verification_type == "code_execution":
            return CodeExecutionSchema
        elif verification_type == "research":
            return ResearchResultSchema
        
        # Check task payload for hints
        task_payload = context.get("task_payload", {})
        task_type = task_payload.get("type", "")
        
        if "code" in task_type or "execute" in task_type:
            return CodeExecutionSchema
        elif "research" in task_type or "search" in task_type:
            return ResearchResultSchema
        
        # Default to generic task result
        return TaskResultSchema
    
    async def _validate_basic_structure(self, data: Any, start_time: float) -> VerificationResult:
        """Basic validation when no specific schema is available."""
        end_time = time.time()
        
        if not isinstance(data, dict):
            return VerificationResult(
                level=VerificationLevel.V1_SCHEMA,
                passed=False,
                score=0.0,
                message="Data is not a dictionary",
                details={"data_type": type(data).__name__},
                execution_time=end_time - start_time
            )
        
        # Check for required basic fields
        required_basic = ["success"]
        missing_fields = [field for field in required_basic if field not in data]
        
        if missing_fields:
            return VerificationResult(
                level=VerificationLevel.V1_SCHEMA,
                passed=False,
                score=0.5,
                message=f"Missing basic fields: {missing_fields}",
                details={
                    "missing_fields": missing_fields,
                    "available_fields": list(data.keys())
                },
                execution_time=end_time - start_time
            )
        
        # Basic structure is valid
        return VerificationResult(
            level=VerificationLevel.V1_SCHEMA,
            passed=True,
            score=0.8,  # Lower score since no specific schema
            message="Basic structure validation passed",
            details={
                "validation_type": "basic",
                "fields": list(data.keys())
            },
            execution_time=end_time - start_time
        )
    
    def _format_validation_errors(self, error: ValidationError) -> list[Dict[str, Any]]:
        """Format Pydantic validation errors for detailed reporting."""
        formatted_errors = []
        
        for err in error.errors():
            formatted_errors.append({
                "field": ".".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
                "input": err.get("input")
            })
        
        return formatted_errors
    
    def _get_extra_fields(self, original_data: Any, validated_instance: BaseModel) -> list[str]:
        """Get list of fields in original data that aren't in the schema."""
        if not isinstance(original_data, dict):
            return []
        
        validated_fields = set(validated_instance.model_dump().keys())
        original_fields = set(original_data.keys())
        
        return list(original_fields - validated_fields)
    
    def add_schema(self, name: str, schema_class: Type[BaseModel]) -> None:
        """Add a custom schema for specific validation needs."""
        self.schemas[name] = schema_class
    
    def get_available_schemas(self) -> Dict[str, str]:
        """Get list of available schemas."""
        return {name: schema.__name__ for name, schema in self.schemas.items()}
    
    @property
    def level(self) -> VerificationLevel:
        """This is a V1 (schema) verifier."""
        return VerificationLevel.V1_SCHEMA
