from abc import ABC, abstractmethod

from tongagents.logtrace import TracedAs
from tongagents.memory.engine import (
    DEFAULT_AGENT_ID,
    DEFAULT_SESSION_ID,
    StoreEngine,
)
from tongagents.memory.sql_engine import DefaultSQLStoreEngine
from tongagents.message.message import (
    ConfigDeserializer,
    Message,
    MessageChunk,
    MessageRole,
    Serializable,
)
from tongagents.utils.media import MediaFileManager

DEFAULT_MEDIA_MANAGER = MediaFileManager()


class MemoryBase(ABC):
    @abstractmethod
    def add_message(self, message: Message) -> None:
        """
        Abstract interface
        Add message to memory

        Args:
            message (Message): The message to add
        """

    @abstractmethod
    def add_chunk(
        self,
        content: Serializable,
        role: MessageRole = MessageRole.UNSPECIFIED,
        require_upload: bool = False,
    ) -> None:
        """
        User add one chunk to memory
        Implicit create a new message with the content chunk

        Args:
            content (Serializable): The content of the chunk
            role (MessageRole): The role of the message
            require_upload (bool): If True, the content will be uploaded to
            media manager
        """

    @abstractmethod
    def add_chunks(self, chunks: list[MessageChunk], role=MessageRole.UNSPECIFIED):
        """
        Add multiple message chunks to memory.

        This method implicitly creates a new message using the provided chunks
        and assigns a role to the message. It is an abstract method that must
        be implemented by subclasses.

        Args:
            chunks (list[MessageChunk]): A list of message chunks to be added.
            role (MessageRole): The role assigned to the message. Default is
                MessageRole.UNSPECIFIED.
        """

    @abstractmethod
    def add_messages(self, messages: list[Message]):
        """
        Abstract method to add multiple messages to memory.

        This method serves as an interface that must be implemented by any
        subclass to handle the storage of multiple messages.

        Args:
            messages (list[Message]): A list of Message objects to be added
                                      to the memory.
        """

    @abstractmethod
    def get_messages(
        self,
        session_id: str | None = None,
        recent_n: int | None = None,
        **kwargs,
    ) -> list[Message]:
        """
        Retrieve messages from memory.

        This method should be implemented by subclasses to retrieve messages
        from the memory store. It allows filtering by agent_id, session_id,
        and the number of recent messages.

        Args:
            session_id (str | None): The ID of the session to filter messages by.
                Defaults to None.
            recent_n (int | None): The number of recent messages to retrieve.
                Defaults to None.
            **kwargs: Additional keyword arguments for custom filtering.

        Returns:
            list[Message]: A list of Message objects retrieved from memory.
        """

    @abstractmethod
    def clear(self):
        """
        abstract interface
        Clear memory
        """


class SimpleMemory(MemoryBase):
    """
    agent running memory
    """

    def __init__(self):
        self.store = []

    @TracedAs("SimpleMemory.get_messages", record_params=True, record_result=True)
    def get_messages(
        self,
        session_id: str | None = None,
        recent_n: int | None = None,
        **kwargs,
    ):
        """
        get all messages from the store
        """
        return self.store

    def clear(self):
        self.store = []

    @TracedAs("SimpleMemory.get_contents", record_params=True, record_result=True)
    def get_contents(
        self, config: ConfigDeserializer | None = None
    ) -> list[Serializable]:
        """
        Get all the content of chunks in messages in the memory.

        This method iterates over all the messages in memory and collects
        the content of all the chunks in all the messages. The content
        is returned as a flat list of all the chunk contents.

        Returns:
            list[Serializable]: A list of all the chunk contents in memory.
        """
        contents = []
        for message in self.store:
            for chunk in message.chunks:
                contents.append(chunk.content)
        return contents

    def add_message(self, message: Message):
        """
        add one message to memory
        """
        self.store.append(message)

    def add_chunk(
        self,
        content: Serializable,
        role: MessageRole = MessageRole.UNSPECIFIED,
        require_upload: bool = False,
    ):
        """
        user add one chunk to memory
        implicit create a new message with the content chunk
        """
        chunk = MessageChunk(content=content)
        message = Message(chunks=[chunk], role=role)
        self.add_message(message)

    def add_chunks(self, chunks: list[MessageChunk], role=MessageRole.UNSPECIFIED):
        """
        user add multiple chunks to memory
        implicit create a new message with the content chunks
        """
        message = Message(chunks=chunks, role=role)
        self.add_message(message)

    def add_messages(self, messages: list[Message]):
        self.store.extend(messages)


