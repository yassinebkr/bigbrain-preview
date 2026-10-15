"""BigBrain CLI — argument parsing and auth commands.

Extracted from ``__main__.py`` (Phase 2 refactor): argparse flags, the
``--login`` / ``--logout`` / ``--auth-status`` OAuth commands, and the
UI-mode selection. The system class lives in ``system.py``.
"""

import sys
from pathlib import Path

from .system import AIOHTTP_AVAILABLE, TEXTUAL_AVAILABLE, BigBrainSystem


async def main() -> None:
    """Main entry point for BigBrain."""
    import argparse
    import time
    
    parser = argparse.ArgumentParser(description="BigBrain - Multi-Brain AI Agent System")
    parser.add_argument("--workspace", default="default", help="Workspace name (default: default)")
    parser.add_argument("--log-dir", default="logs", help="Log directory (default: logs)")
    parser.add_argument("--simple", action="store_true", default=False,
                       help="Use simple Rich console interface instead of TUI")
    parser.add_argument("--web", action="store_true", default=False,
                       help="Launch Morphable Web UI (browser-based, port 8080)")
    parser.add_argument("--web-port", type=int, default=8080,
                       help="Port for web UI server (default: 8080)")
    parser.add_argument("--web-host", default="127.0.0.1",
                       help="Bind address for web UI (default: 127.0.0.1)")
    parser.add_argument("--mock-voice", action="store_true", default=False,
                       help="Force mock STT/TTS (skip real Deepgram/Cartesia)")
    parser.add_argument("--login", action="store_true", default=False,
                       help="Login with Claude Pro/Max OAuth (free API access)")
    parser.add_argument("--logout", action="store_true", default=False,
                       help="Remove stored OAuth credentials")
    parser.add_argument("--auth-status", action="store_true", default=False,
                       help="Check authentication status")
    
    args = parser.parse_args()
    
    # Handle auth commands first
    if args.login:
        from .auth.oauth import login
        login()
        return
    
    if args.logout:
        from .auth.oauth import delete_credentials
        delete_credentials()
        print("✅ OAuth credentials removed.")
        return
    
    if args.auth_status:
        from .auth.oauth import load_credentials
        creds = load_credentials()
        if creds is None:
            print("❌ No OAuth credentials stored.")
            print("   Run: python -m bigbrain --login")
        elif creds.is_expired:
            print(f"⚠️  OAuth token expired (was valid until {time.strftime('%Y-%m-%d %H:%M', time.localtime(creds.expires_at))})")
            print("   Will auto-refresh on next run, or re-login: python -m bigbrain --login")
        else:
            remaining = (creds.expires_at - time.time()) / 3600
            print(f"✅ OAuth active — {remaining:.1f}h remaining")
            print(f"   Token stored at: ~/.bigbrain/auth/")
        return
    
    # Determine UI mode
    if args.web:
        ui_mode = "web"
        if not AIOHTTP_AVAILABLE:
            print("⚠️  aiohttp not installed. Run: pip install aiohttp")
            ui_mode = "simple"
    elif args.simple:
        ui_mode = "simple"
    else:
        ui_mode = "tui"
        if not TEXTUAL_AVAILABLE:
            print("⚠️  Textual not available, using simple mode")
            ui_mode = "simple"
    
    if not args.simple:
        print(f"🧠 Starting BigBrain (workspace: {args.workspace})...")
    
    # Create and run the system
    system = BigBrainSystem(
        workspace=args.workspace,
        log_dir=Path(args.log_dir),
        ui_mode=ui_mode,
        mock_voice=args.mock_voice,
        web_port=args.web_port,
        web_host=getattr(args, 'web_host', '127.0.0.1'),
    )
    
    try:
        await system.run(mode="interactive")
    except KeyboardInterrupt:
        print("\\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\\n❌ Fatal error: {e}")
        sys.exit(1)

