"""Tests for BigBrain message bus system."""

import asyncio
import tempfile
import time
import uuid
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.message import BusMessage, MessageType, Priority
from bigbrain.bus.bus import MessageBus
from bigbrain.bus.logger import BusLogger


class TestBusMessage:
    """Test BusMessage functionality."""
    
    def test_create_basic_message(self):
        """Test creating a basic message."""
        msg = BusMessage(
            type=MessageType.TASK,
            source="test_source",
            target="test_target",
            payload={"data": "test"}
        )
        
        assert msg.type == MessageType.TASK
        assert msg.source == "test_source"
        assert msg.target == "test_target"
        assert msg.payload == {"data": "test"}
        assert msg.id is not None
        assert msg.timestamp > 0
        assert msg.priority == Priority.NORMAL
    
    def test_message_defaults(self):
        """Test message default values."""
        msg = BusMessage(
            type=MessageType.EVENT,
            source="source",
            target="target"
        )
        
        assert msg.payload == {}
        assert msg.workspace is None
        assert msg.project is None
        assert msg.reply_to is None
        assert msg.priority == Priority.NORMAL
        
    def test_is_broadcast(self):
        """Test broadcast message detection."""
        broadcast_msg = BusMessage(
            type=MessageType.EVENT,
            source="source",
            target="*"
        )
        
        direct_msg = BusMessage(
            type=MessageType.TASK,
            source="source", 
            target="specific_target"
        )
        
        assert broadcast_msg.is_broadcast() is True
        assert direct_msg.is_broadcast() is False
    
    def test_is_reply(self):
        """Test reply message detection."""
        original = BusMessage(
            type=MessageType.TASK,
            source="source",
            target="target"
        )
        
        reply = BusMessage(
            type=MessageType.RESULT,
            source="target",
            target="source",
            reply_to=original.id
        )
        
        assert original.is_reply() is False
        assert reply.is_reply() is True
    
    def test_create_reply(self):
        """Test creating a reply message."""
        original = BusMessage(
            type=MessageType.TASK,
            source="requester",
            target="handler",
            workspace="test_workspace",
            project="test_project",
            payload={"task": "do_something"}
        )
        
        reply = original.create_reply(
            source="handler",
            payload={"success": True, "result": "done"}
        )
        
        assert reply.type == MessageType.RESULT
        assert reply.source == "handler"
        assert reply.target == "requester"  # Reply goes back to original sender
        assert reply.workspace == "test_workspace"
        assert reply.project == "test_project"
        assert reply.reply_to == original.id
        assert reply.payload == {"success": True, "result": "done"}
    
    def test_to_log_dict(self):
        """Test converting message to log dictionary."""
        msg = BusMessage(
            type=MessageType.PROGRESS,
            source="brain",
            target="orchestrator",
            workspace="test",
            payload={"progress": 0.5},
            priority=Priority.HIGH
        )
        
        log_dict = msg.to_log_dict()
        
        assert log_dict["id"] == msg.id
        assert log_dict["type"] == "progress"
        assert log_dict["source"] == "brain"
        assert log_dict["target"] == "orchestrator"
        assert log_dict["workspace"] == "test"
        assert log_dict["payload"] == {"progress": 0.5}
        assert log_dict["priority"] == 2  # HIGH priority value
        assert "timestamp" in log_dict


