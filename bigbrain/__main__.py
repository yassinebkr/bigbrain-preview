"""BigBrain - Main entry point that wires everything together."""

import asyncio
import sys
import signal
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .bus.bus import MessageBus
from .bus.message import BusMessage, MessageType, Priority
from .bus.auth import BusAuth
from .config import config
from .orchestrator.orchestrator import WorkspaceOrchestrator
from .orchestrator.execution_modes import ExecutionMode, BrainExecutionConfig
from .brains.python_brain import PythonBrain
from .brains.researcher import ResearcherBrain
from .front.front_brain import FrontBrain
from .front.focus_manager import FocusManager, FocusMode, FocusState
from .ui.rich_adapter import RichAdapter
from .llm.mock_provider import MockLLMProvider
from .voice.voice_manager import create_voice_manager
from .voice.voice_brain import VoiceBrain
from .verification.pipeline import VerificationPipeline, VerificationLevel
from .verification.v1_schema import SchemaValidator
from .verification.v4_deterministic import DeterministicValidator
from .verification.v3_cross_check import CrossProviderVerifier
from .verification.v5_human_gate import HumanGateVerifier
from .memory.memory_manager import MemoryManager

# Try to import TUI, fall back to Rich if unavailable
try:
    from .tui.app import BigBrainApp
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False


