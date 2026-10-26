import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import requests

from tongagents.agents.llm import LLM_FACTORY
from tongagents.agents.llm.messages import (
    MESSAGE_DESERIALIZER,
    ModelOutputMessage,
    StreamModelOutputMessage,
    SystemPromptMessage,
    ToolCallMessage,
    ToolResultMessage,
    ToolRetryExceptionMessage,
    UserPromptMessage,
)
from tongagents.base_agent import WorkflowAgent
from tongagents.entity import Action, DebugEvent, EntityType, Event, Observation
from tongagents.knowledge.core import KnowledgeStore
from tongagents.logtrace import get_tracer
from tongagents.message.message import Serializable
from tongagents.tools.base import (
    NonRetryableToolCallException,
    RetryableToolCallException,
    Tool,
)
from tongagents.tools.tool_manager import ToolManager
from tongagents.utils.exception import (
    ToolCallFailedException,
    ToolCallOutputTruncatedException,
    ToolCallRateLimitException,
    is_rate_limit_error,
)
from tongagents.utils.logger import logger
from tongagents.utils.utils import json_loads
from tongagents.workflow.callbacks.base import BaseCallbackHandler
from tongagents.workflow.commands.transfer_command import (
    TransferCommand,
)
from tongagents.workflow.nodes.simple_node_base import END, START, InputProcessMode
from tongagents.workflow.simple_workflow import node_declare

from .defs import (
    LIMIT_REACHED_SUMMARY_SYSTEM_PROMPT,
    RATE_LIMIT_USER_FACING_MESSAGE,
    ErrorCode,
    ExceuteInputAction,
    LimitReachedStrategy,
    LLMInputEvent,
    LLMRunContext,
    ReactAgentSetting,
    ReactInputEvent,
    TextAction,
    TextActionType,
    ToolAction,
    ToolErrorAction,
    ToolResutAction,
    build_finalize_fallback_summary,
    build_limit_reached_tool_results,
    build_rate_limit_tool_result,
    build_tool_failure_fallback_summary,
    build_tool_failure_message,
    build_tool_failure_summary_prompt,
)


def _put_debug_tool_result(context, tool_result_action: ToolResutAction) -> None:
    if (
        context is None
        or not getattr(context.workflow, "debug_mode", False)
        or context.workflow.debug_queue is None
    ):
        return
    context.workflow.debug_queue.put(
        DebugEvent(
            type="node_process",
            data={
                "node_name": "execute",
                "in_event": tool_result_action,
            },
        )
    )


def _put_debug_tool_action(context, tool_action: ToolAction) -> None:
    if (
        context is None
        or not getattr(context.workflow, "debug_mode", False)
        or context.workflow.debug_queue is None
    ):
        return
    context.workflow.debug_queue.put(
        DebugEvent(
            type="node_process",
            data={
                "node_name": "execute",
                "in_event": tool_action,
            },
        )
    )


