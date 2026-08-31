"""
Request Validation Module
Prevents quota waste through provenance validation.

Standard usage pattern - NEVER call models without validation:

    from request_validation import ValidatedModelCall
    
    # Test mode (no quota consumed):
    response = ValidatedModelCall.generate_content(
        origin_agent="Architect",
        model="gemini-2.5-pro",
        prompt="...",
        estimated_tokens=1500,
        dry_run=True  # <-- Set to True for testing
    )
    
    # Production mode (quota consumed):
    response = ValidatedModelCall.generate_content(
        origin_agent="Architect",
        model="gemini-2.5-pro",
        prompt="...",
        estimated_tokens=1500,
        dry_run=False  # <-- Only when proven legitimate
    )
"""

from .provenance_validator import (
    ProvenanceValidator,
    ProvenanceLevel,
    RequestContext,
    validate_before_api_call,
    get_validator,
)

from .validated_model_call import (
    ValidatedModelCall,
    ValidationTracker,
    get_validation_tracker,
)

__all__ = [
    "ProvenanceValidator",
    "ProvenanceLevel",
    "RequestContext",
    "ValidatedModelCall",
    "ValidationTracker",
    "validate_before_api_call",
    "get_validator",
    "get_validation_tracker",
]