class BigBrainSystem:
    """
    BigBrain system coordinator.
    
    Wires together all components and provides the main demo/entry point.
    Creates the bus, registers brains, starts orchestrator, and launches TUI.
    """
    
    def __init__(self, workspace: str = "demo", log_dir: Path = None, ui_mode: str = "tui"):
        """
        Initialize BigBrain system.
        
        Args:
            workspace: Name of the primary workspace
            log_dir: Directory for message logs (defaults to ./logs)
            ui_mode: UI mode ("tui" or "simple")
        """
        self.workspace = workspace
        self.log_dir = log_dir or Path("logs")
        self.ui_mode = ui_mode
        
        # Core components
        self.bus: Optional[MessageBus] = None
        self.bus_auth: Optional[BusAuth] = None
        self.orchestrator: Optional[WorkspaceOrchestrator] = None
        self.front_brain: Optional[FrontBrain] = None
        self.focus_manager: Optional[FocusManager] = None
        self.ui: Optional[RichAdapter] = None
        self.tui_app: Optional['BigBrainApp'] = None
        
        # New components
        self.llm_provider: Optional[MockLLMProvider] = None
        self.voice_manager = None
        self.voice_brain: Optional[VoiceBrain] = None
        self.verification: Optional[VerificationPipeline] = None
        self.memory_manager: Optional[MemoryManager] = None
        
        # Brain registry
        self.brains: Dict[str, Any] = {}
        
        # System state
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def _ui_msg(self, message: str, msg_type: str = "info") -> None:
        """Safe UI message — prints to console if UI not available."""
        if self.ui:
            await self.ui.render_message(message, msg_type)
        else:
            icons = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️"}
            print(f"{icons.get(msg_type, '📝')} {message}")
    
    def _create_llm_provider(self):
        """Create the best available LLM provider."""
        # Check for OAuth token first (Claude Pro/Max)
        oauth_key = config.resolve_anthropic_key()
        if oauth_key and not config.anthropic_api_key:
            # OAuth token — use dedicated provider with stealth headers
            from .llm.anthropic_oauth import AnthropicOAuthProvider
            model = config.front_brain_model or "claude-sonnet-4-20250514"
            provider = AnthropicOAuthProvider(token=oauth_key, default_model=model)
            print(f"🔑 LLM: Claude via OAuth ({model})")
            return provider

        # Check for env var API keys
        if config.has_api_key:
            try:
                from .llm.litellm_provider import LiteLLMProvider
                # If we have an OAuth-resolved Anthropic key, set it
                if oauth_key:
                    import os
                    os.environ["ANTHROPIC_API_KEY"] = oauth_key
                provider = LiteLLMProvider(default_model=config.effective_front_model)
                print(f"🔑 LLM: {config.summary()}")
                return provider
            except ImportError:
                print("⚠️  API key found but litellm not installed. Run: pip install litellm")
                print("    Falling back to mock LLM.")

        print("ℹ️  No API key found — using mock LLM.")
        print("    Run: python -m bigbrain --login    (Claude Pro/Max OAuth)")
        print("    Or set OPENAI_API_KEY / ANTHROPIC_API_KEY in .env")
        return MockLLMProvider(token_delay_ms=50, realistic_responses=True)
    
    async def initialize(self) -> None:
        """Initialize all BigBrain components."""
        print(f"🧠 Initializing BigBrain system (workspace: {self.workspace})...")
        
        # 1. Bus authentication (HMAC-SHA256 per-brain tokens)
        self.bus_auth = BusAuth()
        
        # 2. Message bus with auth
        self.bus = MessageBus(log_dir=self.log_dir, auth=self.bus_auth)
        
        # 3. Focus manager (attention filtering)
        self.focus_manager = FocusManager()
        self.focus_manager.set_workspace_focus(self.workspace, FocusState.ACTIVE, "system")
        self.focus_manager.set_focus_mode(FocusMode.NORMAL, "system")
        
        # 4. LLM provider (OAuth → litellm → mock)
        self.llm_provider = self._create_llm_provider()
        
        # 5. Verification pipeline (V4 → V1 → V3 → V5)
        self.verification = self._create_verification_pipeline()
        
        # 6. Memory manager
        try:
            self.memory_manager = MemoryManager(
                brain_name="system",
                project_name="bigbrain",
                workspace=self.workspace,
            )
            print("💾 Memory: ChromaDB loaded")
        except Exception as e:
            print(f"⚠️  Memory init failed: {e} — running without persistent memory")
            self.memory_manager = None
        
        # 7. Orchestrator with execution modes
        self.orchestrator = WorkspaceOrchestrator(self.workspace, self.bus)
        self._configure_execution_modes()
        
        # 8. Voice manager (auto-detects real APIs)
        self.voice_manager = create_voice_manager(auto_listen=True)
        
        # 8b. Voice Brain — fast conversational LLM for natural speech
        self.voice_brain = VoiceBrain(
            llm_provider=self.llm_provider,
            bus=self.bus,
        )
        voice_model = self.voice_brain.voice_model
        print(f"🗣️  Voice Brain: {voice_model} (fast conversational model)")
        
        # 9. Brains (registers HMAC tokens)
        await self._create_brains()
        
        # 10. Front brain
        self.front_brain = FrontBrain(self.bus, llm_provider=self.llm_provider)
        
        # 11. Wire everything together
        self._setup_voice_integration()
        self._setup_focus_filtering()
        
        # 12. UI
        await self._create_ui()
        
        print("✅ BigBrain system initialized successfully!")
    
    def _create_verification_pipeline(self) -> VerificationPipeline:
        """Create the 5-layer verification pipeline."""
        pipeline = VerificationPipeline()
        
        # V4: Deterministic checks (syntax, tests) — free, fast
        try:
            v4 = DeterministicValidator()
            pipeline.add_verifier(v4)
        except Exception:
            pass
        
        # V1: Schema validation — free
        try:
            v1 = SchemaValidator()
            pipeline.add_verifier(v1)
        except Exception:
            pass
        
        # V3: Cross-provider LLM review — costs money, uses different provider
        try:
            v3 = CrossProviderVerifier(llm_provider=self.llm_provider)
            pipeline.add_verifier(v3)
        except Exception:
            pass
        
        # V5: Human gate — waits for approval
        try:
            v5 = HumanGateVerifier(timeout=300.0)
            pipeline.add_verifier(v5)
        except Exception:
            pass
        
        # Default: run V4 + V1 only (Lightning mode)
        pipeline.set_enabled_levels([
            VerificationLevel.V4_DETERMINISTIC,
            VerificationLevel.V1_SCHEMA,
        ])
        
        print(f"✅ Verification: {len(pipeline.verifiers)} layers loaded")
        return pipeline
    
    def _configure_execution_modes(self) -> None:
        """Configure execution modes for each brain."""
        # PythonBrain: Lightning (auto) by default — V4 + V1 only
        self.orchestrator.set_execution_mode(
            "python_brain",
            BrainExecutionConfig(
                brain_name="python_brain",
                mode=ExecutionMode.LIGHTNING,
                requires_approval=False,
                max_retries=3,
            )
        )
        
        # Researcher: Lightning — auto-approve research results
        self.orchestrator.set_execution_mode(
            "researcher",
            BrainExecutionConfig(
                brain_name="researcher",
                mode=ExecutionMode.LIGHTNING,
                requires_approval=False,
                max_retries=2,
            )
        )
        
        print("⚡ Execution modes: Lightning (auto) for all brains")
    
    def _setup_focus_filtering(self) -> None:
        """Wire the system's focus manager into Front Brain.
        
        FrontBrain already has focus filtering built into _handle_bus_event,
        so we just share the system-level FocusManager instance instead of
        letting FrontBrain use a separate one.
        """
        if self.front_brain and self.focus_manager:
            self.front_brain.focus_manager = self.focus_manager
    
    async def _create_brains(self) -> None:
        """Create and register execution brains."""
        # Python execution brain (with LLM for code generation)
        python_brain = PythonBrain(
            name="python_brain",
            bus=self.bus,
            workspace=self.workspace,
            timeout=30,
            work_dir=None,  # Uses tempdir (cross-platform safe)
            llm_provider=self.llm_provider
        )
        self.brains["python_brain"] = python_brain
        
        # Research brain (if available)
        try:
            research_brain = ResearcherBrain(
                name="researcher",
                bus=self.bus,
                workspace=self.workspace
            )
            self.brains["researcher"] = research_brain
        except Exception as e:
            print(f"⚠️  Research brain unavailable: {e}")
            print("    Code execution will still work, but research tasks may be limited.")
        
        # Register HMAC tokens for each brain
        for brain_name in self.brains:
            if self.bus_auth:
                self.bus_auth.generate_token(brain_name)
        # Also register system components
        for name in ["orchestrator", f"orchestrator_{self.workspace}", "front_brain", "voice_manager", "voice_brain", "bigbrain_system", "demo_system"]:
            if self.bus_auth:
                self.bus_auth.generate_token(name)
        
        print(f"📋 Registered {len(self.brains)} brains: {list(self.brains.keys())}")
    
    async def _create_ui(self) -> None:
        """Create UI based on mode."""
        if self.ui_mode == "tui" and TEXTUAL_AVAILABLE:
            print("🖥️  Starting Textual TUI...")
            self.tui_app = BigBrainApp(bigbrain_system=self)
        else:
            if self.ui_mode == "tui" and not TEXTUAL_AVAILABLE:
                print("⚠️  Textual not available, falling back to simple mode")
            self.ui = RichAdapter()
    
    def _setup_voice_integration(self) -> None:
        """Wire Voice Manager → Voice Brain → TTS pipeline.
        
        The Voice Brain has its own fast LLM (Sonnet-class) that generates
        natural spoken responses. It's NOT a TTS wrapper — it decides HOW
        to say things in a conversational way.
        
        Flow: User speaks → STT → Voice Brain (fast LLM) → TTS → User hears
        """
        async def on_transcription(text: str, is_final: bool) -> None:
            if is_final and self.front_brain:
                # Notify the bus that voice input arrived
                message = BusMessage(
                    type=MessageType.TASK,
                    source="voice_manager",
                    target="front_brain",
                    workspace=self.workspace,
                    payload={
                        "type": "voice_input",
                        "text": text,
                        "timestamp": time.time()
                    }
                )
                await self.bus.send(message)
        
        async def on_response_needed(user_input: str) -> str:
            """Voice Brain generates the spoken response — not the main LLM."""
            if self.voice_brain:
                return await self.voice_brain.respond_to_voice(user_input)
            return "I heard you, but my voice brain isn't connected yet."
        
        async def on_state_change(new_state, extra_data) -> None:
            if self.tui_app and hasattr(self.tui_app, 'brain_panel'):
                voice_status = {
                    "listening": "busy",
                    "thinking": "busy", 
                    "speaking": "busy",
                    "idle": "idle"
                }.get(str(new_state), "offline")
                
                self.tui_app.brain_panel.update_brain_status(
                    "voice_brain", 
                    voice_status, 
                    self.voice_manager.is_enabled
                )
        
        self.voice_manager.set_transcription_callback(on_transcription)
        self.voice_manager.set_response_callback(on_response_needed)
        self.voice_manager.set_state_change_callback(on_state_change)
    
    async def start(self) -> None:
        """Start the BigBrain system."""
        if self._running:
            raise RuntimeError("BigBrain system is already running")
        
        self._running = True
        
        try:
            # Start UI
            if self.tui_app:
                # TUI mode will be started separately
                pass
            else:
                if self.ui:
                    await self.ui.start()
                await self._ui_msg("🧠 Starting BigBrain system...", "info")
            
            # Start orchestrator
            await self.orchestrator.start()
            
            # Register brains with orchestrator
            for brain_name, brain in self.brains.items():
                self.orchestrator.register_brain(brain_name, {"type": type(brain).__name__})
            
            # Start all brains
            for brain_name, brain in self.brains.items():
                await brain.start()
                if self.ui:
                    if self.ui:
                        await self.ui.render_brain_status(brain_name, brain.get_status())
            
            # Start front brain
            await self.front_brain.start()
            
            # Start voice brain
            if self.voice_brain:
                await self.voice_brain.start()
            
            # Announce system ready
            await self.bus.broadcast_event(
                source="bigbrain_system",
                event_type="system.ready",
                payload={
                    "workspace": self.workspace,
                    "brains": list(self.brains.keys()),
                    "version": "0.1.0"
                },
                workspace=self.workspace,
                priority=Priority.HIGH
            )
            
            if self.ui:
                await self._ui_msg("✅ BigBrain system started! Type 'help' for assistance.", "success")
            
        except Exception as e:
            if self.ui:
                await self._ui_msg(f"❌ Failed to start BigBrain: {e}", "error")
            else:
                print(f"❌ Failed to start BigBrain: {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the BigBrain system."""
        if not self._running:
            return
        
        print("🛑 Stopping BigBrain system...")
        self._running = False
        
        try:
            # Stop voice brain
            if self.voice_brain:
                await self.voice_brain.stop()
            
            # Stop front brain
            if self.front_brain:
                await self.front_brain.stop()
            
            # Stop all brains
            for brain in self.brains.values():
                await brain.stop()
            
            # Stop orchestrator
            if self.orchestrator:
                await self.orchestrator.stop()
            
            # Stop UI
            if self.ui:
                if self.ui:
                    await self.ui.stop()
            
            # Close message bus
            if self.bus:
                await self.bus.close()
            
            print("✅ BigBrain system stopped cleanly.")
        
        except Exception as e:
            print(f"⚠️  Error during shutdown: {e}")
    
    async def run_demo(self) -> None:
        """Run the interactive demo mode."""
        await self._ui_msg("🎮 Entering demo mode - showing system capabilities...", "info")
        
        # Demo tasks to showcase functionality
        demo_tasks = [
            {
                "name": "Code Execution",
                "description": "Execute a simple Python script",
                "task": {
                    "type": "execute_code",
                    "code": '''
# BigBrain Python execution demo
import time
import math

print("🧠 BigBrain Python Brain Demo")
print("=" * 40)

# Calculate some values
result = math.sqrt(42)
print(f"✓ Square root of 42: {result:.3f}")

# Generate a simple list
numbers = [i**2 for i in range(5)]
print(f"✓ Squares of 0-4: {numbers}")

# Show current time
print(f"✓ Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

print("=" * 40)
print("Demo completed successfully!")
'''
                }
            },
            {
                "name": "File Operations",
                "description": "Create and read files",
                "task": {
                    "type": "execute_code",
                    "files": {
                        "demo_input.txt": "Hello from BigBrain!"
                    },
                    "code": '''
# File operations demo
import os

print("📁 File Operations Demo")
print("=" * 30)

# Read the input file
with open("demo_input.txt", "r") as f:
    content = f.read()
    print(f"✓ Input file content: {content}")

# Create an output file
output_data = {
    "system": "BigBrain",
    "demo": "file_operations",
    "status": "success"
}

with open("demo_output.txt", "w") as f:
    for key, value in output_data.items():
        f.write(f"{key}: {value}\\n")

print("✓ Created demo_output.txt")

# List files
files = os.listdir(".")
python_files = [f for f in files if f.endswith(('.py', '.txt'))]
print(f"✓ Files in directory: {python_files}")
'''
                }
            }
        ]
        
        for i, demo in enumerate(demo_tasks, 1):
            await self._ui_msg(f"🎯 Demo {i}/{len(demo_tasks)}: {demo['name']}", "info")
            await self._ui_msg(f"   {demo['description']}", "info")
            
            # Send task through the system
            task_message = BusMessage(
                type=MessageType.TASK,
                source="demo_system",
                target="orchestrator_demo",
                workspace=self.workspace,
                payload=demo['task'],
                priority=Priority.NORMAL
            )
            
            await self.bus.send(task_message)
            if self.ui:
                await self.ui.render_progress(f"demo_{i}", status="Running...")
            
            # Wait for completion (simplified for demo)
            await asyncio.sleep(3)
            if self.ui:
                await self.ui.render_progress(f"demo_{i}", progress=1.0, status="Complete")
            
            # Small delay between demos
            await asyncio.sleep(1)
        
        await self._ui_msg("🎉 Demo completed! The system is ready for your tasks.", "success")
    
    async def run_interactive(self) -> None:
        """Run interactive mode where user can enter tasks."""
        await self._ui_msg("💬 Interactive mode started. Type your tasks naturally!", "info")
        
        while self._running:
            try:
                # Get user input
                if self.ui:
                    user_input = await self.ui.get_user_input("BigBrain")
                
                if not user_input or user_input.strip() == "":
                    continue
                
                # Handle special commands
                command = user_input.lower().strip()
                
                if command in ("quit", "exit"):
                    self._shutdown_event.set()
                    break
                elif command == "help":
                    if self.ui:
                        await self.ui.show_help()
                    continue
                elif command == "status":
                    await self._show_system_status()
                    continue
                elif command == "demo":
                    await self.run_demo()
                    continue
                
                # Send user input directly to Front Brain for processing
                print("⏳ Thinking...", end="", flush=True)
                response = await self.front_brain.handle_user_input(user_input)
                print("\r" + " " * 20 + "\r", end="", flush=True)  # Clear thinking
                await self._ui_msg(f"🧠 {response}", "info")
                
            except KeyboardInterrupt:
                self._shutdown_event.set()
                break
            except EOFError:
                self._shutdown_event.set()
                break
            except Exception as e:
                await self._ui_msg(f"Input error: {e}", "error")
    
    async def _show_system_status(self) -> None:
        """Show current system status."""
        # Get orchestrator status
        orchestrator_status = self.orchestrator.get_status()
        
        # Get brain statuses
        brain_statuses = {}
        for name, brain in self.brains.items():
            brain_statuses[name] = brain.get_status()
        
        # Get bus stats
        bus_stats = self.bus.get_stats()
        
        if self.ui:
            await self.ui.render_workspace_overview({
            self.workspace: {
                "state": "active" if self._running else "stopped",
                "orchestrator": orchestrator_status,
                "brains": brain_statuses,
                "bus": bus_stats
            }
        })
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\\n🛑 Received signal {signum}, shutting down...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run_tui(self) -> None:
        """Run the Textual TUI interface."""
        if not self.tui_app:
            raise RuntimeError("TUI app not initialized")
        
        # Start the TUI app (this blocks until app exits)
        await self.tui_app.run_async()
        
        # When TUI exits, signal shutdown
        self._shutdown_event.set()
    
    async def run(self, mode: str = "interactive") -> None:
        """
        Run BigBrain in the specified mode.
        
        Args:
            mode: "interactive" for REPL mode, "demo" for automated demo
        """
        self._setup_signal_handlers()
        
        try:
            await self.initialize()
            
            if self.tui_app:
                # TUI mode — system starts inside TUI's event loop (on_mount)
                await self.run_tui()
            else:
                # Simple mode — start system, then REPL
                await self.start()
                await self.run_interactive()
                
                # Wait for shutdown signal
                await self._shutdown_event.wait()
            
        finally:
            await self.stop()


async def main() -> None:
    """Main entry point for BigBrain."""
    import argparse
    import time
    
    parser = argparse.ArgumentParser(description="BigBrain - Multi-Brain AI Agent System")
    parser.add_argument("--workspace", default="default", help="Workspace name (default: default)")
    parser.add_argument("--log-dir", default="logs", help="Log directory (default: logs)")
    parser.add_argument("--simple", action="store_true", default=False,
                       help="Use simple Rich console interface instead of TUI")
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
    ui_mode = "simple" if args.simple else "tui"
    if ui_mode == "tui" and not TEXTUAL_AVAILABLE:
        print("⚠️  Textual not available, using simple mode")
        ui_mode = "simple"
    
    if not args.simple:
        print(f"🧠 Starting BigBrain (workspace: {args.workspace})...")
    
    # Create and run the system
    system = BigBrainSystem(
        workspace=args.workspace,
        log_dir=Path(args.log_dir),
        ui_mode=ui_mode
    )
    
    try:
        await system.run(mode="interactive")
    except KeyboardInterrupt:
        print("\\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Handle missing event loop on Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(main())