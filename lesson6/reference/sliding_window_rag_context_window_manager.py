import traceback

from tongagents.agents.context_window.base import (
    ChatHistoryUnit,
    ContextWindowManager,
    Query,
)
from tongagents.agents.llm.messages import (
    ModelInputMessage,
    ModelOutputMessage,
    SystemPromptMessage,
    ToolResultMessage,
    UserPromptMessage,
)
from tongagents.memory.memory import MemoryBase, SimpleMemory
from tongagents.message.message import ConfigDeserializer, Message
from tongagents.utils.logger import logger


class RAGQuery(Query):
    rag_context: str | None = None


# Resolve forward ref: Query.query is typed as `str | PromptMessageContent`.
# PromptMessageContent is defined in tongagents.agents.llm.messages and is
# importable in this module. In some import orders (e.g. circular imports
# via react_agent_with_memory), pydantic may not have resolved the
# PromptMessageContent forward ref when RAGQuery is subclassed, causing
# `PydanticUserError: 'RAGQuery' is not fully defined`. Calling
# model_rebuild() explicitly forces pydantic to re-resolve all forward
# refs in the model graph after class definition.
RAGQuery.model_rebuild()


class SlidingWindowRAGContextWindowManager(ContextWindowManager):
    """
    RAG memory management mechanism based on sliding window

    The memory includes three parts:
    <system_prompt>
    <history_dialog (excluding rag content)>:
        may include multiple user, tool call, tool result, assistant
    <rag_result (possibly empty) + current user query>
    """

    def __init__(
        self,
        max_history_len: int = 5,
        system_prompt: str | None = None,
        memory: MemoryBase | None = None,
    ):
        self.system_prompt = (
            SystemPromptMessage(content=system_prompt) if system_prompt else None
        )
        self.rag_context = ""  # Temporarily stored rag results
        self.chat_history: list[ChatHistoryUnit] = []  # 内存中的缓存
        self.max_history_len = max_history_len

        self.memory = memory
        if self.memory is None:
            logger.debug("Using memory to store chat history")
            self.memory = SimpleMemory()

        self.chat_history = self._get_recent_chat_units(max_history_len)

    def _get_recent_chat_units(self, recent_n) -> list[ChatHistoryUnit]:
        msgs: list[Message] = self.memory.get_messages(
            recent_n=recent_n,
            config=ConfigDeserializer(
                {
                    ChatHistoryUnit.__name__: ChatHistoryUnit.load,
                }
            ),
        )
        chat_history = []
        for msg in msgs:
            if isinstance(msg.chunks[0].content, ChatHistoryUnit):
                chat_history.append(msg.chunks[0].content)
            else:
                raise ValueError(f"Invalid message type {type(msg)}")
        logger.info(
            "context_window.history_loaded: requested_recent=%s loaded_units=%s",
            recent_n,
            len(chat_history),
        )
        return chat_history

    def _save_chat_unit_to_memory(self, unit: ChatHistoryUnit):
        logger.info(
            "context_window.memory_saved: message_count=%s is_done=%s",
            len(getattr(unit, "message_list", []) or []),
            unit.is_done(),
        )
        logger.debug("context_window.memory_saved.detail: %s", unit)
        self.memory.add_chunk(content=unit)

    def add_query(self, query: RAGQuery):
        self._add_user_query(
            UserPromptMessage(content=query.query), rag_result=query.rag_context
        )

    def _add_user_query(
        self, message: UserPromptMessage, rag_result: str | None = None, **kwargs
    ):
        if not isinstance(message, UserPromptMessage):
            raise ValueError(f"Invalid user prompt message type {type(message)}")
        if len(self.chat_history) >= self.max_history_len:
            self.chat_history.pop(0)

        # 允许重复添加：当最后一个消息是 UserPromptMessage 时，
        # 用新的消息替换旧的（避免 WorkflowWithMemory 中的重复添加问题）
        if len(self.chat_history) != 0 and not self.chat_history[-1].is_done():
            last_msg = (
                self.chat_history[-1].message_list[-1]
                if self.chat_history[-1].message_list
                else None
            )
            if isinstance(last_msg, UserPromptMessage):
                logger.debug(
                    "[_add_user_query] UserPromptMessage detected, allowing replacement"
                )
                # 替换最后一个消息为新的消息（保留原有的 ChatHistoryUnit）
                self.chat_history[-1].message_list[-1] = message
                if rag_result:
                    self.rag_context = rag_result
                return
            logger.error(
                "Previous conversation not finished, cannot add new conversation, %s",
                self.chat_history[-1],
            )
            traceback.print_stack()
            raise ValueError(
                "Previous conversation not finished, cannot add new conversation"
            )

        unit = ChatHistoryUnit()
        unit.add_message(message)  # rag won't be stored here
        self.chat_history.append(unit)
        if rag_result:
            self.rag_context = rag_result

    def _add_tool_call(self, message: ToolResultMessage, **kwargs):
        if not isinstance(message, ToolResultMessage):
            raise ValueError(f"Invalid tool result message type {type(message)}")
        if len(self.chat_history) == 0:
            raise ValueError("No history dialog, cannot add tool result")
        if self.chat_history[-1].is_done():
            raise ValueError(
                "Previous conversation already finished, cannot add new conversation"
            )
        self.chat_history[-1].add_message(message)

    def _add_model_output(self, message: ModelOutputMessage, **kwargs):
        if not isinstance(message, ModelOutputMessage):
            raise ValueError(f"Invalid model output message type {type(message)}")
        if len(self.chat_history) == 0:
            raise ValueError("No history dialog, cannot add model output")
        if self.chat_history[-1].is_done():
            raise ValueError(
                "Previous conversation already finished, cannot add new conversation"
            )
        self.chat_history[-1].add_message(message)
        if self.chat_history[-1].is_done():
            logger.debug("a new ChatUnit is DONE, save to memory")
            self._save_chat_unit_to_memory(self.chat_history[-1])

    def get_prompt(self) -> list[ModelInputMessage]:
        return self._build_all_messages()

    def _build_all_messages(self) -> list[ModelInputMessage]:
        """
        Build all messages including system prompt,
        history, and enhanced user query
        """
        messages: list[ModelInputMessage] = []
        if self.system_prompt:
            messages.append(self.system_prompt)

        for unit in self.chat_history:
            messages.extend(unit.message_list)

        if self.rag_context:
            # Find the last UserPromptMessage from the end
            for i in range(len(messages) - 1, -1, -1):
                if isinstance(messages[i], UserPromptMessage):
                    original_content = messages[i].content
                    new_content = original_content

                    if self.rag_context:
                        new_content = (
                            "参考知识库中的信息："
                            + self.rag_context
                            + "\n\n"
                            + f"用户的问题或指令是：{original_content}"
                        )

                    messages[i] = UserPromptMessage(content=new_content)
                    break
        return messages
