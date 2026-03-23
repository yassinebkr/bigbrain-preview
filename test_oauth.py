"""Test OAuth token with Claude Code stealth headers."""
import httpx
import json
from bigbrain.auth.oauth import get_api_key

key = get_api_key()
print(f"Token: {key[:20]}...")

resp = httpx.post(
    "https://api.anthropic.com/v1/messages",
    headers={
        "Authorization": f"Bearer {key}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "claude-code-20250219,oauth-2025-04-20",
        "user-agent": "claude-cli/2.1.2 (external, cli)",
        "x-app": "cli",
        "anthropic-dangerous-direct-browser-access": "true",
        "content-type": "application/json",
    },
    json={
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 50,
        "system": [
            {
                "type": "text",
                "text": "You are Claude Code, Anthropic's official CLI for Claude.",
            }
        ],
        "messages": [{"role": "user", "content": "Say hi in 5 words"}],
    },
)

print(f"Status: {resp.status_code}")
body = resp.json()
if resp.status_code == 200:
    print(f"Response: {body['content'][0]['text']}")
else:
    print(f"Error: {json.dumps(body, indent=2)}")
