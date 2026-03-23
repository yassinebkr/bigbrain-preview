"""Voice Brain - Fast conversational model for natural spoken responses.

This is NOT a text-to-speech wrapper. The Voice Brain has its own fast LLM
(Sonnet-class) that generates responses specifically designed for speech:
- Short, natural sentences (not walls of text)
- Conversational tone (not robotic status dumps)
- Context-aware pausing and emphasis
- Knows when to be brief vs detailed based on voice context

The Voice Brain sits between the Front Brain and the TTS engine:
  User speaks → STT → Voice Brain (fast LLM) → TTS → User hears

It can also be triggered by bus events that the Front Brain decides
are worth communicating to the user verbally.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from ..bus.bus import MessageBus
from ..bus.message import BusMessage, MessageType, Priority
from ..llm.provider import LLMProvider


# System prompt tuned for voice output — concise, natural, spoken
VOICE_SYSTEM_PROMPT = """\
You are BigBrain's voice. You speak naturally, like a smart colleague talking out loud.

Rules for voice responses:
- Keep sentences SHORT (8-15 words). Long sentences are hard to follow in audio.
- Use natural speech patterns: "So...", "Alright,", "Here's what happened —"
- Never use markdown, bullet lists, code blocks, or formatting. This is SPEECH.
- Never say "asterisk" or describe formatting. Just talk normally.
- When reporting results, summarize — don't dump raw output.
- Numbers: say "about forty-two percent" not "41.7%"
- If code ran successfully, say what it DID, not what the code LOOKS like.
- Match the user's energy. Casual question → casual answer. Urgent → direct.
- Use filler words sparingly but naturally: "okay", "right", "so"
- If you don't know something, say so in one sentence. Don't ramble.
- NEVER start with "I" — vary your openings.

You have context about the BigBrain system state. Use it naturally:
- "The Python brain just finished that fibonacci thing. Got the right output."
- "Heads up — your research task hit an error. Want me to look into it?"
- "All quiet on the workspace front. What's next?"

