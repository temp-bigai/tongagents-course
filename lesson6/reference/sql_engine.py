import json
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,  # 添加 Index 导入
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    Session,
    declarative_base,
    joinedload,
    relationship,
    scoped_session,
    sessionmaker,
)

from tongagents.memory.engine import DEFAULT_AGENT_ID, DEFAULT_SESSION_ID, StoreEngine
from tongagents.message.message import (
    ConfigDeserializer,
    Message,
    MessageChunk,
    MessageRole,
    Serializable,
)
from tongagents.utils.logger import logger
from tongagents.utils.sql import DEFAULT_POOL_SIZE, DEFAULT_SQL_URL, DatabaseEngine
from tongagents.utils.tracer import tracer

Base = declarative_base()


class MessageModel(Base):
    __tablename__ = "agent_memory"
    id = Column(String(255), primary_key=True)
    agent_id = Column(String(255))
    session_id = Column(String(255))
    media_id = Column(String(255), nullable=True)
    timestamp = Column(BigInteger)
    meta_data = Column(String(1024))
    role = Column(String(20))
    chunks = relationship(
        "ChunkModel", back_populates="agent_memory", cascade="all, delete-orphan"
    )

    # 添加索引以提高查询性能
    __table_args__ = (
        Index("idx_agent_session_timestamp", "agent_id", "session_id", "timestamp"),
    )


class ChunkModel(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text)
    require_upload = Column(Boolean, default=False)
    media_id = Column(String(255), nullable=True)
    serial_name = Column(String(255))
    belongs_to = Column(String(255), ForeignKey("agent_memory.id"))
    agent_memory = relationship("MessageModel", back_populates="chunks")


