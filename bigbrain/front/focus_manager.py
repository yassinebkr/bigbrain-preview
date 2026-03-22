"""Focus Manager - Attention filtering system for BigBrain."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from ..bus.message import BusMessage, Priority


class FocusMode(str, Enum):
    """User-selectable focus modes."""
    DEEP_FOCUS = "deep_focus"    # Only P0 (critical) events reach user
    NORMAL = "normal"            # P0 + P1 (critical + high) events reach user  
    OVERVIEW = "overview"        # P0 + P1 + P2 (all except low) from all workspaces


class FocusState(str, Enum):
    """Focus state per workspace."""
    ACTIVE = "active"            # Full attention - all events reach Front Brain
    PERIPHERAL = "peripheral"    # Background monitoring - only high priority events
    BACKGROUND = "background"    # Minimal attention - only critical events


@dataclass
class WorkspaceFocus:
    """Focus configuration for a single workspace."""
    name: str
    state: FocusState = FocusState.BACKGROUND
    since: float = field(default_factory=time.time)
    
    # Focus rules for this workspace
    promotion_triggers: Set[str] = field(default_factory=lambda: {"error", "complete", "blocked"})
    interrupt_threshold: Priority = Priority.HIGH
    detail_level: str = "summary"  # "detailed", "summary", "minimal"
    
    # Statistics
    events_received: int = 0
    events_filtered: int = 0
    last_event_time: float = 0


@dataclass
class FocusRules:
    """Global focus rules and configuration."""
    current_mode: FocusMode = FocusMode.NORMAL
    changed_by: str = "system"  # "user", "front_brain", "focus_rules", "system"
    last_mode_change: float = field(default_factory=time.time)
    
    # Auto-focus management
    auto_switch_enabled: bool = True
    idle_timeout_minutes: int = 30  # Switch to overview after idle period
    deep_focus_duration_minutes: int = 90  # Max time in deep focus before suggesting break


class FocusManager:
    """
    Manages attention and focus for BigBrain Front Brain.
    
    Filters bus events based on:
    - Current focus mode (deep/normal/overview)
    - Workspace focus states (active/peripheral/background)
    - Event priorities and types
    - User preferences and rules
    
    Key Features:
    - Event-driven filtering at bus level
    - Workspace-specific focus rules
    - Automatic focus mode suggestions
    - Focus switching with context preservation
    - Attention statistics and monitoring
    """
    
    def __init__(self):
        """Initialize focus manager with default settings."""
        self.focus_rules = FocusRules()
        self.workspaces: Dict[str, WorkspaceFocus] = {}
        
        # Track user activity
        self.last_user_activity = time.time()
        self.last_focus_suggestion = 0.0
        
        # Buffered events for deferred delivery
        self._buffered_events: Dict[str, List[BusMessage]] = {}
    
    def set_focus_mode(self, mode: FocusMode, changed_by: str = "user") -> None:
        """
        Change the global focus mode.
        
        Args:
            mode: New focus mode
            changed_by: Who requested the change
        """
        old_mode = self.focus_rules.current_mode
        self.focus_rules.current_mode = mode
        self.focus_rules.changed_by = changed_by
        self.focus_rules.last_mode_change = time.time()
        
        # Log the change
        print(f"Focus mode changed: {old_mode.value} → {mode.value} (by {changed_by})")
        
        # Deliver any buffered events that now pass the filter
        self._process_buffered_events()
    
    def set_workspace_focus(self, workspace: str, state: FocusState, 
                           changed_by: str = "user") -> List[BusMessage]:
        """
        Change focus state for a specific workspace.
        
        Args:
            workspace: Workspace name
            state: New focus state
            changed_by: Who requested the change
            
        Returns:
            List of buffered events to deliver to Front Brain
        """
        if workspace not in self.workspaces:
            self.workspaces[workspace] = WorkspaceFocus(workspace)
        
        old_state = self.workspaces[workspace].state
        self.workspaces[workspace].state = state
        self.workspaces[workspace].since = time.time()
        
        print(f"Workspace {workspace} focus: {old_state.value} → {state.value} (by {changed_by})")
        
        # If switching to active, deliver buffered events for this workspace
        events_to_deliver = []
        if state == FocusState.ACTIVE and workspace in self._buffered_events:
            buffered = self._buffered_events[workspace]
            self._buffered_events[workspace] = []
            
            for event in buffered:
                if self._should_deliver_event(event):
                    events_to_deliver.append(event)  # Collect events to deliver
        
        return events_to_deliver
    
    def filter_event(self, event: BusMessage) -> Optional[BusMessage]:
        """
        Filter an event through the focus system.
        
        Args:
            event: Event to filter
            
        Returns:
            Event if it should be delivered, None if filtered
        """
        workspace = event.workspace or "default"
        
        # Track event for workspace
        if workspace not in self.workspaces:
            self.workspaces[workspace] = WorkspaceFocus(workspace)
        
        workspace_focus = self.workspaces[workspace]
        workspace_focus.events_received += 1
        workspace_focus.last_event_time = time.time()
        
        # Check if event should be delivered
        if self._should_deliver_event(event):
            return event
        else:
            # Buffer for potential later delivery
            workspace_focus.events_filtered += 1
            self._buffer_event(event)
            return None
    
    def get_active_workspace(self) -> Optional[str]:
        """Get the currently active workspace."""
        active_workspaces = [
            ws.name for ws in self.workspaces.values() 
            if ws.state == FocusState.ACTIVE
        ]
        
        if active_workspaces:
            # Return most recently activated
            return max(active_workspaces, 
                      key=lambda ws: self.workspaces[ws].since)
        
        return None
    
    def suggest_focus_change(self) -> Optional[Dict[str, Any]]:
        """
        Suggest focus mode or workspace changes based on context.
        
        Returns:
            Suggestion dictionary or None
        """
        current_time = time.time()
        
        # Don't suggest too frequently
        if current_time - self.last_focus_suggestion < 300:  # 5 minutes
            return None
        
        # Check if user has been idle
        idle_minutes = (current_time - self.last_user_activity) / 60
        
        if (idle_minutes > self.focus_rules.idle_timeout_minutes and 
            self.focus_rules.current_mode != FocusMode.OVERVIEW):
            self.last_focus_suggestion = current_time
            return {
                "type": "mode_change",
                "suggested_mode": FocusMode.OVERVIEW,
                "reason": f"Idle for {idle_minutes:.1f} minutes",
                "confidence": 0.7
            }
        
        # Check if user has been in deep focus too long
        if self.focus_rules.current_mode == FocusMode.DEEP_FOCUS:
            deep_focus_minutes = (current_time - self.focus_rules.last_mode_change) / 60
            if deep_focus_minutes > self.focus_rules.deep_focus_duration_minutes:
                self.last_focus_suggestion = current_time
                return {
                    "type": "break_suggestion",
                    "suggested_mode": FocusMode.NORMAL,
                    "reason": f"Deep focus for {deep_focus_minutes:.1f} minutes",
                    "confidence": 0.8
                }
        
        # Check for workspaces with pending high-priority events
        for workspace, focus in self.workspaces.items():
            if (focus.state == FocusState.BACKGROUND and 
                workspace in self._buffered_events and
                len(self._buffered_events[workspace]) > 5):
                
                # Check if any buffered events are high priority
                high_priority_events = [
                    e for e in self._buffered_events[workspace] 
                    if e.priority >= Priority.HIGH
                ]
                
                if high_priority_events:
                    self.last_focus_suggestion = current_time
                    return {
                        "type": "workspace_attention",
                        "workspace": workspace,
                        "suggested_state": FocusState.PERIPHERAL,
                        "reason": f"{len(high_priority_events)} high priority events",
                        "confidence": 0.9
                    }
        
        return None
    
    def mark_user_activity(self) -> None:
        """Mark that the user is active (resets idle timer)."""
        self.last_user_activity = time.time()
    
    def get_focus_status(self) -> Dict[str, Any]:
        """Get current focus status and statistics."""
        current_time = time.time()
        
        workspace_stats = {}
        for name, focus in self.workspaces.items():
            workspace_stats[name] = {
                "state": focus.state.value,
                "since_minutes": (current_time - focus.since) / 60,
                "events_received": focus.events_received,
                "events_filtered": focus.events_filtered,
                "filter_rate": (focus.events_filtered / max(1, focus.events_received)) * 100,
                "buffered_events": len(self._buffered_events.get(name, []))
            }
        
        return {
            "focus_mode": self.focus_rules.current_mode.value,
            "mode_since_minutes": (current_time - self.focus_rules.last_mode_change) / 60,
            "changed_by": self.focus_rules.changed_by,
            "active_workspace": self.get_active_workspace(),
            "idle_minutes": (current_time - self.last_user_activity) / 60,
            "workspaces": workspace_stats,
            "total_buffered_events": sum(len(events) for events in self._buffered_events.values()),
            "auto_switch_enabled": self.focus_rules.auto_switch_enabled
        }
    
    def _should_deliver_event(self, event: BusMessage) -> bool:
        """Determine if an event should be delivered to Front Brain."""
        workspace = event.workspace or "default"
        workspace_focus = self.workspaces.get(workspace)
        
        # Always deliver critical events
        if event.priority >= Priority.CRITICAL:
            return True
        
        # Apply focus mode filters
        if self.focus_rules.current_mode == FocusMode.DEEP_FOCUS:
            # Only critical events in deep focus
            return event.priority >= Priority.CRITICAL
        
        elif self.focus_rules.current_mode == FocusMode.NORMAL:
            # Critical + high priority events
            if event.priority >= Priority.HIGH:
                return True
            
            # Normal priority events only from active workspaces
            if workspace_focus and workspace_focus.state == FocusState.ACTIVE:
                return event.priority >= Priority.NORMAL
            
            return False
        
        elif self.focus_rules.current_mode == FocusMode.OVERVIEW:
            # All except low priority events
            return event.priority >= Priority.NORMAL
        
        return False
    
    def _buffer_event(self, event: BusMessage) -> None:
        """Buffer an event for potential later delivery."""
        workspace = event.workspace or "default"
        
        if workspace not in self._buffered_events:
            self._buffered_events[workspace] = []
        
        self._buffered_events[workspace].append(event)
        
        # Limit buffer size to prevent memory bloat
        max_buffer_size = 50
        if len(self._buffered_events[workspace]) > max_buffer_size:
            # Remove oldest events, keeping high priority ones
            buffer = self._buffered_events[workspace]
            high_priority = [e for e in buffer if e.priority >= Priority.HIGH]
            recent_normal = [e for e in buffer if e.priority < Priority.HIGH][-20:]  # Keep 20 recent
            
            self._buffered_events[workspace] = high_priority + recent_normal
    
    def _process_buffered_events(self) -> List[BusMessage]:
        """Process buffered events with current focus rules."""
        deliverable_events = []
        
        for workspace, events in self._buffered_events.items():
            remaining_events = []
            
            for event in events:
                if self._should_deliver_event(event):
                    deliverable_events.append(event)
                else:
                    remaining_events.append(event)
            
            self._buffered_events[workspace] = remaining_events
        
        # Sort by priority and timestamp
        deliverable_events.sort(key=lambda e: (e.priority.value, e.timestamp), reverse=True)
        
        return deliverable_events