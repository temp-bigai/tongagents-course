import inspect
import json
import threading
import warnings
from collections.abc import Callable
from typing import ClassVar

import requests
import yaml
from typing_extensions import deprecated

from tongagents.exception.framework_exception import InitializeException
from tongagents.tools.base import Tool, ToolInfo, ToolParameters
from tongagents.tools.build_tool_class import BuildToolClass
from tongagents.tools.openapi_to_mcp import convert_openapi_to_mcp, parse_openapi_data
from tongagents.tools.tool.api_tool import ApiTool
from tongagents.tools.type_converter import ParameterProcessor
from tongagents.utils.function_parser import FunctionParser
from tongagents.utils.logger import logger


def tool(
    name: str | Callable | None = None,
    description: str | None = None,
    retry_times: int = 1,
):
    """
    Decorator to convert a function into a Tool class and register it to ToolManager.

    Args:
        name (str, optional): Tool name. If not provided, will use function name
        description (str, optional): Tool description
        retry_times (int, optional): Number of times to retry the tool call on failure.
        Defaults to 1 (no retry).
    """
    _func = None
    if callable(name):
        # To be compatible with the old parameter signature
        _func = name
        name = None

    def decorator(func):
        schema = FunctionParser.parse_function(func)

        if not description and not schema.get("description"):
            logger.warning(
                "No description provided for tool '%s'", name or func.__name__
            )
        tool_description = description or schema.get("description", "")

        func_tool_name = name or schema.get("title", func.__name__)

        # Create a new Tool class dynamically
        class FuncTool(Tool):
            name = func_tool_name
            description = tool_description
            parameters = ToolParameters(parameters=schema)

            def _do_call(self, params=None, **kwargs):
                sig = inspect.signature(func)
                # Check if the function accepts variable keyword arguments (**kwargs)
                has_var_kwargs = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD
                    for param in sig.parameters.values()
                )

                # Process parameters with type conversion
                processor = ParameterProcessor()
                processed_params = processor.process_parameters(func, params)

                if has_var_kwargs:
                    return func(**processed_params, **kwargs)
                return func(**processed_params)

            def __call__(self, *args, **kwargs):
                return func(*args, **kwargs)

        # Store retry_times in the runtime config
        FuncTool.retry_times = retry_times

        # Register the tool class
        ToolManager.register_tool(FuncTool.name, FuncTool)
        return FuncTool()

    if _func:
        return decorator(_func)
    return decorator


def register_local_tool(name, retry_times: int = 1):
    """
    The annotation register_local_tool is not required for user-implemented local tools,
    but only local tools that declare the annotation can be bound to agent via tool_name

    Args:
        name (str): The name of the tool
        retry_times (int, optional): Number of times to retry the tool call on failure.
        Defaults to 1 (no retry).
    """

    def decorator(cls):
        if cls.name and cls.name not in ("", name):
            raise ValueError(
                f'{cls.__name__}.name="{cls.name}" conflicts with '
                f'@register_local_tool(name="{name}")'
            )
        cls.name = name
        cls.retry_times = retry_times
        ToolManager.register_tool(name, cls)

        return cls

    return decorator


