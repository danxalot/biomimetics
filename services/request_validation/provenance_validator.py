"""
Request Provenance Validation Framework
Prevents quota waste by validating request legitimacy before API calls.
Implements dry-run capability for testing without consuming quota.

Key Principle: NO API CALL without proven legitimate origin
"""

import os
import json
import uuid
import hmac
import hashlib
from typing import Dict, Any, Optional, Literal, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ProvenanceLevel(Enum):
    """Validation levels for request legitimacy"""
    UNVALIDATED = "unvalidated"  # No verification - DO NOT CALL QUOTA
    DRY_RUN = "dry_run"          # Testing mode - can trace but not consume quota
    VALIDATED = "validated"      # Verified origin - safe for quota consumption
    SYSTEM = "system"            # System initialization - special case
    EMERGENCY = "emergency"      # Error recovery - use cautiously


@dataclass
class RequestContext:
    """Complete context of a request including provenance"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Origin validation
    origin_agent: Optional[str] = None           # Which agent created this request
    origin_system: str = "arca"                  # System that created it
    provenance_level: ProvenanceLevel = ProvenanceLevel.UNVALIDATED
    provenance_signature: Optional[str] = None   # Cryptographic proof of legitimacy
    
    # Request details
    request_type: str = "unknown"                # generate_content, embed, etc.
    model: Optional[str] = None                  # Which model to call
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Dry-run mode
    dry_run: bool = False                        # Test without consuming quota
    dry_run_result: Optional[str] = None         # Cached result for testing
    
    # Quota tracking
    estimated_tokens: int = 0                    # Estimated tokens this will use
    quota_budget_remaining: Optional[int] = None # Tokens available
    
    # Audit trail
    validation_chain: list = field(default_factory=list)  # Validation steps taken
    errors: list = field(default_factory=list)  # Any errors during validation
    
    def add_validation_step(self, step: str, result: bool, details: str = ""):
        """Record a validation step in the chain"""
        self.validation_chain.append({
            "step": step,
            "result": result,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def is_safe_for_quota(self) -> bool:
        """Check if this request can safely consume quota"""
        return (
            self.provenance_level in [
                ProvenanceLevel.VALIDATED,
                ProvenanceLevel.SYSTEM,
            ]
            and not self.dry_run
            and len(self.errors) == 0
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['provenance_level'] = self.provenance_level.value
        return data


class ProvenanceValidator:
    """
    Validates request provenance before API calls.
    Implements multi-stage validation to prevent quota waste.
    """
    
    def __init__(self, secret_key: str = None):
        """
        Initialize validator with secret key for signature verification
        
        Args:
            secret_key: Secret for HMAC signatures (from env if not provided)
        """
        self.secret_key = secret_key or os.environ.get("ARCA_PROVENANCE_SECRET")
        if not self.secret_key:
            logger.warning("No provenance secret configured - signature validation disabled")
        
        # Known legitimate origins
        self.trusted_agents = {
            "Architect",
            "Planner", 
            "Engineer",
            "Reviewer",
            "Serena",
            "DockerOps",
            "GitOps",
            "SecurityOps",
            "FileOps",
            "Genesis"
        }
        
        # Request quotas (tokens/minute per agent)
        self.agent_quotas = {
            "Architect": 20000,   # Can use up to 20k tokens/min
            "Planner": 10000,
            "Engineer": 15000,
            "Reviewer": 5000,
            "Serena": 3000,
            "Genesis": 50000,     # System initialization
        }
        
        self.request_history = {}  # Track requests for rate limiting
    
    def validate_request(self, context: RequestContext) -> Tuple[bool, str]:
        """
        Multi-stage validation of request provenance.
        
        Returns:
            (is_valid, reason)
        """
        logger.info(f"Starting validation for request {context.request_id}")
        
        # Stage 1: Basic sanity checks
        if not self._validate_basic(context):
            return False, "Failed basic validation"
        
        # Stage 2: Origin validation
        if not self._validate_origin(context):
            return False, "Failed origin validation"
        
        # Stage 3: Signature validation (if available)
        if self.secret_key and not self._validate_signature(context):
            return False, "Failed signature validation"
        
        # Stage 4: Quota check
        if not self._validate_quota(context):
            return False, "Quota exceeded or insufficient budget"
        
        # Stage 5: Model availability
        if not self._validate_model(context):
            return False, "Model not available or invalid"
        
        logger.info(f"Request {context.request_id} validation PASSED at level {context.provenance_level.value}")
        return True, "Validation successful"
    
    def _validate_basic(self, context: RequestContext) -> bool:
        """Validate basic request properties"""
        context.add_validation_step("basic_sanity", True)
        
        if not context.request_id:
            context.add_validation_step("request_id", False, "Missing request ID")
            context.errors.append("Request ID required")
            return False
        
        if not context.model:
            context.add_validation_step("model_specified", False, "No model specified")
            context.errors.append("Model must be specified")
            return False
        
        if context.timestamp > datetime.utcnow() + timedelta(seconds=300):
            context.add_validation_step("timestamp_valid", False, "Timestamp too far in future")
            context.errors.append("Timestamp cannot be more than 5 minutes in future")
            return False
        
        context.add_validation_step("basic_sanity", True)
        return True
    
    def _validate_origin(self, context: RequestContext) -> bool:
        """Validate request origin"""
        if not context.origin_agent:
            context.add_validation_step("origin_agent", False, "No origin agent specified")
            context.provenance_level = ProvenanceLevel.UNVALIDATED
            context.errors.append("Cannot validate request without origin agent")
            return False
        
        if context.origin_agent not in self.trusted_agents:
            context.add_validation_step("trusted_agent", False, f"Unknown agent: {context.origin_agent}")
            context.provenance_level = ProvenanceLevel.UNVALIDATED
            context.errors.append(f"Agent {context.origin_agent} not in trusted list")
            return False
        
        context.add_validation_step("origin_agent", True, f"Trusted: {context.origin_agent}")
        context.provenance_level = ProvenanceLevel.VALIDATED
        return True
    
    def _validate_signature(self, context: RequestContext) -> bool:
        """Validate cryptographic signature"""
        if not self.secret_key:
            context.add_validation_step("signature_validation", True, "Skipped - no secret configured")
            return True
        
        if not context.provenance_signature:
            context.add_validation_step("signature_present", False, "No signature provided")
            context.errors.append("Signature required for verified requests")
            return False
        
        # Recreate expected signature
        expected_sig = self._create_signature(context)
        
        if not hmac.compare_digest(context.provenance_signature, expected_sig):
            context.add_validation_step("signature_valid", False, "Signature mismatch")
            context.errors.append("Invalid provenance signature")
            return False
        
        context.add_validation_step("signature_valid", True)
        return True
    
    def _validate_quota(self, context: RequestContext) -> bool:
        """Validate quota availability"""
        if context.dry_run:
            context.add_validation_step("quota_check", True, "Skipped - dry run mode")
            return True
        
        if not context.origin_agent:
            context.add_validation_step("quota_check", False, "Cannot check quota without origin")
            return False
        
        quota = self.agent_quotas.get(context.origin_agent, 5000)
        
        if context.estimated_tokens > quota:
            context.add_validation_step("quota_check", False, f"Request exceeds agent quota: {context.estimated_tokens} > {quota}")
            context.errors.append(f"Request would exceed quota: {context.estimated_tokens} tokens > {quota} tokens")
            return False
        
        context.add_validation_step("quota_check", True, f"Within quota: {context.estimated_tokens}/{quota}")
        return True
    
    def _validate_model(self, context: RequestContext) -> bool:
        """Validate model availability"""
        valid_models = {
            # Google models
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash-exp",
            "learnlm-2.0-flash-experimental",
            "gemini-embedding-001",
            # Local models
            "gemma3:27b",
            "gemma3:4b",
            "granite-guardian:2b",
        }
        
        if context.model not in valid_models:
            context.add_validation_step("model_valid", False, f"Unknown model: {context.model}")
            context.errors.append(f"Model {context.model} not in valid models list")
            return False
        
        context.add_validation_step("model_valid", True, f"Model recognized: {context.model}")
        return True
    
    def _create_signature(self, context: RequestContext) -> str:
        """Create HMAC signature for request"""
        if not self.secret_key:
            return ""
        
        payload = f"{context.request_id}:{context.origin_agent}:{context.model}:{context.timestamp.isoformat()}"
        signature = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def create_validated_context(self, 
                                origin_agent: str,
                                model: str,
                                request_type: str,
                                parameters: Dict[str, Any],
                                estimated_tokens: int = 0,
                                dry_run: bool = False) -> RequestContext:
        """
        Create and validate a request context.
        
        Args:
            origin_agent: Which agent is making this request
            model: Which model to call
            request_type: Type of request (generate_content, embed, etc.)
            parameters: Request parameters
            estimated_tokens: Estimated tokens this will use
            dry_run: Whether to run in dry-run mode (no quota consumed)
        
        Returns:
            RequestContext with validation results
        """
        context = RequestContext(
            origin_agent=origin_agent,
            model=model,
            request_type=request_type,
            parameters=parameters,
            estimated_tokens=estimated_tokens,
            dry_run=dry_run,
            provenance_signature=self._create_signature(RequestContext(
                origin_agent=origin_agent,
                model=model
            ))
        )
        
        is_valid, reason = self.validate_request(context)
        
        logger.info(f"Request {context.request_id}: {reason}")
        logger.debug(f"Validation chain: {context.validation_chain}")
        
        return context
    
    def get_validation_report(self, context: RequestContext) -> Dict[str, Any]:
        """Generate a human-readable validation report"""
        return {
            "request_id": context.request_id,
            "provenance_level": context.provenance_level.value,
            "safe_for_quota": context.is_safe_for_quota(),
            "validation_steps": context.validation_chain,
            "errors": context.errors,
            "origin_agent": context.origin_agent,
            "model": context.model,
            "dry_run": context.dry_run,
            "estimated_tokens": context.estimated_tokens,
            "timestamp": context.timestamp.isoformat()
        }


# Global validator instance
_validator_instance: Optional[ProvenanceValidator] = None


def get_validator() -> ProvenanceValidator:
    """Get or create global validator instance"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ProvenanceValidator()
    return _validator_instance


