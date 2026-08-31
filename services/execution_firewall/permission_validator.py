"""
ARCA Execution Firewall - Permission Validator

Enforces the architectural constraint that ONLY Genesis Chain agents
can dispatch jobs to Maintainer Agents. Direct execution attempts are
blocked and logged for audit purposes.

This is a SECURITY-CRITICAL module that must verify execution sources
before any I/O operations are performed.
"""

import os
import json
import logging
import redis
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import hashlib
import hmac
from enum import Enum

logger = logging.getLogger("execution-firewall")


class ExecutionSource(Enum):
    """Valid sources for job execution"""
    GENESIS_CHAIN = "genesis_chain"  # Only valid source
    MAINTAINER_DIRECT = "maintainer_direct"  # BLOCKED
    USER_DIRECT = "user_direct"  # BLOCKED
    UNKNOWN = "unknown"  # BLOCKED


class ExecutionFirewall:
    """
    Enforces execution permissions and audits all execution attempts.
    
    Architecture:
    - ONLY Genesis Chain can dispatch jobs to Maintainer Agents
    - All other execution attempts are blocked with ERROR logging
    - All attempts (blocked and allowed) are audit-logged to Redis
    - Request signatures verified to prevent token forgery
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        """Initialize firewall with Redis audit logging"""
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info("ExecutionFirewall connected to Redis for audit logging")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
        
        # Genesis Chain API key for request signing
        self.genesis_api_key = os.environ.get("GENESIS_CHAIN_API_KEY")
        if not self.genesis_api_key:
            logger.warning("GENESIS_CHAIN_API_KEY not set - Genesis Chain validation disabled")
        
        # Audit configuration
        self.audit_retention_days = 30
        self.blocked_attempts_key = "arca:firewall:blocked_attempts"
        self.allowed_attempts_key = "arca:firewall:allowed_attempts"
        self.execution_log_key = "arca:firewall:execution_log"
    
    def verify_execution_source(
        self, 
        request_headers: Dict[str, str],
        operation_type: str,
        request_body: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, ExecutionSource]:
        """
        Verify that execution request is from Genesis Chain.
        
        Args:
            request_headers: HTTP request headers
            operation_type: Type of operation (git, docker, etc.)
            request_body: Request body (for signature verification)
            
        Returns:
            (is_allowed, reason, source)
        """
        try:
            # 1. Identify execution source
            source = self._identify_source(request_headers)
            
            # 2. Check if source is Genesis Chain
            if source != ExecutionSource.GENESIS_CHAIN:
                reason = f"Unauthorized execution source: {source.value}"
                logger.error(f"FIREWALL BLOCKED: {reason} | Operation: {operation_type}")
                self._audit_blocked_attempt(
                    source=source,
                    operation=operation_type,
                    headers=request_headers,
                    reason=reason
                )
                return False, reason, source
            
            # 3. Verify Genesis Chain signature (if API key available)
            if self.genesis_api_key:
                signature = request_headers.get("X-Genesis-Signature")
                if not signature:
                    reason = "Missing Genesis Chain signature"
                    logger.error(f"FIREWALL BLOCKED: {reason} | Operation: {operation_type}")
                    self._audit_blocked_attempt(
                        source=source,
                        operation=operation_type,
                        headers=request_headers,
                        reason=reason
                    )
                    return False, reason, source
                
                # Verify HMAC signature
                expected_signature = self._compute_signature(request_body or {})
                if not hmac.compare_digest(signature, expected_signature):
                    reason = "Invalid Genesis Chain signature"
                    logger.error(f"FIREWALL BLOCKED: {reason} | Operation: {operation_type}")
                    self._audit_blocked_attempt(
                        source=source,
                        operation=operation_type,
                        headers=request_headers,
                        reason=reason
                    )
                    return False, reason, source
            
            # 4. All checks passed - allow execution
            logger.info(f"FIREWALL ALLOWED: Genesis Chain execution | Operation: {operation_type}")
            self._audit_allowed_attempt(
                source=source,
                operation=operation_type,
                headers=request_headers
            )
            return True, "Authorized", source
            
        except Exception as e:
            reason = f"Firewall verification error: {e}"
            logger.error(f"FIREWALL BLOCKED: {reason} | Operation: {operation_type}")
            # Log as suspicious activity
            self._audit_blocked_attempt(
                source=ExecutionSource.UNKNOWN,
                operation=operation_type,
                headers=request_headers,
                reason=reason
            )
            return False, reason, ExecutionSource.UNKNOWN
    
    def _identify_source(self, headers: Dict[str, str]) -> ExecutionSource:
        """
        Identify the source of the execution request.
        
        Genesis Chain identification:
        - Must have X-Genesis-Chain header = "true"
        - Must have X-Genesis-Signature header
        - Should have X-Genesis-Agent header
        """
        if headers.get("X-Genesis-Chain") == "true":
            return ExecutionSource.GENESIS_CHAIN
        
        # Check for user-agent indicating direct access
        user_agent = headers.get("User-Agent", "").lower()
        if "curl" in user_agent or "postman" in user_agent:
            return ExecutionSource.USER_DIRECT
        
        # Check for maintainer service direct access
        if "maintainer" in headers.get("X-Service-Name", "").lower():
            return ExecutionSource.MAINTAINER_DIRECT
        
        return ExecutionSource.UNKNOWN
    
    def _compute_signature(self, request_body: Any) -> str:
        """Compute HMAC signature for request verification"""
        if not self.genesis_api_key:
            return ""
        
        if isinstance(request_body, (bytes, bytearray)):
            message_bytes = request_body
        elif isinstance(request_body, str):
            message_bytes = request_body.encode("utf-8")
        else:
            # Fallback to legacy re-serialization (less reliable)
            message_bytes = json.dumps(request_body, sort_keys=True).encode("utf-8")
            
        return hmac.new(
            self.genesis_api_key.encode("utf-8"),
            message_bytes,
            hashlib.sha256
        ).hexdigest()
    
    def _audit_blocked_attempt(
        self,
        source: ExecutionSource,
        operation: str,
        headers: Dict[str, str],
        reason: str
    ) -> None:
        """Log blocked execution attempt to audit trail"""
        if not self.redis_client:
            return
        
        try:
            audit_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "source": source.value,
                "operation": operation,
                "reason": reason,
                "remote_addr": headers.get("X-Forwarded-For", "unknown"),
                "user_agent": headers.get("User-Agent", "unknown"),
                "status": "BLOCKED"
            }
            
            # Append to audit log
            self.redis_client.lpush(
                self.execution_log_key,
                json.dumps(audit_entry)
            )
            
            # Increment blocked attempts counter
            self.redis_client.incr(self.blocked_attempts_key)
            
            # Set expiration for audit log entries (30 days retention)
            self.redis_client.expire(
                self.execution_log_key,
                86400 * self.audit_retention_days
            )
            
            logger.warning(f"Blocked execution attempt logged: {audit_entry}")
            
        except Exception as e:
            logger.error(f"Failed to log blocked attempt to audit trail: {e}")
    
    def _audit_allowed_attempt(
        self,
        source: ExecutionSource,
        operation: str,
        headers: Dict[str, str]
    ) -> None:
        """Log allowed execution attempt to audit trail"""
        if not self.redis_client:
            return
        
        try:
            audit_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "source": source.value,
                "operation": operation,
                "genesis_agent": headers.get("X-Genesis-Agent", "unknown"),
                "remote_addr": headers.get("X-Forwarded-For", "unknown"),
                "status": "ALLOWED"
            }
            
            # Append to audit log
            self.redis_client.lpush(
                self.execution_log_key,
                json.dumps(audit_entry)
            )
            
            # Increment allowed attempts counter
            self.redis_client.incr(self.allowed_attempts_key)
            
            # Set expiration for audit log entries
            self.redis_client.expire(
                self.execution_log_key,
                86400 * self.audit_retention_days
            )
            
        except Exception as e:
            logger.error(f"Failed to log allowed attempt to audit trail: {e}")
    
    def get_audit_stats(self) -> Dict[str, Any]:
        """Get firewall audit statistics"""
        if not self.redis_client:
            return {"error": "Redis not available"}
        
        try:
            blocked_count = int(self.redis_client.get(self.blocked_attempts_key) or 0)
            allowed_count = int(self.redis_client.get(self.allowed_attempts_key) or 0)
            
            return {
                "blocked_attempts": blocked_count,
                "allowed_attempts": allowed_count,
                "total_attempts": blocked_count + allowed_count,
                "block_rate": blocked_count / (blocked_count + allowed_count) if (blocked_count + allowed_count) > 0 else 0
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_audit_log(self, limit: int = 100) -> list[Dict[str, Any]]:
        """Retrieve recent audit log entries"""
        if not self.redis_client:
            return []
        
        try:
            log_entries = self.redis_client.lrange(
                self.execution_log_key,
                0,
                limit - 1
            )
            return [json.loads(entry) for entry in log_entries]
        except Exception as e:
            logger.error(f"Failed to retrieve audit log: {e}")
            return []


# Global firewall instance
firewall = None


def initialize_firewall(redis_host: str = "localhost", redis_port: int = 6379) -> ExecutionFirewall:
    """Initialize global firewall instance"""
    global firewall
    firewall = ExecutionFirewall(redis_host=redis_host, redis_port=redis_port)
    logger.info("ExecutionFirewall initialized")
    return firewall


def get_firewall() -> Optional[ExecutionFirewall]:
    """Get global firewall instance"""
    return firewall
