"""BigBrain - Main entry point that wires everything together."""

import asyncio
import sys
import signal
from pathlib import Path
from typing import Dict, Any, Optional

from .bus.bus import MessageBus
from .bus.message import BusMessage, MessageType, Priority
from .orchestrator.orchestrator import WorkspaceOrchestrator
from .brains.python_brain import PythonBrain
from .brains.researcher import ResearcherBrain
from .front.front_brain import FrontBrain
from .ui.rich_adapter import RichAdapter


class BigBrainSystem:
    """
    BigBrain system coordinator.
    
    Wires together all components and provides the main demo/entry point.
    Creates the bus, registers brains, starts orchestrator, and launches TUI.
    """
    
    def __init__(self, workspace: str = "demo", log_dir: Path = None):
        """
        Initialize BigBrain system.
        
        Args:
            workspace: Name of the primary workspace
            log_dir: Directory for message logs (defaults to ./logs)
        """
        self.workspace = workspace
        self.log_dir = log_dir or Path("logs")
        
        # Core components
        self.bus: Optional[MessageBus] = None
        self.orchestrator: Optional[WorkspaceOrchestrator] = None
        self.front_brain: Optional[FrontBrain] = None
        self.ui: Optional[RichAdapter] = None
        
        # Brain registry
        self.brains: Dict[str, Any] = {}
        
        # System state
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """Initialize all BigBrain components."""
        print(f"🧠 Initializing BigBrain system (workspace: {self.workspace})...")
        
        # Create message bus
        self.bus = MessageBus(log_dir=self.log_dir)
        
        # Create orchestrator
        self.orchestrator = WorkspaceOrchestrator(self.workspace, self.bus)
        
        # Create brains
        await self._create_brains()
        
        # Create front brain
        self.front_brain = FrontBrain(self.bus)
        
        # Create UI
        self.ui = RichAdapter()
        
        print("✅ BigBrain system initialized successfully!")
    
    async def _create_brains(self) -> None:
        """Create and register execution brains."""
        # Python execution brain
        python_brain = PythonBrain(
            name="python_brain",
            bus=self.bus,
            workspace=self.workspace,
            timeout=30,
            work_dir=Path(f"work/{self.workspace}/python")
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
        
        print(f"📋 Registered {len(self.brains)} brains: {list(self.brains.keys())}")
    
    async def start(self) -> None:
        """Start the BigBrain system."""
        if self._running:
            raise RuntimeError("BigBrain system is already running")
        
        self._running = True
        
        try:
            # Start UI
            await self.ui.start()
            await self.ui.render_message("🧠 Starting BigBrain system...", "info")
            
            # Start orchestrator
            await self.orchestrator.start()
            
            # Register brains with orchestrator
            for brain_name, brain in self.brains.items():
                self.orchestrator.register_brain(brain_name, {"type": type(brain).__name__})
            
            # Start all brains
            for brain_name, brain in self.brains.items():
                await brain.start()
                await self.ui.render_brain_status(brain_name, brain.get_status())
            
            # Start front brain
            await self.front_brain.start()
            
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
            
            await self.ui.render_message("✅ BigBrain system started! Type 'help' for assistance.", "success")
            
        except Exception as e:
            await self.ui.render_message(f"❌ Failed to start BigBrain: {e}", "error")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the BigBrain system."""
        if not self._running:
            return
        
        print("🛑 Stopping BigBrain system...")
        self._running = False
        
        try:
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
                await self.ui.stop()
            
            # Close message bus
            if self.bus:
                await self.bus.close()
            
            print("✅ BigBrain system stopped cleanly.")
        
        except Exception as e:
            print(f"⚠️  Error during shutdown: {e}")
    
    async def run_demo(self) -> None:
        """Run the interactive demo mode."""
        await self.ui.render_message("🎮 Entering demo mode - showing system capabilities...", "info")
        
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
            await self.ui.render_message(f"🎯 Demo {i}/{len(demo_tasks)}: {demo['name']}", "info")
            await self.ui.render_message(f"   {demo['description']}", "info")
            
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
            await self.ui.render_progress(f"demo_{i}", status="Running...")
            
            # Wait for completion (simplified for demo)
            await asyncio.sleep(3)
            await self.ui.render_progress(f"demo_{i}", progress=1.0, status="Complete")
            
            # Small delay between demos
            await asyncio.sleep(1)
        
        await self.ui.render_message("🎉 Demo completed! The system is ready for your tasks.", "success")
    
    async def run_interactive(self) -> None:
        """Run interactive mode where user can enter tasks."""
        await self.ui.render_message("💬 Interactive mode started. Type your tasks naturally!", "info")
        
        while self._running:
            try:
                # Get user input
                user_input = await self.ui.get_user_input("BigBrain")
                
                if not user_input or user_input.strip() == "":
                    continue
                
                # Handle special commands
                command = user_input.lower().strip()
                
                if command in ("quit", "exit"):
                    self._shutdown_event.set()
                    break
                elif command == "help":
                    await self.ui.show_help()
                    continue
                elif command == "status":
                    await self._show_system_status()
                    continue
                elif command == "demo":
                    await self.run_demo()
                    continue
                
                # Send user input to front brain for processing
                user_message = BusMessage(
                    type=MessageType.TASK,
                    source="user",
                    target="front_brain",
                    workspace=self.workspace,
                    payload={
                        "type": "user_input",
                        "text": user_input,
                        "timestamp": time.time()
                    }
                )
                
                await self.bus.send(user_message)
                await self.ui.render_message(f"📤 Sent: {user_input}", "info")
                
            except KeyboardInterrupt:
                self._shutdown_event.set()
                break
            except EOFError:
                self._shutdown_event.set()
                break
            except Exception as e:
                await self.ui.show_error(f"Input error: {e}")
    
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
    
    async def run(self, mode: str = "interactive") -> None:
        """
        Run BigBrain in the specified mode.
        
        Args:
            mode: "interactive" for REPL mode, "demo" for automated demo
        """
        self._setup_signal_handlers()
        
        try:
            await self.initialize()
            await self.start()
            
            if mode == "demo":
                await self.run_demo()
                # After demo, switch to interactive
                await self.run_interactive()
            else:
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
    parser.add_argument("--workspace", default="demo", help="Workspace name (default: demo)")
    parser.add_argument("--mode", choices=["interactive", "demo"], default="demo", 
                       help="Run mode (default: demo)")
    parser.add_argument("--log-dir", default="logs", help="Log directory (default: logs)")
    
    args = parser.parse_args()
    
    print(f"""
🧠 BigBrain - Multi-Brain AI Agent System
====================================
Version: 0.1.0 (Preview Implementation)
Workspace: {args.workspace}
Mode: {args.mode}
Logs: {args.log_dir}
Time: {time.strftime('%Y-%m-%d %H:%M:%S')}

This is a reference implementation demonstrating multi-brain AI
architecture with message bus communication and workspace orchestration.
""")
    
    # Create and run the system
    system = BigBrainSystem(
        workspace=args.workspace,
        log_dir=Path(args.log_dir)
    )
    
    try:
        await system.run(mode=args.mode)
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