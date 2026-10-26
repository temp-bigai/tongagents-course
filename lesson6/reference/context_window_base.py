import copy
import json
import os
from abc import ABC, abstractmethod

from tongagents.agents.llm.messages import (
    BaseMessage,
    ModelInputMessage,
    ModelOutputMessage,
    PromptMessageContent,
    ToolResultMessage,
    UserPromptMessage,
)
from tongagents.entity import Event
from tongagents.utils.logger import logger


class ChatHistoryUnit:
    """
    对话历史单元 - 管理单轮对话的状态机

    状态机流程：
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │                             状态转换图                                       │
    ├─────────────────────────────────────────────────────────────────────────────┤
    │                                                                             │
    │  简单对话流程：                                                              │
    │  ┌─────────┐    ┌─────────────┐                                             │
    │  │  User   │───▶│  Assistant  │                                            │
    │  └─────────┘    └─────────────┘                                             │
    │                                                                             │
    │  工具调用流程：                                                              │
    │  ┌─────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────┐   │
    │  │  User   │──▶│  Tool Call      │──▶│ Tool Result │──▶│ Assistant   │   │
    │  │         │    │ (ModelOutput    │    │ (ToolResult │    │ (ModelOutput │  │
    │  │         │    │  with tool_     │    │  Message)   │    │  Message)    │  │
    │  │         │    │  call_messages) │    │             │    │             │  │
    │  └─────────┘    └─────────────────┘    └─────────────┘    └─────────────┘  │
    │                           │                       |                        │
    │                           └──── 循环调用工具───────┘                        │
    │                                                                             │
    └─────────────────────────────────────────────────────────────────────────────┘

    状态说明：
    • User: 用户输入消息 (UserPromptMessage)
    • Tool Call: 模型输出包含工具调用 (ModelOutputMessage with tool_call_messages)
    • Tool Result: 工具执行结果 (ToolResultMessage)
    • Assistant: 模型最终回复 (ModelOutputMessage without tool_call_messages)

    特点：
    - 支持简单的用户-助手对话
    - 支持复杂的工具调用流程，可循环调用多个工具
    - 每个对话单元维护完整的消息序列
    - 通过 is_done() 方法判断对话是否完成
    """

    def __init__(self, message_list: list[BaseMessage] | None = None):
        self.message_list: list[BaseMessage] = message_list or []

    def add_message(self, message):
        self.message_list.append(message)

    def is_done(self):
        if len(self.message_list) == 0:
            return False
        # When calling tools, there's also a response message (ModelOutputMessage),
        # but it's not a final state
        return (
            isinstance(self.message_list[-1], ModelOutputMessage)
            and self.message_list[-1].tool_call_messages is None
        )

    @classmethod
    def load(cls, data: str):
        json_data = json.loads(data)
        message_list = []
        for msg_data in json_data:
            msg_type = msg_data["type"]
            msg_class = globals()[msg_type]
            msg = msg_class.load(msg_data["data"])
            message_list.append(msg)
        return cls(message_list=message_list)

    def dump(self) -> str:
        msg_json_list = []
        for msg in self.message_list:
            msg_json_list.append({"type": msg.__class__.__name__, "data": msg.dump()})
        max_length = 65535 - 1
        try:
            max_length = int(os.getenv("MEMORY_MAX_LEN", "65535"))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to get MEMORY_MAX_LEN, use default value 65535 %s", e)
        curr_length = 0
        for msg in msg_json_list:
            curr_length += len(msg["type"]) + len(msg["data"])
        if curr_length < max_length:
            return json.dumps(msg_json_list, ensure_ascii=False)
        logger.warning(
            "Memory is too long, going to truncate, max_length: %d, curr_length: %d",
            max_length,
            curr_length,
        )
        # 尝试砍tool_result，不够就算了，近似估算
        del_length = max_length - curr_length
        for idx, msg in enumerate(self.message_list):
            if isinstance(msg, ToolResultMessage):
                fake_tool_result_msg = copy.deepcopy(msg)
                del_length -= len(fake_tool_result_msg.to_str())
                fake_tool_result_msg.content = ""
                msg_json_list[idx]["data"] = fake_tool_result_msg.dump()
                if del_length <= 0:
                    return json.dumps(msg_json_list, ensure_ascii=False)
        raise ValueError("Memory is too long, cannot truncate")

    def __str__(self) -> str:
        return self.dump()


class Query(Event):
    query: str | PromptMessageContent


class ContextWindowManager(ABC):
    def gen_context_window_with_query(self, query: Query) -> list[ModelInputMessage]:
        self.add_query(query)
        return self.get_prompt()

    def add_query(self, query: Query):
        """Add query to prompt"""
        user_message = UserPromptMessage(content=query.query)
        self.add_message(user_message)

    @abstractmethod
    def get_prompt(self) -> list[ModelInputMessage]:
        pass

    def add_message(self, message: ModelInputMessage, **kwargs):
        if isinstance(message, UserPromptMessage):
            self._add_user_query(message, **kwargs)
        elif isinstance(message, ToolResultMessage):
            self._add_tool_call(message, **kwargs)
        elif isinstance(message, ModelOutputMessage):
            self._add_model_output(message, **kwargs)
        else:
            raise ValueError(f"Invalid model input message type {type(message)}")

    @abstractmethod
    def _add_user_query(self, message: UserPromptMessage, **kwargs):
        pass

    @abstractmethod
    def _add_tool_call(self, message: ToolResultMessage, **kwargs):
        pass

    @abstractmethod
    def _add_model_output(self, message: ModelOutputMessage, **kwargs):
        pass
