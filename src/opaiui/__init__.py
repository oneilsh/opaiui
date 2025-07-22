import dill, base64
import inspect
from typing import Any, Callable, Optional, List, Dict
from pydantic import field_validator, PrivateAttr, BaseModel, Field, ConfigDict
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import Usage


from pydantic import BaseModel, Field, field_validator
import nest_asyncio

nest_asyncio.apply()


ALLOWED_MENU_KEYS = ["Get Help", "Report a Bug", "About"]

class AppConfig(BaseModel):
    page_title: str = Field(default="Pydantic.AI UI", description="The title of the web page.")
    page_icon: str = Field(default="🤖", description="The icon to display in the browser tab.")
    user_avatar: str = Field(default="👤", description="The avatar to display for the user.")
    sidebar_collapsed: Optional[bool] = Field(default=None, description="Whether the sidebar should be collapsed by default. If none, uses 'auto', which collapses on small screens.")
    menu_items: Dict[str, Optional[str]] = Field(
        default_factory=lambda: {
            "Get Help": None,
            "Report a Bug": None,
            "About": None,
        })

    share_chat_ttl_seconds: int = Field(default=(60 * 60 * 24) * 30, description="Time to live for shared chat sessions in seconds. Default is 30 days.")
    show_modal_error_messages: bool = Field(default=True, description="Whether to show error messages in a modal dialog. If False, errors will be logged but not displayed to the user.")
    show_function_calls: bool = Field(default=False, description="Whether to show function calls in the UI.")

    rendering_functions: List[Callable[[Any], None]] = Field(
        default_factory=list,
    )

    @field_validator("menu_items", mode="after")
    @classmethod
    def validate_menu_items(cls, v):
        extra_keys = set(v) - set(ALLOWED_MENU_KEYS)
        if extra_keys:
            raise ValueError(f"Invalid page menu keys: {extra_keys}. Only {ALLOWED_MENU_KEYS} are allowed.")
        return v

    @field_validator("rendering_functions", mode="before")
    @classmethod
    def validate_rendering_functions(cls, v):
        if not all(inspect.iscoroutinefunction(func) for func in v):
            raise ValueError("All rendering functions must be async functions (defined with async def).")
        return v

class DisplayMessage(BaseModel):
    model_message: Optional[ModelMessage] = None
    render_func: Optional[str] = None
    render_args: Dict[str, Any] = Field(default_factory=dict)
    before_agent_response: bool = Field(default=True, description="If True, this message will be rendered before the agent's response is displayed (immediately after the user message). If False, it will be rendered immediately after.")


class AgentState(BaseModel):
    model_config = ConfigDict(extra="allow")


class AgentConfig(BaseModel):
    agent: Any = Field(default=None, exclude=True, description="The Pydantic.AI Agent instance this config is for.", )
    deps: Any = Field(default=None, exclude=True, description="Dependencies for the agent, to be provided to agent.iter() during a run.")

    greeting: str = Field(default="Hello! How can I assist you today?", description="Greeting message shown in the chat. Appears as a message from the agent, but is not included in the agent's history.")
    agent_avatar: str = Field(default="🤖", description="Avatar to display for the agent in the chat. Can be an emoji or a URL to an image.")

    sidebar_func: Optional[Callable[[Any], None]] = Field(default=None, exclude=True, description="Function to render the agent's sidebar components using Streamlit functions. Takes the agent's dependencies as an argument for stateful information.")

    _usage: Usage = PrivateAttr(default_factory=Usage)
    _history_messages: List[ModelMessage] = PrivateAttr(default_factory=list)
    _display_messages: List[DisplayMessage] = PrivateAttr(default_factory=list)
    _delayed_messages: List[DisplayMessage] = PrivateAttr(default_factory=list) # private attribute as temporary holding for rendering messages; they will be moved to _display_messages when the agent finishes running


    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        serialize_exclude={"agent", "sidebar_func"},
    )

    def serializable_dict(self):
        base = self.model_dump(exclude={"agent", "sidebar_func", "deps"}) # private attributes are not included by default
        base["_usage"] = base64.b64encode(dill.dumps(self._usage)).decode("utf-8") if self._usage else None
        base["_history_messages"] = base64.b64encode(dill.dumps(self._history_messages)).decode("utf-8") if self._history_messages else None
        base["_display_messages"] = base64.b64encode(dill.dumps(self._display_messages)).decode("utf-8") if self._display_messages else None
        # if there's a deps.state, try to serialize it
        if self.deps is not None and hasattr(self.deps, "state"):
            base["deps_state"] = base64.b64encode(dill.dumps(self.deps.state)).decode("utf-8")
        else:
            base["deps_state"] = None
        return base

    @classmethod
    def from_serializable(cls, data: dict, agent=None, sidebar_func=None, deps=None):
        """Create an AgentConfig instance from a serializable dict."""
        usage = Usage()
        if "_usage" in data and data["_usage"] is not None:
            usage = dill.loads(base64.b64decode(data["_usage"]))

        history_messages = []
        if "_history_messages" in data and data["_history_messages"] is not None:
            history_messages = dill.loads(base64.b64decode(data["_history_messages"]))
        else:
            history_messages = []

        display_messages = []
        if "_display_messages" in data and data["_display_messages"] is not None:
            display_messages = dill.loads(base64.b64decode(data["_display_messages"]))

        deps_state = None
        if "deps_state" in data and data["deps_state"] is not None:
            deps_state = dill.loads(base64.b64decode(data["deps_state"]))
        # Remove runtime-only keys from data before constructing
        data = {k: v for k, v in data.items() if k not in ("agent", "sidebar_func", "deps", "_display_messages")}
        obj = cls(**data)
        obj.agent = agent
        obj.deps = deps
        obj.sidebar_func = sidebar_func
        if deps_state is not None:
            obj.deps.state = deps_state
        obj._usage = usage
        obj._history_messages = history_messages
        obj._display_messages = display_messages
        return obj

    # sidebar_func must be a callable and async (coroutine)
    @field_validator("sidebar_func", mode="before")
    @classmethod
    def validate_sidebar_func(cls, v):
        if not callable(v):
            raise ValueError("sidebar_func must be a callable")
        if not inspect.iscoroutinefunction(v):
            raise ValueError("sidebar_func must be an async function")
        return v