class ToolManager:
    """
    Tool manager that supports both tool_name and tool_id access.

    For local tools, only tool_name is supported.
    For remote tools, both tool_name and tool_id can be used to access the tool.
    """

    # Main storage for tool classes, indexed by tool_name
    tool_classes: ClassVar[dict[str, type[Tool]]] = {}
    # Additional index for remote tools, mapping tool_id to tool_name
    _tool_id_to_name: ClassVar[dict[str, str]] = {}
    _tool_name_to_id: ClassVar[dict[str, str]] = {}

    _last_tool_snapshot: ClassVar[dict[str, str]] = {}
    _sync_timer: threading.Timer | None = None
    _sync_stop_event: threading.Event = threading.Event()

    @classmethod
    def contains(cls, tool_identifier: str) -> bool:
        """Check if a tool exists by its name or id.

        Args:
            tool_identifier: Tool name or tool id.

        Returns:
            bool: True if the tool exists.
        """
        return (
            tool_identifier in cls.tool_classes
            or tool_identifier in cls._tool_id_to_name
        )

    @classmethod
    def get_tool_instance(
        cls, tool_identifier: str, runtime_config: dict | None = None
    ) -> Tool:
        """Get tool instance by tool name or id."""
        tool_name = cls.get_tool_name(tool_identifier)
        if not tool_name:
            raise ValueError(f"Tool `{tool_identifier}` not found.")
        return cls.tool_classes[tool_name](runtime_config)

    @classmethod
    @deprecated(
        "Use get_original_tool_info instead, this method will be removed in the future"
    )
    def get_tool_info(cls, tool_identifier: str) -> ToolInfo:
        """Get tool info by tool name or id.

        Args:
            tool_identifier: Tool name or tool id.

        Returns:
            ToolInfo: Tool information.

        Raises:
            ValueError: If tool is not found.
        """
        return cls.get_original_tool_info(tool_identifier)

    @classmethod
    def get_original_tool_info(cls, tool_identifier: str) -> ToolInfo:
        """Get tool info by tool name or id.

        Args:
            tool_identifier: Tool name or tool id.

        Returns:
            ToolInfo: Tool information.

        Raises:
            ValueError: If tool is not found.
        """
        tool_name = cls.get_tool_name(tool_identifier)
        if not tool_name:
            raise ValueError(f"Tool `{tool_identifier}` not found.")
        return cls.tool_classes[tool_name].get_original_tool_info()

    @classmethod
    def register_tool(
        cls, tool_name: str, tool_clz: type[Tool], tool_id: str | None = None
    ):
        """Register a tool class.

        Args:
            tool_name: The name of the tool.
            tool_clz: The tool class.
            tool_id: Optional tool id for remote tools.
        """
        if tool_name in cls.tool_classes:
            logger.warning("Tool `%s` already exists! Overwriting.", tool_name)
        if not issubclass(tool_clz, Tool):
            raise ValueError(f"{tool_clz.__name__} is not a subclass of Tool.")

        if tool_name != tool_clz.name:
            raise ValueError(
                f'{tool_clz.__name__}.name="{tool_clz.name}" conflicts with '
                f'provided tool_name="{tool_name}"'
            )

        cls.tool_classes[tool_name] = tool_clz
        if tool_id:
            cls._tool_id_to_name[tool_id] = tool_name
            cls._tool_name_to_id[tool_name] = tool_id

    @classmethod
    def get_tool_name(cls, tool_identifier: str) -> str | None:
        """Get tool name from tool identifier (name or id).

        Args:
            tool_identifier: Tool name or tool id.

        Returns:
            str | None: Tool name if found, None otherwise.
        """
        if tool_identifier in cls.tool_classes:
            return tool_identifier
        return cls._tool_id_to_name.get(tool_identifier)

    @classmethod
    def get_tool_id(cls, tool_name: str) -> str | None:
        """Get tool id by tool name."""
        return cls._tool_name_to_id.get(tool_name)

    @classmethod
    def call(cls, tool_identifier: str, args, runtime_config=None, **kwargs):
        """Call a tool by its name or id.

        Args:
            tool_identifier: Tool name or tool id.
            args: Tool arguments.
            runtime_config: Optional runtime configuration.
            **kwargs: Additional keyword arguments.

        Returns:
            Tool execution result.

        Raises:
            ValueError: If tool is not found.
        """
        warnings.warn("Please use the Tool instance bound to the Agent", stacklevel=2)
        tool_name = cls.get_tool_name(tool_identifier)
        if not tool_name:
            raise ValueError(f"Tool `{tool_identifier}` not found.")

        tool_cls = cls.tool_classes[tool_name]
        return tool_cls(runtime_config).call(params=args, **kwargs)

    # --- 启动后台定时同步 ---
    @classmethod
    def start_background_tool_sync(
        cls, url: str | list[str], interval: int = 60
    ):
        """
        启动后台线程，周期性同步远程工具配置。
        Args:
            url: 远程工具配置接口（不含 http://）；支持单个 URL 或 URL 列表。
            interval: 轮询间隔秒数，默认60秒
        """
        cls._sync_stop_event.clear()

        def _sync_loop():
            if cls._sync_stop_event.is_set():
                logger.info("停止后台工具同步任务")
                return
            try:
                cls._sync_remote_tools(url)
            except (
                requests.RequestException,
                json.JSONDecodeError,
                yaml.YAMLError,
                ValueError,
                TypeError,
            ) as e:
                logger.error("自动同步远程工具失败: %s", e)
            cls._sync_timer = threading.Timer(interval, _sync_loop)
            cls._sync_timer.start()
            # finally:
            #     # 递归调用，实现周期执行
            #     threading.Timer(interval, _sync_loop).start()

        logger.info("启动后台远程工具同步任务，url=%s，间隔=%d秒", url, interval)
        _sync_loop()

    @classmethod
    def stop_background_tool_sync(cls):
        """
        停止后台工具同步任务
        """
        cls._sync_stop_event.set()
        if cls._sync_timer:
            cls._sync_timer.cancel()
            cls._sync_timer = None
        logger.info("后台工具同步任务已手动停止")

    @classmethod
    def _sync_remote_tools(cls, url: str | list[str]):
        """
        Fetch remote tools information via HTTP and register them to ToolManager.
        Args:
            url (str | list[str]): The URL of the remote uv services or uv gateway.
        """
        if isinstance(url, list):
            for _url in url:
                cls._sync_remote_tools(_url)
                return
        try:
            logger.info("Fetching remote tools from %s...", url)
            response = requests.get(f"http://{url}/config", timeout=5)
            response.raise_for_status()
            remote_tools = response.json()

            new_snapshot = {}
            changed_tools = {}
            for key, tool_info in remote_tools.items():
                if "openapi_config" in tool_info:
                    tool_id = tool_info["tool_id"]
                    try:
                        hash_str = json.dumps(
                            tool_info["openapi_config"], sort_keys=True
                        )
                        new_snapshot[tool_id] = hash_str

                        if cls._last_tool_snapshot.get(tool_id) != hash_str:
                            pdata = parse_openapi_data(tool_info["openapi_config"])
                            mcp_config = convert_openapi_to_mcp(pdata)
                            changed_tools[tool_id] = ("openapi", mcp_config)
                    except (
                        json.JSONDecodeError,
                        yaml.YAMLError,
                        TypeError,
                        ValueError,
                    ) as e:
                        logger.error("解析 openapi_config 失败 [%s]: %s", key, e)
                        continue

                elif "tool_config" in tool_info:
                    tool_id = tool_info["tool_id"]
                    try:
                        hash_str = json.dumps(tool_info, sort_keys=True)
                        new_snapshot[tool_id] = hash_str

                        if cls._last_tool_snapshot.get(tool_id) != hash_str:
                            changed_tools[tool_id] = ("sdk", tool_info)
                    except (TypeError, ValueError) as e:
                        logger.error("处理 tool_config 失败 [%s]: %s", key, e)
                        continue
                else:
                    logger.warning("跳过无效工具: %s", key)

            removed_ids = set(cls._last_tool_snapshot.keys()) - set(new_snapshot.keys())
            for removed_tool_id in removed_ids:
                tool_name = ToolManager.get_tool_name(removed_tool_id)
                try:
                    # 如果已注册的工具中包含该 tool_name，则删除
                    if tool_name in cls.tool_classes:
                        del cls.tool_classes[tool_name]
                        # print("注销已删除工具", tool_name)
                        logger.info("注销远程已删除工具 [%s]", tool_name)
                        cls._tool_id_to_name.pop(removed_tool_id, None)
                        if tool_name in cls._tool_name_to_id:
                            cls._tool_name_to_id.pop(tool_name)
                        cls._last_tool_snapshot.pop(removed_tool_id, None)
                    else:
                        logger.warning("注销失败，未找到工具名 [%s]", tool_name)

                except (TypeError, ValueError) as e:
                    logger.warning("注销工具失败 [%s]: %s", tool_name, e)

            if not changed_tools:
                logger.debug("未检测到远程工具变化，跳过注册")
                return
            # print("检测到 %d 个工具变更，开始注册...", len(changed_tools))
            logger.info("检测到 %d 个工具变更，开始注册...", len(changed_tools))
            for tool_id, (tool_type, data) in changed_tools.items():
                try:
                    if tool_type == "openapi":
                        cls.initialize_from_openapi(tool_id=tool_id, config=data)
                        tools = data.get("tools", [])
                        for tool_def in tools:
                            name = tool_def["name"]
                        # print("注册更新openapi工具", name)
                        logger.info("注册更新的 OpenAPI 工具集：%s", name)
                    elif tool_type == "sdk":
                        tool_name = data.get("u_name")
                        tool_class = cls._build_api_tool_class(url, data)
                        if tool_name and tool_class:
                            cls.register_tool(tool_name, tool_class, tool_id)
                            # print("注册更新uv工具", tool_name)
                            logger.info(
                                "注册更新的 SDK 工具：%s [%s]", tool_name, tool_id
                            )
                except (ValueError, TypeError, AttributeError) as e:
                    logger.error("注册工具失败 [%s]: %s", tool_id, e)

            cls._last_tool_snapshot = new_snapshot

        except requests.RequestException as e:
            logger.error("Failed to fetch remote tools: %s", e)

    @classmethod
    def initialize_from_remote(cls, url: str | list[str]):
        """
        Fetch remote tools information via HTTP and register them to ToolManager.
        Args:
            url (str | list[str]): The URL of the remote uv services or uv gateway.
        """
        if isinstance(url, list):
            for _url in url:
                cls.initialize_from_remote(_url)
                return
        try:
            logger.info("Fetching remote tools from %s...", url)
            response = requests.get(f"http://{url}/config", timeout=5)
            response.raise_for_status()
            remote_tools = response.json()

            for key, tool_info in remote_tools.items():
                logger.info("initialize from remote tool `%s`", key)

                if "openapi_config" in tool_info:
                    tool_id = tool_info["tool_id"]
                    openapi_config = tool_info["openapi_config"]
                    parsed_config = parse_openapi_data(openapi_config)
                    mcp_config = convert_openapi_to_mcp(parsed_config)
                    cls.initialize_from_openapi(tool_id=tool_id, config=mcp_config)
                    logger.info("成功从 remote openapi_config 注册工具集：%s", key)
                    continue

                if "tool_config" not in tool_info:
                    logger.warning("U `%s` is not a tool.", key)
                    continue

                tool_name = tool_info.get("u_name")
                tool_id = tool_info.get("tool_id")
                tool_class = cls._build_api_tool_class(url, tool_info)

                if tool_name and tool_class:
                    cls.register_tool(tool_name, tool_class, tool_id)
                    logger.info(
                        "Registered remote tool `%s` with id `%s`.",
                        tool_name,
                        tool_id,
                    )

        except requests.RequestException as e:
            logger.error("Failed to fetch remote tools: %s", e)
            raise InitializeException(f"Failed to fetch remote tools: {e}") from e

    @staticmethod
    def _build_api_tool_class(url, tool_info: dict) -> type[ApiTool]:
        """
        Dynamically build a tool class from the given tool information.
        """

        class NewApiTool(ApiTool):
            # required
            name: ClassVar[str] = tool_info["u_name"]
            description: ClassVar[str] = tool_info["description"]
            parameters: ClassVar[ToolParameters] = ToolParameters(
                parameters=tool_info["tool_config"]["parameters"]
            )

            provider: ClassVar[str] = tool_info["provider"]
            u_service_url: ClassVar[str] = url

            # not required
            name_for_human: ClassVar[str] = tool_info.get("name_for_human", "")
            args_format: ClassVar[str] = tool_info.get("args_format", "")

        return NewApiTool

    @classmethod
    def initialize_from_openapi(cls, tool_id, config: dict) -> list[type[Tool]]:
        tools = config.get("tools", [])
        registered_tools = []
        for tool_def in tools:
            name = tool_def["name"]
            desc = tool_def.get("description", "")
            params = tool_def.get("schema", [])
            request_template = tool_def["requestTemplate"]

            tool_cls = BuildToolClass.build_openapi_tool_class(
                name, desc, params, request_template
            )
            ToolManager.register_tool(name, tool_cls, tool_id=tool_id)
            logger.info("成功注册openapi工具: %s", name)
            registered_tools.append(tool_cls)

        return registered_tools


if __name__ == "__main__":
    ToolManager.initialize_from_remote("10.1.100.242:8002")
    for _k, v in ToolManager.tool_classes.items():
        info = v.get_tool_info()
        print(info)

        tool_obj = v()
        print(tool_obj.name)
        print(tool_obj.description)

        resp = tool_obj.call({"q": "123", "other": "这是一个其他信息"})
        print(resp)
