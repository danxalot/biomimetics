import os
import secrets
import json
import redis
import time
from typing import Optional, Dict

class ApprovalTokenManager:
    def __init__(self, redis_host="localhost", redis_port=6379, db=0):
        try:
            self.redis = redis.Redis(host=redis_host, port=redis_port, db=db, decode_responses=True)
        except Exception:
            self.redis = None

    def generate_token(self, action: str, params: Dict, ttl: int = 600) -> str:
        """
        Generate a secure approval token for a specific action/params context.
        Stores payload in Redis with TTL.
        """
        if not self.redis:
            return "MOCK_TOKEN_REDIS_UNAVAILABLE"
            
        token = secrets.token_hex(16)
        key = f"arca:approval:{token}"
        
        payload = {
            "action": action,
            "params": params,
            "created_at": time.time()
        }
        
        self.redis.set(key, json.dumps(payload), ex=ttl)
        return token

    def validate_token(self, token: str, expected_action: str) -> Optional[Dict]:
        """
        Validate a token. 
        Returns payload if valid and matches action.
        Returns None if invalid, expired, or mismatch.
        BURNS the token (one-time use).
        """
        if not self.redis:
             if token == "MOCK_TOKEN_REDIS_UNAVAILABLE":
                 return {"mock": True}
             return None

        key = f"arca:approval:{token}"
        data = self.redis.get(key)
        
        if not data:
            return None
            
        payload = json.loads(data)
        
        if payload.get("action") != expected_action:
            return None
            
        # Burn token
        self.redis.delete(key)
        
        return payload
