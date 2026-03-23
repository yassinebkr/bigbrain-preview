"""BusAuth - HMAC-SHA256 message authentication for BigBrain bus."""

import hashlib
import hmac
import json
import secrets
from typing import Dict, Optional

from .message import BusMessage


class BusAuth:
    """
    Manages per-brain HMAC-SHA256 authentication tokens for bus messages.
    
    Each brain gets a unique token at registration. Messages are signed
    with HMAC-SHA256(token, msg.id + sha256(json(payload))) and verified
    on receipt. Tokens are stored in memory and rotated on brain restart.
    """

    def __init__(self) -> None:
        """Initialize with empty token registry."""
        self._tokens: Dict[str, str] = {}

    def generate_token(self, brain_name: str) -> str:
        """
        Generate (or rotate) a random token for a brain.
        
        Args:
            brain_name: Unique name of the brain to register.
            
        Returns:
            The generated hex token string.
        """
        token = secrets.token_hex(32)
        self._tokens[brain_name] = token
        return token

    def get_token(self, brain_name: str) -> Optional[str]:
        """
        Retrieve the current token for a brain, if any.
        
        Args:
            brain_name: Name of the brain.
            
        Returns:
            Token string or None if the brain has no token.
        """
        return self._tokens.get(brain_name)

    def revoke_token(self, brain_name: str) -> None:
        """
        Remove a brain's token (e.g. on unregister).
        
        Args:
            brain_name: Name of the brain whose token to revoke.
        """
        self._tokens.pop(brain_name, None)

    @staticmethod
    def sign_message(token: str, msg: BusMessage) -> str:
        """
        Compute HMAC-SHA256 signature for a bus message.
        
        The signed data is ``msg.id + sha256(json(payload))``.
        
        Args:
            token: The brain's secret token.
            msg: The BusMessage to sign.
            
        Returns:
            Hex-encoded HMAC-SHA256 signature.
        """
        payload_json = json.dumps(msg.payload, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        data = msg.id + payload_hash
        return hmac.new(
            token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_message(self, brain_name: str, msg: BusMessage, signature: str) -> bool:
        """
        Verify the HMAC-SHA256 signature of a bus message.
        
        Args:
            brain_name: Name of the brain that allegedly sent the message.
            msg: The BusMessage to verify.
            signature: Hex-encoded signature to check.
            
        Returns:
            True if the signature is valid, False otherwise.
        """
        token = self._tokens.get(brain_name)
        if token is None:
            return False
        expected = self.sign_message(token, msg)
        return hmac.compare_digest(expected, signature)
