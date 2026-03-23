"""Anthropic OAuth — PKCE flow for Claude Pro/Max subscriptions.

Uses the same OAuth flow as OpenClaw/NanoBots to get an access token
from your Claude subscription. The token works as an API key for
the Anthropic API (scope: user:inference).

Flow:
1. Generate PKCE challenge
2. Open browser → claude.ai/oauth/authorize
3. User logs in, copies authorization code
4. Exchange code for access + refresh tokens
5. Access token used as ANTHROPIC_API_KEY
6. Auto-refresh when token expires
"""

import base64
import hashlib
import json
import os
import secrets
import time
import webbrowser
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

try:
    import httpx
    _HTTP_CLIENT = "httpx"
except ImportError:
    import urllib.request
    import urllib.parse
    _HTTP_CLIENT = "urllib"


# Anthropic OAuth constants (same as OpenClaw/pi-ai)
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
SCOPES = "org:create_api_key user:profile user:inference"

# Token storage
DEFAULT_AUTH_DIR = Path.home() / ".bigbrain" / "auth"
TOKEN_FILE = "anthropic_oauth.json"


@dataclass
class OAuthCredentials:
    """Stored OAuth credentials."""
    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp
    email: Optional[str] = None
    created_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        """Check if access token has expired (with 5 min buffer)."""
        return time.time() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if credentials exist and aren't expired."""
        return bool(self.access_token) and not self.is_expired


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(32)
    challenge_bytes = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _http_post(url: str, data: dict) -> dict:
    """Make HTTP POST request (works with or without httpx)."""
    if _HTTP_CLIENT == "httpx":
        response = httpx.post(url, json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))


def get_auth_dir() -> Path:
    """Get/create the auth directory."""
    auth_dir = Path(os.environ.get("BIGBRAIN_AUTH_DIR", str(DEFAULT_AUTH_DIR)))
    auth_dir.mkdir(parents=True, exist_ok=True)
    return auth_dir


def save_credentials(creds: OAuthCredentials) -> None:
    """Save OAuth credentials to disk."""
    path = get_auth_dir() / TOKEN_FILE
    data = asdict(creds)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Restrict file permissions on Unix
    try:
        os.chmod(path, 0o600)
    except (OSError, AttributeError):
        pass  # Windows doesn't support chmod the same way


def load_credentials() -> Optional[OAuthCredentials]:
    """Load stored OAuth credentials from disk."""
    path = get_auth_dir() / TOKEN_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return OAuthCredentials(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def delete_credentials() -> None:
    """Delete stored OAuth credentials."""
    path = get_auth_dir() / TOKEN_FILE
    if path.exists():
        path.unlink()


def login() -> OAuthCredentials:
    """
    Run the Anthropic OAuth login flow.

    Opens browser for authentication, waits for user to paste the
    authorization code, exchanges it for tokens.

    Returns:
        OAuthCredentials with access and refresh tokens
    """
    verifier, challenge = _generate_pkce()

    # Build authorization URL
    params = {
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": verifier,
    }

    if _HTTP_CLIENT == "httpx":
        query = "&".join(f"{k}={httpx.URL('').copy_with(params={k: v}).params[k]}"
                        for k, v in params.items())
    else:
        query = urllib.parse.urlencode(params)

    auth_url = f"{AUTHORIZE_URL}?{query}"

    print("\n🔑 Anthropic OAuth Login (Claude Pro/Max)")
    print("=" * 50)
    print("\nOpening browser for authentication...")
    print(f"\nIf browser doesn't open, visit:\n{auth_url}\n")

    # Try to open browser
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    # Wait for user to paste the code
    print("After signing in, you'll be redirected to a page with a code.")
    print("Copy the FULL URL or just the code and paste it here.\n")

    raw_input = input("Paste authorization code: ").strip()

    # Parse code — format is either "code#state" or just the code
    if "#" in raw_input:
        code, state = raw_input.split("#", 1)
    else:
        # Try to extract from URL
        if "code=" in raw_input:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(raw_input)
            qs = parse_qs(parsed.query) if parsed.query else parse_qs(parsed.fragment)
            code = qs.get("code", [raw_input])[0]
            state = qs.get("state", [verifier])[0]
        else:
            code = raw_input
            state = verifier

    # Exchange code for tokens
    print("\n⏳ Exchanging code for tokens...")

    token_data = _http_post(TOKEN_URL, {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "state": state,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    })

    # Calculate expiry (expires_in seconds - 5 min buffer)
    expires_at = time.time() + token_data["expires_in"] - 300

    creds = OAuthCredentials(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=expires_at,
        created_at=time.time(),
    )

    # Save to disk
    save_credentials(creds)

    print("✅ OAuth login successful! Token saved to ~/.bigbrain/auth/")
    print(f"   Token expires in {token_data['expires_in'] // 3600}h")
    print(f"   Auto-refresh enabled.\n")

    return creds


def refresh_token(creds: OAuthCredentials) -> OAuthCredentials:
    """
    Refresh an expired access token using the refresh token.

    Args:
        creds: Existing credentials with valid refresh_token

    Returns:
        Updated credentials with new access token
    """
    token_data = _http_post(TOKEN_URL, {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": creds.refresh_token,
    })

    expires_at = time.time() + token_data["expires_in"] - 300

    new_creds = OAuthCredentials(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", creds.refresh_token),
        expires_at=expires_at,
        email=creds.email,
        created_at=creds.created_at,
    )

    save_credentials(new_creds)
    return new_creds


def get_api_key() -> Optional[str]:
    """
    Get a valid Anthropic API key from stored OAuth credentials.

    Automatically refreshes if expired. Returns None if no credentials stored.
    """
    creds = load_credentials()
    if creds is None:
        return None

    if creds.is_expired:
        try:
            creds = refresh_token(creds)
        except Exception as e:
            print(f"⚠️  OAuth token refresh failed: {e}")
            print("   Run `python -m bigbrain --login` to re-authenticate.")
            return None

    return creds.access_token