class TestMessageBus:
    """Test MessageBus functionality."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary directory for logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    async def bus(self, temp_log_dir):
        """Create a MessageBus instance for testing."""
        bus = MessageBus(log_dir=temp_log_dir)
        yield bus
        await bus.close()
    
    @pytest.mark.asyncio
    async def test_send_message(self, bus):
        """Test basic message sending."""
        received_messages = []
        
        def handler(message):
            received_messages.append(message)
        
        # Subscribe to messages
        bus.subscribe("test_target", handler)
        
        # Send a message
        msg = BusMessage(
            type=MessageType.TASK,
            source="sender",
            target="test_target",
            payload={"data": "test"}
        )
        
        await bus.send(msg)
        
        # Give async delivery a moment
        await asyncio.sleep(0.1)
        
        assert len(received_messages) == 1
        assert received_messages[0].id == msg.id
        assert received_messages[0].payload == {"data": "test"}
    
    @pytest.mark.asyncio
    async def test_broadcast_message(self, bus):
        """Test broadcast message delivery."""
        received_messages_1 = []
        received_messages_2 = []
        
        def handler1(message):
            received_messages_1.append(message)
        
        def handler2(message):
            received_messages_2.append(message)
        
        # Subscribe multiple handlers
        bus.subscribe("target1", handler1)
        bus.subscribe("target2", handler2)
        
        # Send broadcast message
        msg = BusMessage(
            type=MessageType.EVENT,
            source="broadcaster",
            target="*",
            payload={"event": "global_update"}
        )
        
        await bus.send(msg)
        await asyncio.sleep(0.1)
        
        # Both handlers should receive the broadcast
        assert len(received_messages_1) == 1
        assert len(received_messages_2) == 1
    
    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, bus):
        """Test wildcard subscription receives all messages."""
        all_messages = []
        specific_messages = []
        
        def wildcard_handler(message):
            all_messages.append(message)
        
        def specific_handler(message):
            specific_messages.append(message)
        
        # Subscribe with wildcard and specific target
        bus.subscribe("*", wildcard_handler)
        bus.subscribe("specific", specific_handler)
        
        # Send messages to different targets
        msg1 = BusMessage(type=MessageType.EVENT, source="s1", target="specific")
        msg2 = BusMessage(type=MessageType.EVENT, source="s2", target="other")
        
        await bus.send(msg1)
        await bus.send(msg2)
        await asyncio.sleep(0.1)
        
        # Wildcard handler gets both, specific gets only one
        assert len(all_messages) == 2
        assert len(specific_messages) == 1
        assert specific_messages[0].target == "specific"
    
    @pytest.mark.asyncio
    async def test_async_handler(self, bus):
        """Test async message handlers."""
        results = []
        
        async def async_handler(message):
            await asyncio.sleep(0.01)  # Simulate async work
            results.append(f"processed_{message.payload['id']}")
        
        bus.subscribe("async_target", async_handler)
        
        # Send multiple messages
        for i in range(3):
            msg = BusMessage(
                type=MessageType.TASK,
                source="sender",
                target="async_target",
                payload={"id": i}
            )
            await bus.send(msg)
        
        await asyncio.sleep(0.1)
        
        # All messages should be processed
        assert len(results) == 3
        assert "processed_0" in results
        assert "processed_1" in results
        assert "processed_2" in results
    
    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, bus):
        """Test that handler errors don't affect other handlers."""
        good_results = []
        
        def error_handler(message):
            raise RuntimeError("Handler error")
        
        def good_handler(message):
            good_results.append(message.id)
        
        bus.subscribe("target", error_handler)
        bus.subscribe("target", good_handler)
        
        msg = BusMessage(
            type=MessageType.EVENT,
            source="sender",
            target="target"
        )
        
        await bus.send(msg)
        await asyncio.sleep(0.1)
        
        # Good handler should still work despite error in other handler
        assert len(good_results) == 1
    
    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Test unsubscribing from messages."""
        results = []
        
        def handler(message):
            results.append(message.id)
        
        bus.subscribe("target", handler)
        
        # Send message - should be received
        msg1 = BusMessage(type=MessageType.EVENT, source="s", target="target")
        await bus.send(msg1)
        
        # Unsubscribe
        bus.unsubscribe("target", handler)
        
        # Send message - should not be received
        msg2 = BusMessage(type=MessageType.EVENT, source="s", target="target")
        await bus.send(msg2)
        
        await asyncio.sleep(0.1)
        
        assert len(results) == 1
        assert results[0] == msg1.id
    
    @pytest.mark.asyncio
    async def test_convenience_methods(self, bus):
        """Test convenience methods for common message patterns."""
        results = []
        
        def handler(message):
            results.append({
                "type": message.type,
                "payload": message.payload,
                "target": message.target
            })
        
        bus.subscribe("*", handler)
        
        # Test broadcast_event
        await bus.broadcast_event(
            source="test",
            event_type="custom_event",
            payload={"data": "event_data"},
            workspace="test_workspace"
        )
        
        # Test send_task
        task_msg = await bus.send_task(
            source="requester",
            target="worker",
            task_data={"action": "process"},
            workspace="test_workspace"
        )
        
        await asyncio.sleep(0.1)
        
        assert len(results) == 2
        
        # Check event
        event_result = next(r for r in results if r["type"] == "event")
        assert event_result["target"] == "*"
        assert event_result["payload"]["event"] == "custom_event"
        assert event_result["payload"]["data"] == "event_data"
        
        # Check task
        task_result = next(r for r in results if r["type"] == "task")
        assert task_result["target"] == "worker"
        assert task_result["payload"]["action"] == "process"
        
        # Task message should have an ID for tracking
        assert task_msg.id is not None
    
    def test_list_subscribers(self, bus):
        """Test listing subscribers."""
        def handler1(msg): pass
        def handler2(msg): pass
        
        bus.subscribe("target1", handler1)
        bus.subscribe("target1", handler2)
        bus.subscribe("target2", handler1)
        bus.subscribe("*", handler1)
        
        counts = bus.list_subscribers()
        
        assert counts["target1"] == 2
        assert counts["target2"] == 1
        assert counts["*"] == 1
    
    @pytest.mark.asyncio
    async def test_get_stats(self, bus):
        """Test getting bus statistics."""
        # Subscribe and send some messages
        def handler(msg): pass
        bus.subscribe("target", handler)
        
        msg = BusMessage(type=MessageType.EVENT, source="test", target="target")
        await bus.send(msg)
        await asyncio.sleep(0.1)
        
        stats = bus.get_stats()
        
        assert "messages_sent" in stats
        assert "messages_delivered" in stats
        assert "delivery_errors" in stats
        assert "active_components" in stats
        assert "subscriber_counts" in stats
        
        assert stats["messages_sent"] >= 1
        assert stats["messages_delivered"] >= 1
        assert "test" in stats["active_components"]


class TestBusLogger:
    """Test BusLogger functionality."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary directory for logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    async def logger(self, temp_log_dir):
        """Create a BusLogger instance for testing."""
        logger = BusLogger(temp_log_dir)
        yield logger
        await logger.close()
    
    @pytest.mark.asyncio
    async def test_log_message(self, logger):
        """Test logging a message."""
        msg = BusMessage(
            type=MessageType.TASK,
            source="test_source",
            target="test_target",
            payload={"test": "data"}
        )
        
        await logger.log_message(msg)
        
        # Verify log file was created
        log_files = list(logger.log_dir.glob("*.jsonl"))
        assert len(log_files) > 0
        
        # Read back the logged message
        messages = []
        async for logged_msg in logger.read_messages(limit=10):
            messages.append(logged_msg)
        
        assert len(messages) == 1
        assert messages[0].id == msg.id
        assert messages[0].type == msg.type
        assert messages[0].payload == msg.payload
    
    @pytest.mark.asyncio
    async def test_read_messages_filtering(self, logger):
        """Test reading all messages from log file."""
        # Log messages with different types and sources
        msg1 = BusMessage(type=MessageType.TASK, source="brain1", target="target")
        msg2 = BusMessage(type=MessageType.EVENT, source="brain2", target="target")
        msg3 = BusMessage(type=MessageType.RESULT, source="brain1", target="target")
        
        await logger.log_message(msg1)
        await logger.log_message(msg2)
        await logger.log_message(msg3)
        
        # Read all messages
        all_messages = []
        async for msg in logger.read_messages(limit=10):
            all_messages.append(msg)
        
        assert len(all_messages) == 3
        
        # Check that we can identify different message types
        task_messages = [msg for msg in all_messages if msg.type == MessageType.TASK]
        event_messages = [msg for msg in all_messages if msg.type == MessageType.EVENT]
        result_messages = [msg for msg in all_messages if msg.type == MessageType.RESULT]
        
        assert len(task_messages) == 1
        assert len(event_messages) == 1
        assert len(result_messages) == 1
        
        # Check that we can filter by source manually
        brain1_messages = [msg for msg in all_messages if msg.source == "brain1"]
        assert len(brain1_messages) == 2
    
    @pytest.mark.asyncio
    async def test_log_rotation(self, logger):
        """Test that logs are properly rotated by day."""
        # This is a basic test - full rotation testing would require
        # mocking datetime or waiting for day change
        msg = BusMessage(type=MessageType.EVENT, source="test", target="test")
        await logger.log_message(msg)
        
        # Should have created a log file with today's date
        log_files = list(logger.log_dir.glob("bus-*.jsonl"))
        assert len(log_files) >= 1
        
        # File name should contain date
        filename = log_files[0].name
        assert "bus-" in filename
        assert filename.endswith(".jsonl")