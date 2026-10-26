import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, TypeVar, runtime_checkable


def get_current_timestamp() -> int:
    return time.time_ns()


class MessageRole(Enum):
    """
    Enum class for message.
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    # SUMMARY: 压缩摘要消息，存储用（不用于 LLM）
    SUMMARY = "summary"
    # SYS_SUMMARY: 系统摘要消息，用于 LLM（会被转换为 system role）
    SYS_SUMMARY = "sys_summary"
    UNSPECIFIED = "unspecified"

    @classmethod
    def value_of(cls, value: str) -> "MessageRole":
        """
        Get value of given mode.

        :param value: mode value
        :return: mode
        """
        for mode in cls:
            if mode.value == value:
                return mode
        return cls.UNSPECIFIED


T = TypeVar("T", bound="Serializable")


@runtime_checkable
class Serializable(Protocol):
    def dump(self) -> str:
        raise NotImplementedError

    @classmethod
    def load(cls: type[T], data: str) -> T:
        """从字符串反序列化对象"""
        raise NotImplementedError


# type alias, str is the name of the class,  callable is the deserializer
ConfigDeserializer = dict[str, Callable[[str], Serializable]]


@dataclass
class MessageChunk:
    """
    Message chunk model
    """

    content: str | bytes | Serializable
    require_upload: bool = False  # 是否需要上传
    media_id: str | None = None


@dataclass
class Message:
    """
    Message model
    """

    chunks: list[MessageChunk] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: int = field(default_factory=get_current_timestamp)
    meta_data: dict = field(default_factory=dict)
    role: MessageRole = MessageRole.UNSPECIFIED