Keep responses under 3 sentences for status updates.
For actual questions, be as thorough as needed but still conversational.
"""


class VoiceBrain:
    """
    Fast conversational LLM for generating natural spoken responses.

    Uses a cheaper/faster model (Sonnet-class) than the Front Brain (Opus)
    because voice needs low latency more than deep reasoning.

    Responsibilities:
    - Convert Front Brain decisions into natural speech
    - Generate spoken responses to user voice input
    - Summarize bus events into speakable notifications
    - Maintain a short voice conversation history (last 10 turns)
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        voice_model: str = None,
        bus: Optional[MessageBus] = None,
    ):
        """
        Initialize the Voice Brain.

        Args:
            llm_provider: LLM provider (litellm, OAuth, or mock)
            voice_model: Model to use for voice responses.
                         Defaults to a fast Sonnet-class model.
                         Should be cheaper/faster than Front Brain's Opus.
            bus: Optional bus for receiving events to vocalize
        """
        self.llm_provider = llm_provider
        self.bus = bus

        # Pick a fast model — voice needs latency, not deep reasoning
        self.voice_model = voice_model or self._pick_fast_model()

        # Short conversation history for voice context (not the full chat)
        self._voice_history: List[Dict[str, str]] = []
        self._max_history = 10

        # Recent bus events for context (last N events worth mentioning)
        self._recent_events: List[Dict[str, Any]] = []
        self._max_events = 5

        # State
        self._running = False

    def _pick_fast_model(self) -> str:
        """Pick the fastest available model for voice responses."""
        # Check what the provider supports
        provider_type = type(self.llm_provider).__name__

        if provider_type == "AnthropicOAuthProvider":
            # OAuth → use Sonnet (fast, good at conversation)
            return "claude-sonnet-4-20250514"
        elif provider_type == "LiteLLMProvider":
            # litellm → use whatever's cheapest/fastest
            return "gpt-4o-mini"
        else:
            # Mock or unknown → use default
            return "gpt-4o-mini"

    async def start(self) -> None:
        """Start the Voice Brain."""
        if self._running:
            return
        self._running = True

        # Subscribe to bus events we might want to vocalize
        if self.bus:
            self.bus.subscribe("*", self._on_bus_event)

    async def stop(self) -> None:
        """Stop the Voice Brain."""
        if not self._running:
            return
        self._running = False
        if self.bus:
            self.bus.unsubscribe("*", self._on_bus_event)

    async def respond_to_voice(self, user_text: str) -> str:
        """
        Generate a spoken response to user voice input.

        This is the main entry point for voice conversations.
        Uses the fast voice model with conversation history.

        Args:
            user_text: What the user said (from STT)

        Returns:
            Natural spoken response text (ready for TTS)
        """
        # Add to voice history
        self._voice_history.append({"role": "user", "content": user_text})
        self._trim_history()

        # Build context-aware messages
        messages = self._build_voice_messages()

        try:
            response = await self.llm_provider.chat_complete(
                messages=messages,
                model=self.voice_model,
                stream=False,
                max_tokens=150,  # Voice responses should be SHORT
                temperature=0.8,  # Slightly more creative for natural speech
            )

            # Store response in voice history
            self._voice_history.append({"role": "assistant", "content": response})
            self._trim_history()

            return response

        except Exception as e:
            return f"Sorry, hit a snag. {e}"

    async def stream_response(self, user_text: str):
        """
        Stream a spoken response token by token.

        For real-time TTS that starts speaking before the full
        response is generated. Yields sentence fragments.

        Args:
            user_text: What the user said

        Yields:
            str: Sentence fragments ready for TTS
        """
        self._voice_history.append({"role": "user", "content": user_text})
        self._trim_history()

        messages = self._build_voice_messages()

        try:
            stream = await self.llm_provider.chat_complete(
                messages=messages,
                model=self.voice_model,
                stream=True,
                max_tokens=150,
                temperature=0.8,
            )

            buffer = []
            full_response = []

            async for chunk in stream:
                buffer.append(chunk)
                full_response.append(chunk)

                # Yield at sentence boundaries for natural TTS pacing
                text = "".join(buffer)
                if any(text.rstrip().endswith(p) for p in [".", "!", "?", "—", ":"]):
                    yield text
                    buffer = []

            # Yield any remaining text
            if buffer:
                yield "".join(buffer)

            # Store full response
            self._voice_history.append({
                "role": "assistant",
                "content": "".join(full_response),
            })
            self._trim_history()

        except Exception as e:
            yield f"Sorry, hit a snag."

    async def vocalize_event(self, event_summary: str) -> str:
        """
        Convert a bus event summary into natural speech.

        Called by the Front Brain when it decides an event is worth
        telling the user about verbally.

        Args:
            event_summary: Brief description of what happened
                          (e.g. "PythonBrain completed fibonacci task, output: 0 1 1 2 3")

        Returns:
            Natural spoken notification
        """
        prompt = f"""Convert this system event into a brief, natural spoken notification.
One or two sentences max. Don't be robotic.

Event: {event_summary}"""

        try:
            response = await self.llm_provider.chat_complete(
                messages=[
                    {"role": "system", "content": VOICE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=self.voice_model,
                stream=False,
                max_tokens=80,
                temperature=0.8,
            )
            return response
        except Exception:
            # Fallback: just clean up the summary
            return event_summary.split(",")[0] + "."

    async def vocalize_result(self, task_description: str, result: Dict[str, Any]) -> str:
        """
        Generate a natural spoken summary of a task result.

        Args:
            task_description: What the user originally asked for
            result: The task result payload

        Returns:
            Natural spoken summary
        """
        success = result.get("success", False)
        data = result.get("data", result)

        if success and isinstance(data, dict):
            stdout = data.get("stdout", "").strip()[:300]
            stderr = data.get("stderr", "").strip()[:100]
            exit_code = data.get("exit_code", -1)

            context = f"""The user asked: "{task_description}"
Result: {'Success' if exit_code == 0 else 'Failed'} (exit code {exit_code})
Output: {stdout if stdout else '(no output)'}
{f'Errors: {stderr}' if stderr else ''}"""
        else:
            error = data.get("error", str(data)) if isinstance(data, dict) else str(data)
            context = f"""The user asked: "{task_description}"
Result: Failed — {error}"""

        prompt = f"""Summarize this task result as a brief spoken response.
Say what was done and the key result. Two sentences max.

{context}"""

        try:
            response = await self.llm_provider.chat_complete(
                messages=[
                    {"role": "system", "content": VOICE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                model=self.voice_model,
                stream=False,
                max_tokens=100,
                temperature=0.7,
            )
            return response
        except Exception:
            if success:
                return "That's done. Ran without issues."
            else:
                return "That didn't work out. Want me to try again?"

    def _build_voice_messages(self) -> List[Dict[str, str]]:
        """Build the message list for the voice LLM call."""
        messages = [{"role": "system", "content": VOICE_SYSTEM_PROMPT}]

        # Add recent event context if any
        if self._recent_events:
            event_context = "\n".join(
                f"- {e['summary']}" for e in self._recent_events[-3:]
            )
            messages.append({
                "role": "system",
                "content": f"Recent system activity:\n{event_context}",
            })

        # Add voice conversation history
        messages.extend(self._voice_history)

        return messages

    def _trim_history(self) -> None:
        """Keep voice history short — voice context doesn't need 20 turns."""
        if len(self._voice_history) > self._max_history:
            self._voice_history = self._voice_history[-self._max_history:]

    async def _on_bus_event(self, message: BusMessage) -> None:
        """
        Track notable bus events for voice context.

        Doesn't vocalize them — just stores them so the Voice Brain
        knows what's been happening when the user asks.
        """
        if not self._running:
            return
        if message.source == "voice_brain":
            return

        event_type = message.payload.get("event", "")

        # Only track notable events
        notable = [
            "brain.complete", "brain.error", "brain.blocked",
            "system.ready", "task.timeout",
        ]
        if not any(n in event_type for n in notable):
            return

        self._recent_events.append({
            "time": time.time(),
            "source": message.source,
            "event": event_type,
            "summary": f"{message.source}: {event_type}",
        })

        # Keep only recent events
        if len(self._recent_events) > self._max_events:
            self._recent_events = self._recent_events[-self._max_events:]

    def get_status(self) -> Dict[str, Any]:
        """Get Voice Brain status."""
        return {
            "running": self._running,
            "model": self.voice_model,
            "history_turns": len(self._voice_history),
            "recent_events": len(self._recent_events),
        }
