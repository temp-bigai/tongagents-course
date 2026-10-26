import json
import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar, TypeAlias

import jsonschema
from pydantic import BaseModel

from tongagents.logtrace import TracedAs
from tongagents.utils.exception import is_rate_limit_error
from tongagents.utils.logger import logger
from tongagents.utils.utils import json_loads

DEFAULT_API_TOOL_TIMEOUT = int(os.getenv("API_TOOL_TIMEOUT", "30"))
RUNTIME_CFG_KEY = "runtime_config"

ToolParameterSchema: TypeAlias = list[dict[str, Any]] | dict[str, Any]


class ToolHook:
    """工具调用钩子接口

    业务方可以实现这个接口来自定义工具的行为：
    - pre_hook: 在工具调用前处理参数（如添加用户登录态）
    - post_hook: 在工具调用后处理响应（如格式化输出）
    - check_auth: 检查用户权限
    - filter_schema: 过滤 schema 中不需要的参数
    """

    def pre_hook(self, tool: "Tool", params: dict, **kwargs) -> dict:
        """在工具调用前处理参数

        Args:
            tool: 工具实例
            params: 工具调用的原始参数
            **kwargs: 额外的关键字参数

        Returns:
            处理后的参数字典
        """
        return params

    def post_hook(self, tool: "Tool", response: Any, **kwargs) -> Any:
        """在工具调用后处理响应

        Args:
            tool: 工具实例
            response: 工具调用的原始响应
            **kwargs: 额外的关键字参数

        Returns:
            处理后的响应
        """
        return response

    def check_auth(self, tool: "Tool", **kwargs) -> tuple[bool, str | None]:
        """检查用户权限

        Args:
            tool: 工具实例
            **kwargs: 额外的关键字参数

        Returns:
            (是否有权限, 错误信息)
        """
        return True, None

    def filter_schema(self, tool: "Tool", schema: dict) -> dict:
        """过滤 schema 中不需要的参数

        Args:
            tool: 工具实例
            schema: 原始的 JSON Schema

        Returns:
            过滤后的 JSON Schema
        """
        return schema


class RetryableToolCallException(Exception):
    """
    可重试的工具调用异常
    """

    def __init__(self, message: str):
        self.message = message


class NonRetryableToolCallException(Exception):
    """
    不可重试的工具调用异常
    """

    def __init__(self, message: str):
        self.message = message


class RetryMaxTimesException(Exception):
    """
    重试最大次数异常
    """

    def __init__(self, message: str):
        self.message = message


def is_valid_tool_parameters(parameters: dict) -> bool:
    try:
        # Validate that it's a valid JSON Schema
        jsonschema.validators.validator_for(parameters)
        return True
    except jsonschema.exceptions.SchemaError:
        return False


