"""Mock LLM Provider for BigBrain demo and testing."""

import asyncio
import random
import re
from typing import AsyncIterator, Union

from .provider import LLMProvider


class MockLLMProvider(LLMProvider):
    """
    Mock LLM provider that simulates realistic responses with streaming.
    
    Generates contextually appropriate responses based on prompt patterns.
    Simulates realistic delays (~50ms per token) for demo purposes.
    """
    
    def __init__(self, token_delay_ms: int = 50, realistic_responses: bool = True):
        """
        Initialize mock provider.
        
        Args:
            token_delay_ms: Delay between tokens in streaming mode
            realistic_responses: Generate contextual responses vs random text
        """
        self.token_delay_ms = token_delay_ms
        self.realistic_responses = realistic_responses
        
        # Response templates for different prompt patterns
        self._code_templates = [
            "```python\ndef process_data(data):\n    \"\"\"Process the input data.\"\"\"\n    result = []\n    for item in data:\n        if item.get('valid'):\n            result.append(transform(item))\n    return result\n```\n\nThis function processes the data by filtering valid items and transforming them.",
            "```python\nimport asyncio\nimport logging\n\nclass DataProcessor:\n    def __init__(self):\n        self.logger = logging.getLogger(__name__)\n    \n    async def process(self, items):\n        self.logger.info(f\"Processing {len(items)} items\")\n        results = []\n        for item in items:\n            processed = await self.transform_item(item)\n            results.append(processed)\n        return results\n```",
            "```python\nfrom typing import List, Optional\nfrom dataclasses import dataclass\n\n@dataclass\nclass TaskResult:\n    success: bool\n    data: Optional[dict] = None\n    error: Optional[str] = None\n\ndef execute_task(task_config: dict) -> TaskResult:\n    try:\n        # Process the task\n        result_data = handle_task(task_config)\n        return TaskResult(success=True, data=result_data)\n    except Exception as e:\n        return TaskResult(success=False, error=str(e))\n```"
        ]
        
        self._research_templates = [
            "Based on my research, here are the key findings:\n\n1. **Primary considerations**: The approach should prioritize scalability and maintainability.\n\n2. **Best practices**: Industry standards recommend using established patterns and frameworks.\n\n3. **Implementation strategy**: Start with a minimal viable solution and iterate based on feedback.\n\n4. **Risk factors**: Consider potential bottlenecks and plan for horizontal scaling.\n\nWould you like me to dive deeper into any of these areas?",
            "I've analyzed the available information and here's what I discovered:\n\n**Current landscape**: The field is rapidly evolving with several competing approaches.\n\n**Key players**: Major companies are investing heavily in this space.\n\n**Technical requirements**: Solutions need to balance performance with resource efficiency.\n\n**Recommended approach**: A hybrid strategy that combines proven techniques with innovative elements.\n\nThis research suggests focusing on modular architecture for flexibility.",
            "My research indicates several important trends:\n\n• **Emerging patterns**: New methodologies are showing promising results\n• **Performance metrics**: Current benchmarks suggest 20-30% improvement is achievable\n• **Cost considerations**: Implementation requires initial investment but long-term benefits\n• **Timeline**: Typical deployment takes 3-6 months for full integration\n\nThe evidence supports moving forward with a phased approach."
        ]
        
        self._conversation_templates = [
            "I understand what you're looking for. Let me break this down into manageable pieces and help you work through it step by step.",
            "That's an interesting challenge! I can help you approach this systematically. What specific aspect would you like to focus on first?",
            "I see what you're trying to accomplish. Based on your requirements, I'd suggest we start with the core functionality and then expand from there.",
            "Good question! This is a common scenario, and there are several proven approaches we can consider. Let me walk you through the options.",
            "I'm happy to help with that! From experience, this type of task usually involves a few key steps. Let's tackle them one at a time.",
            "Absolutely! This sounds like a great project. I think the best way forward is to establish clear objectives first, then build incrementally.",
            "I can definitely assist with this. Let me share some insights that might be helpful for your specific situation.",
            "That makes sense! I've worked through similar challenges before. Here's how I'd recommend approaching it..."
        ]
        
        # Intents and responses for front brain
        self._intent_responses = {
            "greeting": ["Hello! How can I help you today?", "Hi there! What would you like to work on?", "Good to see you! What can I assist with?"],
            "task_request": ["I'll help you with that task. Let me break it down into steps.", "Sure! I can handle that for you. Let me get started.", "I'll take care of that. Give me a moment to process it."],
            "question": ["Let me think about that and get you a comprehensive answer.", "Good question! I'll research that for you.", "I'll look into that and provide you with detailed information."],
            "help": ["I'm here to help! You can ask me to code, research, analyze, or just chat.", "I can assist with various tasks like programming, research, analysis, and more. What do you need?"],
            "status": ["Everything is running smoothly! All systems are operational.", "All good here! The brains are ready and waiting for tasks.", "Status: All systems green. Ready to help!"]
        }
    
    async def complete(
        self, 
        prompt: str, 
        model: str = "mock-gpt-4", 
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> Union[str, AsyncIterator[str]]:
        """Generate completion for the given prompt."""
        response_text = self._generate_contextual_response(prompt)
        
        if stream:
            return self._stream_response(response_text)
        else:
            # Simulate processing delay
            await asyncio.sleep(0.5 + random.uniform(0, 0.3))
            return response_text
    
    async def chat_complete(
        self,
        messages: list[dict],
        model: str = "mock-gpt-4",
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> Union[str, AsyncIterator[str]]:
        """Generate chat completion for the given messages."""
        # Extract the last user message for context
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        if user_messages:
            prompt = user_messages[-1].get("content", "")
        else:
            prompt = "Hello"
        
        response_text = self._generate_contextual_response(prompt, is_chat=True)
        
        if stream:
            return self._stream_response(response_text)
        else:
            await asyncio.sleep(0.3 + random.uniform(0, 0.2))
            return response_text
    
    def get_available_models(self) -> list[str]:
        """Get list of available mock models."""
        return ["mock-gpt-4", "mock-gpt-3.5", "mock-claude-3", "mock-llama-70b"]
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Rough estimate: ~4 characters per token
        return max(1, len(text) // 4)
    
    def _generate_contextual_response(self, prompt: str, is_chat: bool = False) -> str:
        """Generate contextually appropriate response based on prompt patterns."""
        if not self.realistic_responses:
            return self._generate_random_response()
        
        prompt_lower = prompt.lower()
        
        # Check for intent patterns (for front brain)
        if is_chat:
            if any(word in prompt_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon"]):
                return random.choice(self._intent_responses["greeting"])
            elif any(word in prompt_lower for word in ["help", "what can you", "how do you"]):
                return random.choice(self._intent_responses["help"])
            elif any(word in prompt_lower for word in ["status", "how are", "everything ok"]):
                return random.choice(self._intent_responses["status"])
            elif "?" in prompt:
                return random.choice(self._intent_responses["question"])
            else:
                return random.choice(self._intent_responses["task_request"])
        
        # Check for code-related prompts
        if any(keyword in prompt_lower for keyword in 
               ["code", "function", "python", "class", "def ", "import", "script", "program"]):
            return random.choice(self._code_templates)
        
        # Check for research-related prompts
        if any(keyword in prompt_lower for keyword in 
               ["research", "analyze", "investigate", "find out", "look up", "study"]):
            return random.choice(self._research_templates)
        
        # Default to conversation
        return random.choice(self._conversation_templates)
    
    def _generate_random_response(self) -> str:
        """Generate random demo text for non-realistic mode."""
        words = [
            "innovative", "scalable", "efficient", "robust", "flexible", "comprehensive",
            "advanced", "optimized", "streamlined", "intelligent", "adaptive", "seamless",
            "solution", "system", "framework", "architecture", "implementation", "approach",
            "methodology", "strategy", "process", "workflow", "pipeline", "integration"
        ]
        
        sentences = []
        for _ in range(random.randint(2, 4)):
            sentence_words = random.sample(words, random.randint(4, 8))
            sentence = "This " + " ".join(sentence_words) + " provides excellent results."
            sentences.append(sentence)
        
        return " ".join(sentences)
    
    async def _stream_response(self, response_text: str) -> AsyncIterator[str]:
        """Stream response text with realistic delays."""
        # Split into words for more natural streaming
        words = response_text.split()
        
        for i, word in enumerate(words):
            # Add space before word (except first)
            if i > 0:
                word = " " + word
            
            # Stream word in smaller chunks sometimes for realism
            if len(word) > 10 and random.random() < 0.3:
                # Stream long words in parts
                mid = len(word) // 2
                yield word[:mid]
                await asyncio.sleep(self.token_delay_ms / 1000.0)
                yield word[mid:]
            else:
                yield word
            
            # Variable delay between words
            base_delay = self.token_delay_ms / 1000.0
            delay = base_delay + random.uniform(0, base_delay * 0.5)
            await asyncio.sleep(delay)
            
            # Occasional longer pauses at sentence boundaries
            if word.endswith(('.', '!', '?', '\n')):
                await asyncio.sleep(base_delay * 2)