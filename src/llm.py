from __future__ import annotations

from typing import Any

from src.config import LLMSettings
from src.utils.json_utils import extract_json_object


class HelloAgentRuntime:
    """Thin runtime around the local hello_agents package.

    Main path:
    HelloAgentsLLM -> SimpleAgent.run()

    Reflection path:
    HelloAgentsLLM -> ReflectionAgent.run()

    The class intentionally does not implement a separate HTTP fallback. If the
    project says it uses hello_agents, the LLM calls should really go through
    hello_agents. Higher workflow layers provide deterministic demo fallbacks
    when no API key is configured.
    """

    def __init__(self, settings: LLMSettings):
        self.settings = settings
        self._llm: Any | None = None
        self._simple_agent_cls: Any | None = None
        self._reflection_agent_cls: Any | None = None
        self._context_builder_cls: Any | None = None
        self._context_packet_cls: Any | None = None
        self.load_error: str = ""
        self._load_hello_agents()

    @property
    def available(self) -> bool:
        key_ok = bool(self.settings.api_key and self.settings.api_key != "your-key")
        return self.settings.enabled and key_ok and self._llm is not None

    @property
    def provider_label(self) -> str:
        if not self.available:
            return "offline-demo"
        return f"{self.settings.provider}:{self.settings.model}"

    def run_simple(
        self,
        *,
        name: str,
        system_prompt: str,
        user_prompt: str,
        tool_registry: Any | None = None,
        max_tool_iterations: int = 2,
    ) -> str:
        if not self.available or self._simple_agent_cls is None:
            return ""

        agent = self._simple_agent_cls(
            name=name,
            llm=self._llm,
            system_prompt=system_prompt,
            tool_registry=tool_registry,
            enable_tool_calling=tool_registry is not None,
        )
        return str(
            agent.run(
                user_prompt,
                max_tool_iterations=max_tool_iterations,
                temperature=self.settings.temperature,
            )
        )

    def run_json(
        self,
        *,
        name: str,
        system_prompt: str,
        user_prompt: str,
        tool_registry: Any | None = None,
        max_tool_iterations: int = 2,
    ) -> dict[str, Any] | None:
        text = self.run_simple(
            name=name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_registry=tool_registry,
            max_tool_iterations=max_tool_iterations,
        )
        return extract_json_object(text)

    def run_reflection(
        self,
        *,
        name: str,
        task: str,
        custom_prompts: dict[str, str] | None = None,
        max_iterations: int = 2,
    ) -> str:
        if not self.available or self._reflection_agent_cls is None:
            return ""

        agent = self._reflection_agent_cls(
            name=name,
            llm=self._llm,
            max_iterations=max_iterations,
            custom_prompts=custom_prompts,
        )
        return str(agent.run(task, temperature=self.settings.temperature))

    def build_context(
        self,
        *,
        user_query: str,
        system_instructions: str,
        packets: list[tuple[str, dict[str, Any]]],
        max_tokens: int = 5000,
    ) -> str:
        if self._context_builder_cls is None or self._context_packet_cls is None:
            body = "\n\n".join(content for content, _ in packets)
            return f"{system_instructions}\n\n当前任务：{user_query}\n\n{body}"

        from hello_agents.context import ContextConfig

        context_packets = [
            self._context_packet_cls(content=content, metadata=metadata)
            for content, metadata in packets
            if content.strip()
        ]
        builder = self._context_builder_cls(config=ContextConfig(max_tokens=max_tokens, min_relevance=0.0))
        return builder.build(
            user_query=user_query,
            system_instructions=system_instructions,
            additional_packets=context_packets,
        )

    def _load_hello_agents(self) -> None:
        try:
            from hello_agents import HelloAgentsLLM
            from hello_agents.agents.reflection_agent import ReflectionAgent
            from hello_agents.agents.simple_agent import SimpleAgent
            from hello_agents.context import ContextBuilder, ContextPacket

            self._llm = HelloAgentsLLM(
                api_key=self.settings.api_key,
                model=self.settings.model,
                base_url=self.settings.base_url,
                provider=self.settings.provider if self.settings.provider != "openai-compatible" else "auto",
                temperature=self.settings.temperature,
                timeout=int(self.settings.timeout_seconds),
            )
            self._simple_agent_cls = SimpleAgent
            self._reflection_agent_cls = ReflectionAgent
            self._context_builder_cls = ContextBuilder
            self._context_packet_cls = ContextPacket
        except Exception as exc:
            self._llm = None
            self._simple_agent_cls = None
            self._reflection_agent_cls = None
            self._context_builder_cls = None
            self._context_packet_cls = None
            self.load_error = str(exc)