class StatelessReactAgent(WorkflowAgent):
    def __init__(
        self,
        dep_context: LLMRunContext = None,
        agent_settings: ReactAgentSetting = None,
        tools: list[Tool | KnowledgeStore] | None = None,
        callbacks: list[BaseCallbackHandler] | None = None,
    ):
        super().__init__(dep_context, agent_settings, callbacks)
        self.llm = LLM_FACTORY.create(agent_settings.llm_config)

        # key: tool_identifier(str), value: tool_instance(Tool)
        self.tools = {}
        if tools and len(tools) != 0:
            for tool in tools:
                tool_instance = None
                if isinstance(tool, KnowledgeStore):
                    tool_instance = tool.as_tool_instance()
                else:
                    tool_instance = tool
                if tool_instance.name in self.tools:
                    raise ValueError(f"Tool {tool_instance.name} already exists")
                self.tools[tool_instance.name] = tool_instance

        if agent_settings.tool_identifier_list:
            for tool_identifier in agent_settings.tool_identifier_list:
                tool_instance = ToolManager.get_tool_instance(tool_identifier)
                if tool_instance.name in self.tools:
                    raise ValueError(f"Tool {tool_instance.name} already exists")
                self.tools[tool_instance.name] = tool_instance

        self.system_prompt = None
        if agent_settings.system_prompt is not None:
            self.system_prompt = agent_settings.system_prompt

        # TODO: @wanghao currently it's hard to implement a stateless workflow
        self.input_history = []
        self.appended_history = []
        self.retry_cnt = 0
        self._call_cnt = 0
        self._tool_rate_limited = False
        # Signals from the most recent model response, used by the truncation
        # guard in ``_tool_call`` (Task #4306). ``finish_reason`` is often absent
        # for the failing provider, so it is a bonus signal, not a requirement.
        self._last_finish_reason: str | None = None
        self._last_reasoning_content: str | None = None

    def _reset(self):
        self.input_history = []
        self.appended_history = []
        self.retry_cnt = 0
        self._call_cnt = 0
        self._tool_rate_limited = False
        self._last_finish_reason = None
        self._last_reasoning_content = None

    def get_appended_history(self):
        return self.appended_history

    def _set_appended_history(self, history: list[UserPromptMessage]):
        self.appended_history = history

    def step(self, event: Any) -> Any:
        self._reset()
        wrap_event = event
        if isinstance(event, str):
            wrap_event = LLMInputEvent(input=UserPromptMessage(event))
        # if user call step function, we need to set the input_process_mode
        self.nodes["belife_update"].config.input_process_mode = InputProcessMode.DEFAULT
        ret = super().step(wrap_event)
        result = []
        for resp in ret:
            result.append(resp)

        for resp in ret:
            self._add_msg_to_memory(resp)

        return result

    # 重写stream接口，使到调用方可以不用特别的调用stop
    def stream(self, event: Event, debug: bool = False) -> Iterator[Any]:
        self._reset()

        def event_wrapper(resp):
            for action in resp:
                if isinstance(action, TextAction) and action.is_final_response:
                    logger.debug("StatelessReactAgent stream finished")
                yield action

        user_input = event
        if isinstance(event, str):
            user_input = LLMInputEvent(input=UserPromptMessage(event))

        if debug:
            resp, debug_resp = super().stream(user_input, debug=debug)
            return event_wrapper(resp), debug_resp

        resp = super().stream(user_input)
        return event_wrapper(resp)

    def run(
        self,
        events: Iterator[Any],
        debug: bool = False,
    ) -> Iterator[Any] | tuple[Iterator[Any], Iterator[Any]]:
        self._reset()

        def event_generator():
            for event in events:
                if isinstance(event, str):
                    yield LLMInputEvent(input=UserPromptMessage(event))
                else:
                    yield event

        if debug:
            resp, debug_resp = super().run(event_generator(), debug=debug)
            return resp, debug_resp
        return super().run(event_generator(), debug=debug)

    async def astep(self, event: Any) -> AsyncIterator[Any]:
        """Async version of :meth:`step` (yields messages instead of returning a list).

        Backed by the existing sync pipeline; the async wrapper simply exposes the
        result as an async iterator so callers can write::

            async for msg in agent.astep("hi"):
                ...
        """
        self._reset()
        wrap_event = event
        if isinstance(event, str):
            wrap_event = LLMInputEvent(input=UserPromptMessage(event))
        self.nodes["belife_update"].config.input_process_mode = InputProcessMode.DEFAULT
        ret = super().step(wrap_event)
        for resp in ret:
            yield resp

    def astream(
        self, event: Event, debug: bool = False
    ) -> AsyncIterator[Any] | tuple[AsyncIterator[Any], AsyncIterator[Any]]:
        """Async version of :meth:`stream`. Yields actions instead of returning a generator."""
        self._reset()

        async def event_wrapper(resp):
            async for action in resp:
                if isinstance(action, TextAction) and action.is_final_response:
                    logger.debug("StatelessReactAgent astream finished")
                yield action

        user_input = event
        if isinstance(event, str):
            user_input = LLMInputEvent(input=UserPromptMessage(event))

        if debug:
            resp, debug_resp = super().astream(user_input, debug=debug)
            return event_wrapper(resp), debug_resp

        resp = super().astream(user_input)
        return event_wrapper(resp)

    def arun(
        self,
        events: Iterator[Any] | AsyncIterator[Any],
        debug: bool = False,
    ) -> AsyncIterator[Any] | tuple[AsyncIterator[Any], AsyncIterator[Any]]:
        """Async version of :meth:`run`. Yields actions instead of returning a generator."""
        self._reset()

        async def event_generator():
            if hasattr(events, "__aiter__"):
                async for event in events:
                    if isinstance(event, str):
                        yield LLMInputEvent(input=UserPromptMessage(event))
                    else:
                        yield event
                return

            for event in events:
                if isinstance(event, str):
                    yield LLMInputEvent(input=UserPromptMessage(event))
                else:
                    yield event

        return super().arun(event_generator(), debug=debug)

    def _add_msg_to_memory(self, msg: str | bytes | Serializable):
        logger.debug("----------------[LLMAgent] add msg to memory: %s", msg)
        self.appended_history.append(msg)

    def _get_msg_from_memory(self) -> list:
        if self.system_prompt is not None:
            return [self.system_prompt, *self.input_history, *self.appended_history]
        return self.input_history + self.appended_history

    @node_declare(
        name="belife_update",
        edges=[(START, "belife_update")],
    )
    def belief_update(self, event: Event) -> Observation:
        # TODO: @wanghao support raw string or dict input
        is_rie = isinstance(event, ReactInputEvent)
        is_llm_ie = isinstance(event, LLMInputEvent)

        if not is_rie and not is_llm_ie:
            raise TypeError(
                'The input event type for LLMAgent must be"'
                f'"LLMInputEvent" or "ReactInputEvent", but got {type(event)}'
            )

        if is_llm_ie and isinstance(event.input, str | UserPromptMessage):
            self._reset()

        # if isinstance(event, ReactInputEvent):
        #     self.input_history.extend(event)
        #     return None

        obs = event
        obs.data_type = EntityType.OBSERVATION.name
        return obs

    def _process_stream_model_message(
        self,
        model_message: StreamModelOutputMessage,
    ) -> Iterator[TextAction]:
        # add start signal chunk for each response
        yield TextAction(type=TextActionType.STREAM_START)
        # Task #4324: wrap the actual stream-consumption loop in an
        # ``llm.stream.consume`` span so the trace covers the dominant
        # gap (phase-2 root 4211s: stream loop was ~53% of root with
        # zero trace coverage). ``@TracedAs`` only wraps sync/generator
        # functions at the *call boundary*, so we open the span inside
        # this generator — its scope matches the wall-clock token
        # generation time exactly. The surrounding ``with`` is a normal
        # contextmanager scope inside a generator (PEP 255); we just
        # ensure no ``with`` block straddles a ``yield`` boundary.
        stream_span_cm = get_tracer().start_span(
            "llm.stream.consume",
            attributes={
                "params": {"model_kind": type(model_message).__name__},
            },
        )
        with stream_span_cm as _span:
            for chunk in model_message.stream():
                # Remember the most recent response-level metadata so the
                # tool-call truncation guard can consult it (Task #4306).
                # Recorded here because this is where the stream is
                # actually consumed.
                if (
                    chunk.response_meta is not None
                    and chunk.response_meta.finish_reason
                ):
                    self._last_finish_reason = chunk.response_meta.finish_reason
                yield TextAction(
                    content=chunk.content,
                    reasoning_content=chunk.reasoning_content,
                    response_meta=chunk.response_meta,
                    type=TextActionType.STREAM_CONTENT,
                )
        # add finish signal chunk for each response
        yield TextAction(type=TextActionType.STREAM_FINISH)

        completed_model_message = model_message.to_model_ouput_message()
        if (
            completed_model_message.model_text_message
            and completed_model_message.model_text_message.reasoning_content
        ):
            self._last_reasoning_content = (
                completed_model_message.model_text_message.reasoning_content
            )
        if completed_model_message.tool_call_messages:
            yield ToolAction(tool_calls=completed_model_message.tool_call_messages)

    def _process_blocking_model_message(
        self,
        model_message: ModelOutputMessage,
    ) -> Iterator[TextAction | ToolAction]:
        if model_message.tool_call_messages:
            logger.debug(
                "Got tool call msg from LLM: %s", model_message.tool_call_messages
            )
            yield ToolAction(tool_calls=model_message.tool_call_messages)
        if model_message.model_text_message:
            logger.debug(
                "Got text msg from LLM: %s",
                model_message.model_text_message.content,
            )
            yield TextAction(
                content=model_message.model_text_message.content,
                reasoning_content=model_message.model_text_message.reasoning_content,
                type=TextActionType.BLOCKING_MESSAGE,
            )

    def _process_model_response(
        self, model_response: ModelOutputMessage | StreamModelOutputMessage
    ) -> Iterator[TextAction | ToolAction]:
        if isinstance(model_response, StreamModelOutputMessage):
            yield from self._process_stream_model_message(model_response)
            model_response = model_response.to_model_ouput_message()
        elif isinstance(model_response, ModelOutputMessage):
            yield from self._process_blocking_model_message(model_response)
        else:
            raise ValueError(f"invalid response type {type(model_response)}")

        # self._add_msg_to_memory(model_response)

    def _is_final_response(
        self,
        action: TextAction,
        model_response: ModelOutputMessage | StreamModelOutputMessage,
    ) -> bool:
        if model_response.tool_call_messages:
            return False

        return action.type not in (
            TextActionType.STREAM_CONTENT,
            TextActionType.STREAM_START,
        )

    def _finalize_with_llm(
        self,
        messages: list,
        tool_results: list[ToolResultMessage],
        *,
        summary_system_prompt: str = LIMIT_REACHED_SUMMARY_SYSTEM_PROMPT,
        fallback_summary: str | None = None,
        include_history: bool = True,
    ) -> Iterator[TextAction]:
        summary_prompt_message = SystemPromptMessage(
            content=summary_system_prompt
        )
        summary_messages = (
            [*messages, *tool_results, summary_prompt_message]
            if include_history
            else [summary_prompt_message]
        )
        model_response = self.llm.request(summary_messages, tools=[])
        summary_actions = [
            action
            for action in self._process_model_response(model_response)
            if isinstance(action, TextAction)
        ]
        has_summary_content = any(
            action.content and action.content.strip() for action in summary_actions
        )
        if has_summary_content:
            for action in summary_actions:
                action.is_final_response = action.type not in (
                    TextActionType.STREAM_CONTENT,
                    TextActionType.STREAM_START,
                )
                yield action
        else:
            if fallback_summary is None:
                fallback_summary = build_finalize_fallback_summary(
                    summary_messages
                )
            yield TextAction(
                content=fallback_summary,
                is_final_response=True,
            )

    def _summarize_tool_failure_with_llm(
        self,
        messages: list,
        tool_results: list[ToolResultMessage],
        *,
        tool_name: str,
        attempt_count: int,
        failure_reason: str,
    ) -> Iterator[TextAction]:
        yield from self._finalize_with_llm(
            messages,
            tool_results,
            summary_system_prompt=build_tool_failure_summary_prompt(
                tool_name=tool_name,
                attempt_count=attempt_count,
                failure_reason=failure_reason,
            ),
            fallback_summary=build_tool_failure_fallback_summary(
                tool_name=tool_name,
                attempt_count=attempt_count,
                failure_reason=failure_reason,
            ),
            include_history=False,
        )

    @node_declare(name="plan", edges=[("belife_update", "plan")])
    def plan(
        self,
        observation: ReactInputEvent | None,
    ) -> ExceuteInputAction:
        # if isinstance(observation.input, str):
        #     self._add_msg_to_memory(UserPromptMessage(content=observation.input))
        # elif isinstance(observation.input, UserPromptMessage):
        #     self._add_msg_to_memory(observation.input)
        # # TODO: @wanghao more strict validation
        # elif isinstance(observation.input, list):
        #     for tool_res in observation.input:
        #         self._add_msg_to_memory(tool_res)
        # else:
        #     raise TypeError(
        #         f"invalid input event, expected str, \
        #                     UserPromptMessage or list[ToolResultMessage], \
        #                     but got {type(observation.input)}"
        #     )
        model_response = self.llm.request(
            observation.input,
            tools=list(self.tools.values()),
        )
        return ExceuteInputAction(input=[*observation.input, model_response])

    def _get_tool_retry_times(self, tool_name: str) -> int:
        # 从memory中获取tool_name的retry_times
        retry_times = 0
        messages = self.run_context.deps.memory.get_messages(
            config=MESSAGE_DESERIALIZER
        )[::-1]
        for memory_message in messages:
            msg = (
                memory_message.chunks[0].content
                if getattr(memory_message, "chunks", None)
                else memory_message
            )
            if isinstance(msg, ModelOutputMessage):
                continue
            if (
                isinstance(msg, ToolRetryExceptionMessage)
                and msg.name == tool_name
            ):
                retry_times += 1
            else:
                break
        return retry_times

    def _tool_call(self, tool_call: ToolCallMessage) -> ToolResultMessage:
        if tool_call.tool_name not in self.tools:
            raise ToolCallFailedException(
                tool_name=tool_call.tool_name,
                tool_call_id=tool_call.tool_call_id,
                reason=f"tool {tool_call.tool_name} not found",
            )
        try:
            arguments = json_loads(tool_call.arguments)
        except Exception as parse_err:
            # The model's tool call did not parse. Before charging this to the
            # ordinary retry ledger, work out whether the output was cut off by
            # ``max_tokens`` (Task #4304: a 13,844-char ``write_draft`` payload
            # truncated at ``...\\n        "pass``).  ``finish_reason`` is not a
            # reliable signal — the guard's post-hoc check is the main defence.
            from tongagents.agents.llm.tool_call_guard import (
                emit_truncation_span,
                is_truncated_arguments_payload,
            )

            if is_truncated_arguments_payload(
                tool_call.arguments,
                parse_err,
                finish_reason=self._last_finish_reason,
                reasoning_content=self._last_reasoning_content,
            ):
                emit_truncation_span(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    arguments=tool_call.arguments,
                    error=parse_err,
                    finish_reason=self._last_finish_reason,
                    reasoning_content=self._last_reasoning_content,
                )
                raise ToolCallOutputTruncatedException(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    reason=(
                        f"tool call output was truncated by the max_tokens limit; "
                        f"arguments are not valid JSON ({parse_err})"
                    ),
                ) from parse_err
            # Not a truncation: keep the historical contract so incidental
            # malformed arguments still surface as an ordinary tool failure.
            raise ToolCallFailedException(
                tool_name=tool_call.tool_name,
                tool_call_id=tool_call.tool_call_id,
                reason=str(parse_err),
            ) from parse_err
        try:
            tool_res = self.tools[tool_call.tool_name].call(params=arguments)
            # A sandbox refusal is an answer, not a failure — it goes back to the
            # model as an ordinary tool result and the loop carries on.  Raising
            # here used to end the turn outright (``execute`` returned as soon as
            # it saw the marker), so one refused call ended the whole run and the
            # agent never learned what it could touch; charging it to the retry
            # ledger instead would ration that exploration.  The denial text
            # already names the tool and the workspace, and
            # ``tongagents.sandbox.errors.is_sandbox_denied`` stays the marker
            # observers use to recognise it.
            return ToolResultMessage(
                name=tool_call.tool_name,
                content=tool_res,
                tool_call_id=tool_call.tool_call_id,
            )
        except RetryableToolCallException as e:
            if is_rate_limit_error(e):
                raise ToolCallRateLimitException(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    reason=e.message,
                ) from e
            if (
                self._get_tool_retry_times(tool_call.tool_name) + 1
                >= self.tools[tool_call.tool_name].retry_times
            ):
                raise ToolCallFailedException(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    reason=e.message,
                ) from e
            return ToolRetryExceptionMessage(
                name=tool_call.tool_name,
                content=e.message,
                tool_call_id=tool_call.tool_call_id,
            )
        except NonRetryableToolCallException as e:
            if is_rate_limit_error(e):
                raise ToolCallRateLimitException(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    reason=e.message,
                ) from e
            logger.error("tool calling failed response: %s", e)
            raise ToolCallFailedException(
                tool_name=tool_call.tool_name,
                tool_call_id=tool_call.tool_call_id,
                reason=e.message,
            ) from e
        except requests.HTTPError as e:
            if is_rate_limit_error(e):
                raise ToolCallRateLimitException(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    reason=str(e),
                ) from e
            raise ToolCallFailedException(
                tool_name=tool_call.tool_name,
                tool_call_id=tool_call.tool_call_id,
                reason=str(e),
            ) from e
        except ToolCallFailedException:
            raise
        except Exception as e:  # pylint: disable=W0718
            if is_rate_limit_error(e):
                raise ToolCallRateLimitException(
                    tool_name=tool_call.tool_name,
                    tool_call_id=tool_call.tool_call_id,
                    reason=str(e),
                ) from e
            raise ToolCallFailedException(
                tool_name=tool_call.tool_name,
                tool_call_id=tool_call.tool_call_id,
                reason=str(e),
            ) from e

    @node_declare(
        name="execute",
        edges=[("plan", "execute"), ("execute", END)],
        with_context_when_called=True,
    )
    def execute(  # noqa: PLR0911
        self, input_action: ExceuteInputAction, context=None
    ) -> Iterator[Action]:
        messages = input_action.input
        latest_response = messages[-1]
        call_limit_reached = (
            self.agent_setting.max_call_cnt
            and self.agent_setting.max_call_cnt > 0
            and self._call_cnt >= self.agent_setting.max_call_cnt
        )
        tool_attempt_limit_imminent = (
            self.agent_setting.max_tool_attempts > 0
            and self.retry_cnt >= self.agent_setting.max_tool_attempts - 1
        )
        finalize_with_llm = (
            self.agent_setting.limit_reached_strategy
            == LimitReachedStrategy.FINALIZE_WITH_LLM
        )
        defer_model_text = self.agent_setting.limit_reached_strategy in (
            LimitReachedStrategy.RETURN_ERROR,
            LimitReachedStrategy.FINALIZE_WITH_LLM,
        )
        buffered_actions = None
        if isinstance(latest_response, StreamModelOutputMessage) and (
            finalize_with_llm
            or (
                defer_model_text
                and (call_limit_reached or tool_attempt_limit_imminent)
            )
        ):
            # The presence of tool calls is only known after consuming a stream.
            # RETURN_ERROR buffers only at a known terminal boundary, so ordinary
            # responses remain streaming. FINALIZE_WITH_LLM buffers until the tool
            # outcome is known so a terminal summary never follows original text.
            buffered_actions = list(self._process_model_response(latest_response))
            messages[-1] = latest_response.to_model_ouput_message()
            latest_response = messages[-1]

        # Only block another ReAct round when the model is still requesting tools.
        # A response without tool calls has already completed the current task.
        if call_limit_reached and latest_response.tool_call_messages:
            _put_debug_tool_action(
                context,
                ToolAction(tool_calls=latest_response.tool_call_messages),
            )
            logger.warning(
                "[StatelessReactAgent] reached max call limit (%s), "
                "skipping tool execution",
                self.agent_setting.max_call_cnt,
            )
            if (
                self.agent_setting.limit_reached_strategy
                == LimitReachedStrategy.FINALIZE_WITH_LLM
            ):
                pending_tool_calls = latest_response.tool_call_messages
                limit_message = (
                    "Agent execution stopped because max_call_cnt="
                    f"{self.agent_setting.max_call_cnt} was reached. "
                    "Interruption reason: MAX_REACT_ROUNDS. "
                    "The pending tool call was not executed."
                )
                tool_results = build_limit_reached_tool_results(
                    pending_tool_calls, limit_message
                )
                yield from self._finalize_with_llm(messages, tool_results)
            elif (
                self.agent_setting.limit_reached_strategy
                == LimitReachedStrategy.RETURN_ERROR
            ):
                yield TextAction(
                    content="call exceeded max call times",
                    reasoning_content="call exceeded max call times",
                    is_final_response=True,
                )
            return

        actions = (
            buffered_actions
            if buffered_actions is not None
            else self._process_model_response(latest_response)
        )
        deferred_text_actions = []
        for action in actions:
            if isinstance(action, TextAction):
                action.is_final_response = self._is_final_response(
                    action, latest_response
                )
                if defer_model_text and (
                    action.type == TextActionType.BLOCKING_MESSAGE
                    or finalize_with_llm
                    or call_limit_reached
                    or tool_attempt_limit_imminent
                ):
                    deferred_text_actions.append(action)
                else:
                    yield action
            elif isinstance(action, ToolAction):
                _put_debug_tool_action(context, action)

        if isinstance(latest_response, StreamModelOutputMessage):
            messages[-1] = latest_response.to_model_ouput_message()

        self._call_cnt += 1

        latest_response = messages[-1]
        if not latest_response.tool_call_messages:
            for deferred_action in deferred_text_actions:
                yield deferred_action
            return

        if latest_response.tool_call_messages:
            if self._tool_rate_limited:
                tool_results = build_limit_reached_tool_results(
                    latest_response.tool_call_messages,
                    "Tool call was not executed because a previous tool was "
                    "rate limited. Interruption reason: TOOL_RATE_LIMITED.",
                )
                if (
                    self.agent_setting.limit_reached_strategy
                    == LimitReachedStrategy.FINALIZE_WITH_LLM
                ):
                    yield from self._finalize_with_llm(
                        input_action.input, tool_results
                    )
                elif (
                    self.agent_setting.limit_reached_strategy
                    == LimitReachedStrategy.RETURN_ERROR
                ):
                    tool_call = latest_response.tool_call_messages[0]
                    yield ToolErrorAction(
                        code=ErrorCode.TOOL_CALL_FAILED,
                        message=RATE_LIMIT_USER_FACING_MESSAGE,
                        tool_name=tool_call.tool_name,
                        tool_call_id=tool_call.tool_call_id,
                    )
                return
            for tool_index, tool_call in enumerate(
                latest_response.tool_call_messages
            ):
                if self.retry_cnt >= self.agent_setting.max_tool_attempts:
                    pending_results = build_limit_reached_tool_results(
                        latest_response.tool_call_messages[tool_index:],
                        "Tool call was not executed because MAX_TOOL_ATTEMPTS was "
                        "already reached. The last error is unavailable.",
                    )
                    if (
                        self.agent_setting.limit_reached_strategy
                        == LimitReachedStrategy.FINALIZE_WITH_LLM
                    ):
                        yield from self._finalize_with_llm(
                            input_action.input, pending_results
                        )
                    elif (
                        self.agent_setting.limit_reached_strategy
                        == LimitReachedStrategy.RETURN_ERROR
                    ):
                        yield from self._summarize_tool_failure_with_llm(
                            input_action.input,
                            pending_results,
                            tool_name=tool_call.tool_name,
                            attempt_count=self.retry_cnt,
                            failure_reason=(
                                "maximum tool call attempts reached; "
                                "the last error is unavailable"
                            ),
                        )
                    return
                try:
                    this_call = tool_call
                    if not this_call.tool_call_id:
                        this_call.tool_call_id = f"tool_call_{uuid.uuid4().hex}"
                    tool_resp = self._tool_call(tool_call)
                    if isinstance(tool_resp, ToolRetryExceptionMessage):
                        self.retry_cnt += 1
                        if self.retry_cnt >= self.agent_setting.max_tool_attempts:
                            failure_result = build_tool_failure_message(
                                tool_name=tool_call.tool_name,
                                tool_call_id=tool_call.tool_call_id,
                                reason=tool_resp.content,
                                attempt_count=self.retry_cnt,
                                max_attempts=self.agent_setting.max_tool_attempts,
                            )
                            _put_debug_tool_result(
                                context,
                                ToolResutAction(result=failure_result),
                            )
                            summary_tool_results = [failure_result]
                            remaining_tool_calls = (
                                latest_response.tool_call_messages[
                                    tool_index + 1 :
                                ]
                            )
                            summary_tool_results.extend(
                                build_limit_reached_tool_results(
                                    remaining_tool_calls,
                                    "Tool call was not executed because a previous "
                                    "tool reached MAX_TOOL_ATTEMPTS.",
                                )
                            )
                            if (
                                self.agent_setting.limit_reached_strategy
                                == LimitReachedStrategy.FINALIZE_WITH_LLM
                            ):
                                yield from self._finalize_with_llm(
                                    input_action.input, summary_tool_results
                                )
                            elif (
                                self.agent_setting.limit_reached_strategy
                                == LimitReachedStrategy.RETURN_ERROR
                            ):
                                yield from self._summarize_tool_failure_with_llm(
                                    input_action.input,
                                    summary_tool_results,
                                    tool_name=tool_call.tool_name,
                                    attempt_count=self.retry_cnt,
                                    failure_reason=tool_resp.content,
                                )
                            return
                    else:
                        self.retry_cnt = 0
                    input_action.input.append(tool_resp)
                    _put_debug_tool_result(context, ToolResutAction(result=tool_resp))
                except ToolCallRateLimitException as e:
                    self._tool_rate_limited = True
                    rate_limit_result = build_rate_limit_tool_result(
                        tool_name=e.tool_name,
                        tool_call_id=e.tool_call_id,
                        reason=e.reason,
                    )
                    remaining_results = build_limit_reached_tool_results(
                        latest_response.tool_call_messages[tool_index + 1 :],
                        "Tool call was not executed because a previous tool was "
                        "rate limited. Interruption reason: TOOL_RATE_LIMITED.",
                    )
                    terminal_results = [rate_limit_result, *remaining_results]
                    for tool_result in terminal_results:
                        _put_debug_tool_result(
                            context,
                            ToolResutAction(result=tool_result),
                        )
                    if (
                        self.agent_setting.limit_reached_strategy
                        == LimitReachedStrategy.FINALIZE_WITH_LLM
                    ):
                        yield from self._finalize_with_llm(
                            input_action.input, terminal_results
                        )
                    elif (
                        self.agent_setting.limit_reached_strategy
                        == LimitReachedStrategy.RETURN_ERROR
                    ):
                        yield ToolErrorAction(
                            code=ErrorCode.TOOL_CALL_FAILED,
                            message=RATE_LIMIT_USER_FACING_MESSAGE,
                            tool_name=e.tool_name,
                            tool_call_id=e.tool_call_id,
                        )
                    return
                except ToolCallFailedException as e:  # pylint: disable=W0718
                    self.retry_cnt += 1
                    failure_result = build_tool_failure_message(
                        tool_name=e.tool_name,
                        tool_call_id=e.tool_call_id,
                        reason=e.reason,
                        attempt_count=self.retry_cnt,
                        max_attempts=self.agent_setting.max_tool_attempts,
                        truncated=isinstance(e, ToolCallOutputTruncatedException),
                    )
                    _put_debug_tool_result(
                        context,
                        ToolResutAction(result=failure_result),
                    )
                    if self.retry_cnt >= self.agent_setting.max_tool_attempts:
                        summary_tool_results = [failure_result]
                        remaining_tool_calls = (
                            latest_response.tool_call_messages[tool_index + 1 :]
                        )
                        summary_tool_results.extend(
                            build_limit_reached_tool_results(
                                remaining_tool_calls,
                                "Tool call was not executed because a previous "
                                "tool reached MAX_TOOL_ATTEMPTS.",
                            )
                        )
                        if (
                            self.agent_setting.limit_reached_strategy
                            == LimitReachedStrategy.FINALIZE_WITH_LLM
                        ):
                            yield from self._finalize_with_llm(
                                input_action.input, summary_tool_results
                            )
                        elif (
                            self.agent_setting.limit_reached_strategy
                            == LimitReachedStrategy.RETURN_ERROR
                        ):
                            yield from self._summarize_tool_failure_with_llm(
                                input_action.input,
                                summary_tool_results,
                                tool_name=e.tool_name,
                                attempt_count=self.retry_cnt,
                                failure_reason=e.reason,
                            )
                        return
                    input_action.input.append(failure_result)
            for deferred_action in deferred_text_actions:
                yield deferred_action
            yield TransferCommand(
                transfer_event=ReactInputEvent(input=input_action.input),
                transfer_target="belife_update",
            )