class PersistenceMemory(MemoryBase):
    """
    support for persistence memory
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        engine: StoreEngine | None = None,
        media_manager: MediaFileManager = DEFAULT_MEDIA_MANAGER,
    ):
        if engine is None:
            engine = DefaultSQLStoreEngine.get_instance()
        self.engine = engine
        self.meta_data = {}
        self.meta_data["agent_id"] = agent_id
        self.meta_data["session_id"] = session_id
        self.media_manager = media_manager

    def upload(self, message: Message):
        """
        upload some rich media content of message to media manager
        """
        for index, chunk in enumerate(message.chunks):
            if chunk.require_upload and chunk.content:
                blob_data = chunk.content
                if isinstance(chunk.content, Serializable):
                    blob_data = chunk.content.dump()
                media_id = self.media_manager.upload_file(
                    user_id=self.meta_data.get("agent_id", DEFAULT_AGENT_ID),
                    content=blob_data,
                    file_name=message.id + "_" + str(index),
                )
                chunk.media_id = media_id

    def add_chunk(
        self,
        content: Serializable,
        role: MessageRole = MessageRole.UNSPECIFIED,
        require_upload: bool = False,
        media_id: str | None = None,
    ):
        """
        Add a new message chunk to the memory store.

        This function creates a new MessageChunk with the given content and
        role, then wraps it into a Message object and adds it to the memory.

        Args:
            content (Serializable): The content of the chunk.
            role (MessageRole): The role of the message. Defaults to UNSPECIFIED.
            require_upload (bool): Flag indicating if the content needs to be uploaded.
            media_id (str | None): Optional media ID associated with the chunk.
        """
        # Create a new message chunk with the provided content and upload requirement
        chunk = MessageChunk(
            content=content,
            require_upload=require_upload,
        )

        # Create a message with the chunk and assign the specified role and metadata
        message = Message(
            chunks=[chunk],
            role=role,
            meta_data=self.meta_data,
        )

        # Add the message to memory
        self.add_message(message)

    def add_messages(self, messages: list[Message]):
        for message in messages:
            message.meta_data = self.meta_data
        self.engine.write(messages)

    def add_message(self, message: Message):
        message.meta_data = self.meta_data
        self.upload(message)
        self.engine.write([message])

    def get_messages(
        self,
        session_id: str | None = None,
        recent_n: int | None = None,
        config: ConfigDeserializer | None = None,
        **kwargs,
    ) -> list[Message]:
        """
        get all messages from the store, filter by agent_id and session_id and recent_n
        """
        agent_id = self.meta_data.get("agent_id", DEFAULT_AGENT_ID)
        if session_id is None:
            session_id = self.meta_data.get("session_id", DEFAULT_SESSION_ID)
        messages = self.engine.read(agent_id, session_id, recent_n, config, **kwargs)
        self.fill_back_content_from_media(messages)
        return messages

    def fill_back_content_from_media(self, messages: list[Message]):
        """
        Fill back the content of chunks by querying the media manager.
        This method is used when the content of chunks is not available in the memory,
        and the media manager is configured to store the content of chunks.
        """
        for message in messages:
            for chunk in message.chunks:
                if chunk.media_id is not None:
                    # Get the content of the chunk from the media manager
                    _, chunk.content = self.media_manager.get_file(chunk.media_id)

    def get_contents(
        self,
        session_id: str | None = None,
        recent_n: int | None = None,
        config: ConfigDeserializer | None = None,
        **kwargs,
    ):
        messages = self.get_messages(session_id, recent_n, config, **kwargs)
        return [
            chunk.content
            for message in messages
            for chunk in message.chunks
            if chunk.content is not None
        ]

    def clear(self):
        # 只清理当前session的数据，而不是整个数据库
        session_id = self.meta_data.get("session_id", DEFAULT_SESSION_ID)
        self.engine.delete(session_id)

    def add_chunks(self, chunks: list[MessageChunk], role=MessageRole.UNSPECIFIED):
        message = Message(chunks=chunks, role=role)
        self.engine.write([message])

    def delete(self, session_id: str):
        """
        delete by session_id
        """
        self.engine.delete(session_id)