class ToolParameters(BaseModel):
    """Tool parameters manager using JSON Schema.

    This class manages tool parameters using JSON Schema as its internal representation.
    It supports both a list-based input format for backwards compatibility and direct
    JSON Schema input.
    """

    # Cython compilation compatibility: methods become 'cyfunction' which Pydantic v2
    # treats as non-annotated fields. Adding function/cyfunction to ignored_types fixes this.
    model_config = {"ignored_types": (type(lambda: None),)}

    _schema: dict[str, Any]

    def __init__(self, parameters: ToolParameterSchema, **kwargs):
        """Initialize with either list format or JSON Schema format.

        Args:
            parameters: Either a list of parameter definitions or a JSON Schema object
        """
        super().__init__(**kwargs)
        if isinstance(parameters, list):
            self._schema = self._convert_list_to_schema(parameters)
        else:
            # Validate and store the schema
            if not parameters.get("type") == "object":
                raise ValueError("Root schema must be of type 'object'")
            self._schema = parameters.copy()

    def _convert_list_to_schema(
        self, parameters: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Convert list format to JSON Schema.

        Args:
            parameters: List of parameter definitions in format:
                      [{"name": str, "type": str, "description": str, "required": bool}]

        Returns:
            A JSON Schema object
        """
        properties = {}
        required = []

        for param in parameters:
            name = param["name"]
            prop = {}

            # Handle type
            if "," in param["type"]:
                # Handle multiple types
                types = [t.strip() for t in param["type"].split(",")]
                prop["anyOf"] = [{"type": t} for t in types]
            else:
                prop["type"] = param["type"]

            # Add description if present
            if param.get("description"):
                prop["description"] = param["description"]

            # Add any nested properties or items
            if param.get("properties"):
                prop["properties"] = param["properties"]
            if param.get("items"):
                prop["items"] = param["items"]

            properties[name] = prop

            if param.get("required", False):
                required.append(name)

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required

        return schema

    def validate_parameter(self, name: str, value: Any) -> bool:
        """Validate a parameter value against its schema.

        Args:
            name: Parameter name
            value: Value to validate

        Returns:
            True if validation succeeds, False otherwise
        """
        properties = self._schema.get("properties", {})
        if name not in properties:
            return False

        try:
            jsonschema.validate(
                instance={name: value},
                schema={
                    "type": "object",
                    "properties": {name: properties[name]},
                    "required": [name],
                },
            )
            return True
        except jsonschema.exceptions.ValidationError:
            return False

    def to_json_schema(self) -> dict[str, Any]:
        """Return the internal JSON Schema representation.

        Returns:
            Complete JSON Schema object
        """
        return self._schema.copy()


class ToolInfo(BaseModel):
    name: str = ""
    description: str = ""
    parameters: ToolParameters = None
    name_for_human: str = ""
    args_format: str = ""


class Tool(ABC):
    # required
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    parameters: ClassVar[ToolParameters] = None

    # not required
    name_for_human: ClassVar[str] = ""
    args_format: ClassVar[str] = ""
    retry_times: ClassVar[int] = 1

    def __init__(
        self, runtime_config: dict | None = None, hook: ToolHook | None = None
    ):
        """
        Args:
            runtime_config: The configuration of the tool determines the behavior
                of the tool instance at runtime
            hook: Optional hook for customizing tool behavior
        """
        self.runtime_config = runtime_config or {}
        self.hook = hook
        if not self.name:
            raise ValueError(
                f"You must set {self.__class__.__name__}.name, either by "
                f"@register_local_tool(name=...) or explicitly setting "
                f"{self.__class__.__name__}.name"
            )
        if isinstance(self.parameters, dict) and (
            not is_valid_tool_parameters(self.parameters)
        ):
            raise ValueError(
                "The parameters, when provided as a dict, must confirm to "
                "a valid openai-compatible JSON schema."
            )

    @staticmethod
    def _get_plugin_hooks(hook_name: str) -> list:
        """Return SDK/CLI plugin hooks without making the SDK depend on CLI."""
        try:
            from tongagents.hooks.plugin_registry import get_plugin_manager

            hooks = get_plugin_manager().get_hooks(hook_name)
            if hooks:
                return hooks
            try:
                from tongagents_cli.plugin.plugin_manager import (
                    get_global_plugin_manager,
                )

                return get_global_plugin_manager().get_hooks(hook_name)
            except ImportError:
                return []
        except Exception:
            return []

    @classmethod
    def _run_plugin_hooks(cls, hook_name: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """Run one plugin hook chain best-effort, preserving shared metadata."""
        hooks = cls._get_plugin_hooks(hook_name)
        if not hooks:
            return ctx
        import asyncio

        for hook in hooks:
            try:
                result_ctx = asyncio.run(hook(ctx))
                if result_ctx and isinstance(result_ctx, dict):
                    ctx = result_ctx
            except Exception:
                pass  # Plugin failures must not interrupt a tool call.
        return ctx

    @TracedAs(name="tool.call", record_params=True, record_result=True)
    def call(self, params: str | dict, **kwargs) -> str | list | dict:
        """
        Args:
            params: The parameters of the function call, either as string(json) or dict
            **kwargs: Additional keyword arguments

        Returns:
            The result of the function call
        """
        params = self._normalize_and_validate_params(params)

        # Apply pre_hook if provided
        if self.hook:
            try:
                params = self.hook.pre_hook(self, params, **kwargs)
            except PermissionError as e:
                # Policy denial from sandbox: wrap with SANDBOX_SECURITY_DENIED prefix
                # so react_agent can detect it via is_sandbox_denied() and stop retrying
                from tongagents.sandbox.errors import sandbox_denied

                logger.info("Tool %s denied by sandbox policy: %s", self.name, e)
                return sandbox_denied(str(e))

        # Check auth if hook is provided
        if self.hook:
            auth_result, auth_error = self.hook.check_auth(self, **kwargs)
            if not auth_result:
                return auth_error or "Authentication failed"

        plugin_metadata: dict[str, Any] = {}
        before_ctx = self._run_plugin_hooks(
            "on_tool_execute",
            {
                "tool_name": self.name,
                "tool_args": params,
                "result": None,
                "error": None,
                "tool": self,
                "metadata": plugin_metadata,
            },
        )
        plugin_metadata = before_ctx.get("metadata", plugin_metadata)

        def run_after_plugins(result: Any, error: BaseException | None) -> Any:
            ctx = self._run_plugin_hooks(
                "on_after_tool_execute",
                {
                    "tool_name": self.name,
                    "tool_args": params,
                    "result": result,
                    "error": error,
                    "tool": self,
                    "metadata": plugin_metadata,
                },
            )
            return ctx.get("result", result)

        last_exception = None
        for retry_time in range(max(self.retry_times, 1)):
            try:
                resp = self._do_call(params, **kwargs)

                # Apply post_hook if provided
                if self.hook:
                    resp = self.hook.post_hook(self, resp, **kwargs)

                return run_after_plugins(resp, None)
            except RetryableToolCallException as e:
                if is_rate_limit_error(e):
                    logger.warning(
                        "Tool %s hit rate limit: %s, stop retrying to avoid overload",
                        self.name,
                        e,
                    )
                    run_after_plugins(None, e)
                    raise e
                logger.warning(
                    "Tool %s call failed: %s but retryable retry_time is %s",
                    self.name,
                    e,
                    retry_time,
                )
                last_exception = e
            except NonRetryableToolCallException as e:
                logger.error("Tool %s call failed: %s, and non-retryable", self.name, e)
                run_after_plugins(None, e)
                raise e
            except Exception as e:
                logger.error("Tool %s call failed: %s, and non-retryable", self.name, e)
                run_after_plugins(None, e)
                raise e
        logger.error("Tool %s call failed: %s", self.name, last_exception)
        if last_exception is not None:
            run_after_plugins(None, last_exception)
        raise RetryMaxTimesException(f"Tool {self.name} call failed: {last_exception}")

    @abstractmethod
    def _do_call(self, params: dict, **kwargs) -> str | list | dict:
        raise NotImplementedError

    @classmethod
    def get_tool_info(cls) -> ToolInfo:
        return cls.get_original_tool_info()

    @classmethod
    def get_original_tool_info(cls) -> ToolInfo:
        return ToolInfo(
            **{
                "name": cls.name,
                "description": cls.description,
                "parameters": cls.parameters,
                "name_for_human": cls.name_for_human,
                "args_format": cls.args_format,
            }
        )

    def get_tool_info_with_hook(self) -> ToolInfo:
        """Get tool info with hook-filtered schema.

        Returns:
            ToolInfo with potentially filtered parameters schema
        """
        parameters = self.parameters
        if self.hook and parameters:
            # Apply hook filter to the schema
            filtered_schema = self.hook.filter_schema(self, parameters.to_json_schema())
            parameters = ToolParameters(filtered_schema)

        return ToolInfo(
            **{
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
                "name_for_human": self.name_for_human,
                "args_format": self.args_format,
            }
        )

    def _normalize_and_validate_params(
        self, params: str | dict, strict_json: bool = False
    ) -> dict:
        """Normalize parameter format and validate against schema.

        Args:
            params: The parameters of the function call, either as string or dict
            strict_json: Whether to strictly follow the JSON format. Defaults to False
                to handle invalid JSON generated by large models.

        Returns:
            dict: Normalized and validated parameters

        Raises:
            ValueError: If parameters are invalid or required fields are missing
        """
        if isinstance(params, str):
            try:
                if strict_json:
                    params_json: dict = json.loads(params)
                else:
                    # 可以处理一些简单的非法JSON，比如markdown的前后缀等，
                    # 后续发现其他情况再补充
                    params_json: dict = json_loads(params)
            except json.decoder.JSONDecodeError as exc:
                raise ValueError(
                    "Parameters must be formatted as a valid JSON!"
                ) from exc
        else:
            params_json: dict = params
        param_json_schema = self.parameters.to_json_schema()
        if isinstance(param_json_schema, list):
            for param in param_json_schema:
                if param.get("required") and param["name"] not in params_json:
                    raise ValueError(f"Parameters {param['name']} is required!")
        elif isinstance(param_json_schema, dict):
            jsonschema.validate(instance=params_json, schema=param_json_schema)
        else:
            raise ValueError
        return params_json