class SQLStoreEngine(StoreEngine):
    def __init__(self, url: str | None = None, pool_size=DEFAULT_POOL_SIZE, echo=False):
        self.url = url or DEFAULT_SQL_URL
        self.engine = DatabaseEngine.get_engine(
            url=self.url, pool_size=pool_size, echo=echo
        )
        # 使用 scoped_session 管理会话
        session_factory = sessionmaker(bind=self.engine)
        self.scoped_session = scoped_session(session_factory)

        # 创建表结构
        Base.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self):
        """提供事务范围的session上下文管理器"""
        session = self.scoped_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            self.scoped_session.remove()

    def write(self, messages: list[Message]):
        self._insert(messages)

    def _insert(self, messages: list[Message]):
        if not messages:
            return

        msg_dicts = []
        chunk_dicts = []
        for message in messages:
            msg_dict = {
                "id": message.id,
                "meta_data": json.dumps(message.meta_data),
                "timestamp": message.timestamp,
                "role": message.role.value,
                "agent_id": message.meta_data.get("agent_id", DEFAULT_AGENT_ID),
                "session_id": message.meta_data.get("session_id", DEFAULT_SESSION_ID),
                "media_id": getattr(message, "media_id", None),
            }
            msg_dicts.append(msg_dict)

        # 准备块数据
        chunk_dicts = []
        for message in messages:
            for chunk in message.chunks:
                blob_data = chunk.content
                if isinstance(chunk.content, Serializable):
                    blob_data = chunk.content.dump()

                chunk_dict = {
                    "belongs_to": message.id,  # 使用消息ID作为外键
                    "require_upload": chunk.require_upload,
                    "media_id": chunk.media_id,
                    "serial_name": type(chunk.content).__name__,
                    "content": "" if chunk.media_id else blob_data,
                }
                chunk_dicts.append(chunk_dict)

        with (
            tracer.start_as_current_span("sql_insert") as span,
            self.get_session() as session,
        ):
            try:
                if msg_dicts:
                    session.bulk_insert_mappings(MessageModel, msg_dicts)
                if chunk_dicts:
                    session.bulk_insert_mappings(ChunkModel, chunk_dicts)
                span.set_attribute("sql.rows", len(msg_dicts))
                span.set_attribute("sql.rows.chunks", len(chunk_dicts))
                span.set_attribute("sql.status", "ok")
            except Exception as e:
                logger.error("SQL insert error: %s", str(e), exc_info=True)
                span.set_attribute("sql.status", "error")
                span.set_attribute("error.message", str(e))
                raise

    def _query(
        self,
        session,
        agent_id,
        session_id: str | None = None,
        recent_n: int | None = None,
        **kwargs,
    ):
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        kwargs.update({"agent_id": agent_id})
        if session_id is not None:
            kwargs.update({"session_id": session_id})

        query = (
            session.query(MessageModel)  # 使用传入的 session
            .filter_by(**kwargs)
            .options(joinedload(MessageModel.chunks))
            .order_by(MessageModel.timestamp.desc())
        )

        if recent_n is not None:
            query = query.limit(recent_n)

        return query.all()

    def read(
        self,
        agent_id: str | None = None,
        session_id: str | None = None,
        recent_n: int | None = None,
        config: ConfigDeserializer | None = None,
        **kwargs,
    ) -> list[Message]:
        with self.get_session() as session:
            models = self._query(session, agent_id, session_id, recent_n, **kwargs)
            resp = [self.model_to_message(model, config) for model in models]
            return sorted(resp, key=lambda x: x.timestamp)

    def convert_chunks(
        self, chunk_models, config: ConfigDeserializer | None = None
    ) -> list[MessageChunk]:
        """
        Convert a list of ChunkModel instances into a list of MessageChunk instances.

        Args:
            chunk_models: A list of ChunkModel instances to be converted.
            config: An optional dictionary mapping serial names to deserializer
                    callables for converting chunk content.

        Returns:
            A list of MessageChunk instances with deserialized or raw content.
        """

        chunks = []
        deserializers = config or {}
        for chunk_model in chunk_models:
            try:
                content = deserializers.get(chunk_model.serial_name, lambda x: x)(
                    chunk_model.content
                )
            except (ValueError, TypeError) as e:
                logger.error(
                    "Failed to deserialize, %s, %s", chunk_model.serial_name, e
                )
                continue

            chunks.append(
                MessageChunk(
                    content=content,
                    require_upload=chunk_model.require_upload,
                    media_id=chunk_model.media_id,
                )
            )
        return chunks

    def model_to_message(self, model, config: ConfigDeserializer | None = None):
        """
        Convert a MessageModel instance to a Message instance.

        Args:
            model: A MessageModel instance to be converted.
            config: An optional dictionary mapping serial names to deserializer
                    callables for converting chunk content.

        Returns:
            A Message instance with deserialized or raw content.
        """
        return Message(
            chunks=self.convert_chunks(model.chunks, config),
            meta_data=json.loads(model.meta_data),
            timestamp=model.timestamp,
            role=MessageRole.value_of(model.role),
        )

    def clear(self):
        """
        Clear all data from the tables.
        """
        with Session(self.engine) as session:
            try:
                session.query(ChunkModel).delete()
                session.query(MessageModel).delete()
                session.commit()
            except Exception as e:
                session.rollback()
                raise e

    def delete(self, session_id: str):
        with Session(self.engine) as session:
            try:
                # 先删除子表数据（chunks），再删除父表数据（agent_memory）
                # 获取要删除的消息ID
                message_ids = [
                    msg.id
                    for msg in session.query(MessageModel.id)
                    .filter_by(session_id=session_id)
                    .all()
                ]

                if message_ids:
                    # 删除相关的chunks
                    session.query(ChunkModel).filter(
                        ChunkModel.belongs_to.in_(message_ids)
                    ).delete(synchronize_session=False)

                # 删除消息
                session.query(MessageModel).filter_by(session_id=session_id).delete()
                session.commit()
            except Exception as e:
                logger.error("SQL delete error: %s", str(e), exc_info=True)
                session.rollback()
                raise e


class DefaultSQLStoreEngine:
    _instance: SQLStoreEngine | None = None
    _lock = Lock()

    @classmethod
    def get_instance(cls, url: str | None = None, echo=False) -> SQLStoreEngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = SQLStoreEngine(url=url, echo=echo)
        return cls._instance
