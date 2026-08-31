"""
Model Call Integration with Provenance Validation
Enforces provenance validation BEFORE any quota-consuming API calls.
This is the ONLY way to call LLM/embedding models in ARCA.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from request_validation.provenance_validator import (
    validate_before_api_call,
    RequestContext,
    ProvenanceLevel
)

logger = logging.getLogger(__name__)


class ValidatedModelCall:
    """
    Wrapper for all LLM/embedding API calls with mandatory provenance validation.
    
    CRITICAL: This is the ONLY way to call models. All other direct calls are forbidden.
    """
    
    @staticmethod
    def generate_content(
        origin_agent: str,
        model: str,
        prompt: str,
        parameters: Optional[Dict[str, Any]] = None,
        estimated_tokens: int = 0,
        dry_run: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make a generation API call with mandatory provenance validation.
        
        Args:
            origin_agent: Which agent is making this call (Architect, Engineer, etc.)
            model: Which model to use (gemini-2.5-pro, gemma3:27b, etc.)
            prompt: The prompt/message to send
            parameters: Additional parameters (temperature, etc.)
            estimated_tokens: Rough token count (3-4 chars per token)
            dry_run: If True, returns test response without consuming quota
            **kwargs: Additional arguments passed to actual API
        
        Returns:
            Response from model or cached dry-run response
            
        Example:
            ```
            response = ValidatedModelCall.generate_content(
                origin_agent="Architect",
                model="gemini-2.5-pro",
                prompt="Design a system architecture for...",
                estimated_tokens=2000,
                dry_run=False
            )
            ```
        """
        
        # Step 1: Validate request provenance BEFORE API call
        is_valid, context = validate_before_api_call(
            origin_agent=origin_agent,
            model=model,
            request_type="generate_content",
            parameters=parameters or {},
            estimated_tokens=estimated_tokens,
            dry_run=dry_run
        )
        
        if not is_valid and not dry_run:
            error_msg = f"Request validation failed: {'; '.join(context.errors)}"
            logger.error(f"BLOCKED: {error_msg}")
            logger.debug(f"Validation report: {json.dumps(context.to_dict(), indent=2, default=str)}")
            raise ValueError(error_msg)
        
        logger.info(f"Request {context.request_id} validated. Safe for quota: {context.is_safe_for_quota()}")
        
        # Step 2: Dry-run mode - return test response without consuming quota
        if dry_run:
            logger.info(f"DRY-RUN MODE: Would call {model} with {estimated_tokens} tokens")
            response = ValidatedModelCall._get_dry_run_response(model, prompt)
            logger.debug(f"Returning dry-run response for testing")
            return {
                "status": "dry_run",
                "response": response,
                "request_id": context.request_id,
                "tokens_saved": estimated_tokens,
                "model": model,
                "message": "This is a dry-run response. No quota consumed."
            }
        
        # Step 3: Real API call - quota WILL be consumed
        if not context.is_safe_for_quota():
            error_msg = f"Request not safe for quota consumption: {context.errors}"
            logger.error(f"QUOTA BLOCKED: {error_msg}")
            raise RuntimeError(error_msg)
        
        logger.info(f"Making real API call to {model} (request {context.request_id})")
        
        # Import here to avoid circular imports
        try:
            return ValidatedModelCall._make_real_api_call(
                context, model, prompt, parameters or {}, **kwargs
            )
        except Exception as e:
            logger.error(f"API call failed: {e}", exc_info=True)
            raise
    
    @staticmethod
    def embed_content(
        origin_agent: str,
        model: str,
        texts: List[str],
        estimated_tokens: int = 0,
        dry_run: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make an embedding API call with mandatory provenance validation.
        
        Args:
            origin_agent: Which agent is making this call
            model: Embedding model (gemini-embedding-001)
            texts: Texts to embed
            estimated_tokens: Estimated token count
            dry_run: If True, returns test embeddings without consuming quota
            **kwargs: Additional API arguments
        
        Returns:
            Embeddings or dry-run test embeddings
        """
        
        # Validate provenance
        is_valid, context = validate_before_api_call(
            origin_agent=origin_agent,
            model=model,
            request_type="embed_content",
            parameters={"num_texts": len(texts)},
            estimated_tokens=estimated_tokens,
            dry_run=dry_run
        )
        
        if not is_valid and not dry_run:
            error_msg = f"Embedding request validation failed: {'; '.join(context.errors)}"
            logger.error(f"BLOCKED: {error_msg}")
            raise ValueError(error_msg)
        
        logger.info(f"Embedding request {context.request_id} validated")
        
        # Dry-run mode
        if dry_run:
            logger.info(f"DRY-RUN: Would embed {len(texts)} texts with {estimated_tokens} tokens")
            return {
                "status": "dry_run",
                "embeddings": [ValidatedModelCall._get_dry_run_embedding() for _ in texts],
                "request_id": context.request_id,
                "tokens_saved": estimated_tokens,
                "model": model,
                "message": "Dry-run embeddings (zeros). No quota consumed."
            }
        
        # Real API call
        if not context.is_safe_for_quota():
            raise RuntimeError(f"Embedding not safe for quota: {context.errors}")
        
        logger.info(f"Making real embedding call to {model}")
        return ValidatedModelCall._make_real_embedding_call(context, model, texts, **kwargs)
    
    @staticmethod
    def _make_real_api_call(
        context: RequestContext,
        model: str,
        prompt: str,
        parameters: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Make actual API call to generation model"""
        
        # Route to appropriate provider
        if model.startswith("gemini"):
            return ValidatedModelCall._call_google_gemini(context, model, prompt, parameters, **kwargs)
        elif model.startswith("gemma") or model.startswith("granite"):
            return ValidatedModelCall._call_ollama(context, model, prompt, parameters, **kwargs)
        else:
            raise ValueError(f"Unknown model provider for {model}")
    
    @staticmethod
    def _call_google_gemini(
        context: RequestContext,
        model: str,
        prompt: str,
        parameters: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Call Google Gemini API"""
        try:
            import google.generativeai as genai
            
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("GOOGLE_API_KEY environment variable not set")
            
            genai.configure(api_key=api_key)
            model_obj = genai.GenerativeModel(model)
            
            response = model_obj.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(**parameters),
                **kwargs
            )
            
            # Extract actual token usage from response
            actual_tokens = 0
            if hasattr(response, 'usage_metadata'):
                actual_tokens = response.usage_metadata.output_tokens
                if hasattr(response.usage_metadata, 'input_tokens'):
                    actual_tokens += response.usage_metadata.input_tokens
            
            # Log variance between estimate and actual
            if context.estimated_tokens > 0:
                variance = actual_tokens - context.estimated_tokens
                variance_pct = (variance / context.estimated_tokens * 100) if context.estimated_tokens else 0
                logger.info(
                    f"Token variance: estimated {context.estimated_tokens}, "
                    f"actual {actual_tokens} ({variance_pct:+.1f}%)"
                )
            
            # Record actual usage
            _tracker.record_quota_usage(context.origin_agent, actual_tokens)
            
            logger.info(f"Google Gemini call successful (request {context.request_id})")
            
            return {
                "status": "success",
                "response": response.text,
                "model": model,
                "request_id": context.request_id,
                "tokens_estimated": context.estimated_tokens,
                "tokens_actual": actual_tokens,
                "tokens_variance": actual_tokens - context.estimated_tokens
            }
            
        except Exception as e:
            logger.error(f"Google Gemini API call failed: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _call_ollama(
        context: RequestContext,
        model: str,
        prompt: str,
        parameters: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Call local Ollama model"""
        try:
            import httpx
            
            ollama_base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11435")
            
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                **parameters
            }
            
            response = httpx.post(f"{ollama_base}/api/generate", json=payload, timeout=120.0)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract actual token usage from Ollama response
            actual_tokens = result.get("eval_count", 0)  # Output tokens
            if result.get("prompt_eval_count"):
                actual_tokens += result.get("prompt_eval_count", 0)  # Input tokens
            
            # Log variance
            if context.estimated_tokens > 0:
                variance = actual_tokens - context.estimated_tokens
                variance_pct = (variance / context.estimated_tokens * 100) if context.estimated_tokens else 0
                logger.info(
                    f"Token variance: estimated {context.estimated_tokens}, "
                    f"actual {actual_tokens} ({variance_pct:+.1f}%)"
                )
            
            # Record actual usage
            _tracker.record_quota_usage(context.origin_agent, actual_tokens)
            
            logger.info(f"Ollama call successful (request {context.request_id})")
            
            return {
                "status": "success",
                "response": result.get("response", ""),
                "model": model,
                "request_id": context.request_id,
                "tokens_estimated": context.estimated_tokens,
                "tokens_actual": actual_tokens,
                "tokens_variance": actual_tokens - context.estimated_tokens
            }
            
        except Exception as e:
            logger.error(f"Ollama API call failed: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _make_real_embedding_call(
        context: RequestContext,
        model: str,
        texts: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Make actual embedding API call"""
        
        if model == "gemini-embedding-001":
            return ValidatedModelCall._embed_google_gemini(context, model, texts, **kwargs)
        else:
            raise ValueError(f"Unknown embedding model: {model}")
    
    @staticmethod
    def _embed_google_gemini(
        context: RequestContext,
        model: str,
        texts: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Call Google Gemini embedding API"""
        try:
            import google.generativeai as genai
            
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("GOOGLE_API_KEY not set")
            
            genai.configure(api_key=api_key)
            
            embeddings = []
            actual_tokens = 0
            for text in texts:
                result = genai.embed_content(model="models/embedding-001", content=text)
                embeddings.append(result["embedding"])
                # Google's embedding API uses ~4 tokens per embedding plus text length
                actual_tokens += len(text.split()) + 4
            
            # Log variance
            if context.estimated_tokens > 0:
                variance = actual_tokens - context.estimated_tokens
                variance_pct = (variance / context.estimated_tokens * 100) if context.estimated_tokens else 0
                logger.info(
                    f"Embedding token variance: estimated {context.estimated_tokens}, "
                    f"actual {actual_tokens} ({variance_pct:+.1f}%)"
                )
            
            # Record actual usage
            _tracker.record_quota_usage(context.origin_agent, actual_tokens)
            
            logger.info(f"Google embedding call successful for {len(texts)} texts")
            
            return {
                "status": "success",
                "embeddings": embeddings,
                "model": model,
                "request_id": context.request_id,
                "tokens_estimated": context.estimated_tokens,
                "tokens_actual": actual_tokens,
                "tokens_variance": actual_tokens - context.estimated_tokens,
                "num_texts": len(texts)
            }
            
        except Exception as e:
            logger.error(f"Embedding call failed: {e}", exc_info=True)
            raise
    
    @staticmethod
    def _get_dry_run_response(model: str, prompt: str) -> str:
        """Generate dry-run test response"""
        return f"[DRY-RUN] Test response from {model}: Received prompt of {len(prompt)} chars"
    
    @staticmethod
    def _get_dry_run_embedding() -> List[float]:
        """Generate dry-run test embedding (zeros)"""
        # In dry-run, we use zero vectors so they don't interfere with real searches
        return [0.0] * 768  # Standard embedding dimension


# Validation tracking for testing
class ValidationTracker:
    """Track validation events for testing and debugging"""
    
    def __init__(self):
        self.validations: List[Dict[str, Any]] = []
        self.quota_used: Dict[str, int] = {}  # agent -> tokens used
        self.quota_saved: Dict[str, int] = {}  # agent -> tokens saved (dry-run)
    
    def record_validation(self, context: RequestContext):
        """Record a validation event"""
        self.validations.append({
            "request_id": context.request_id,
            "timestamp": context.timestamp.isoformat(),
            "origin_agent": context.origin_agent,
            "model": context.model,
            "provenance_level": context.provenance_level.value,
            "safe_for_quota": context.is_safe_for_quota(),
            "estimated_tokens": context.estimated_tokens,
            "errors": context.errors
        })
    
    def record_quota_usage(self, agent: str, tokens: int):
        """Track actual quota usage"""
        if agent not in self.quota_used:
            self.quota_used[agent] = 0
        self.quota_used[agent] += tokens
    
    def record_quota_saved(self, agent: str, tokens: int):
        """Track tokens saved via dry-run"""
        if agent not in self.quota_saved:
            self.quota_saved[agent] = 0
        self.quota_saved[agent] += tokens
    
    def get_summary(self) -> Dict[str, Any]:
        """Get tracking summary with actual vs estimated variance"""
        total_used = sum(self.quota_used.values())
        total_saved = sum(self.quota_saved.values())
        total_quota = total_used + total_saved
        
        return {
            "total_validations": len(self.validations),
            "quota_used_actual": self.quota_used,
            "quota_saved_dry_run": self.quota_saved,
            "total_quota_used": total_used,
            "total_quota_saved": total_saved,
            "total_quota_tracked": total_quota,
            "dry_run_efficiency_pct": (
                (total_saved / (total_quota or 1)) * 100
            ),
            "message": f"Tracked {len(self.validations)} requests. "
                      f"Consumed {total_used} tokens (real). "
                      f"Saved {total_saved} tokens (dry-run)."
        }
    
    def get_variance_report(self) -> Dict[str, Any]:
        """Get report of estimated vs actual token variance"""
        variances = []
        for val in self.validations:
            variances.append({
                "request_id": val["request_id"],
                "agent": val["origin_agent"],
                "model": val["model"],
                "estimated": val.get("estimated_tokens", 0)
            })
        
        return {
            "total_validations": len(variances),
            "note": "Actual vs estimated variance logged in each response object"
        }


# Global tracker instance
_tracker = ValidationTracker()


def get_validation_tracker() -> ValidationTracker:
    """Get global validation tracker"""
    return _tracker