def validate_before_api_call(origin_agent: str,
                            model: str,
                            request_type: str,
                            parameters: Dict[str, Any],
                            estimated_tokens: int = 0,
                            dry_run: bool = False) -> Tuple[bool, RequestContext]:
    """
    Standard function to validate before ANY API call.
    
    USAGE PATTERN:
    ```
    is_valid, context = validate_before_api_call(
        origin_agent="Architect",
        model="gemini-2.5-pro",
        request_type="generate_content",
        parameters={"prompt": "..."},
        estimated_tokens=1500,
        dry_run=False  # Set True for testing
    )
    
    if not is_valid:
        logger.error(f"Request not valid: {context.errors}")
        raise ValueError(f"Invalid request: {context.errors}")
    
    # ONLY NOW can we make the API call
    if context.dry_run:
        return cached_test_response  # Use cached response
    else:
        return actual_api_call()
    ```
    """
    validator = get_validator()
    context = validator.create_validated_context(
        origin_agent=origin_agent,
        model=model,
        request_type=request_type,
        parameters=parameters,
        estimated_tokens=estimated_tokens,
        dry_run=dry_run
    )
    
    is_valid = context.is_safe_for_quota() or (dry_run and context.provenance_level != ProvenanceLevel.UNVALIDATED)
    
    return is_valid, context
