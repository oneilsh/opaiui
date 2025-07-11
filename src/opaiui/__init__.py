from pydantic.dataclasses import dataclass
from typing import Any, Callable, Optional
from pydantic_ai import Agent
from pydantic import field_validator
from typing import List, Literal


def default_sidebar(deps):
    """Default sidebar function that can be overridden."""
    pass


@dataclass
class AgentConfig:
    agent: Agent
    description: str = "An agent."
    greeting: str = "Hello, how can I assist you today?"
    name: str = "Agent"
    deps: Any = None
    sidebar_func: Callable[[Any], None] = default_sidebar
    agent_avatar: str = "👾"
    user_avatar: str = "👤"

ALLOWED_MENU_KEYS = ["Get Help", "Report a Bug", "About"]

@dataclass
class AppConfig:
    show_function_calls: bool = True
    show_function_calls_status: bool = True
    page_title: str = "Agents"
    page_icon: str = "🤖"
    sidebar_collapsed: bool = True
    menu_items: dict[str, Optional[str]] = {
            "Get Help": None,
            "Report a Bug": None,
            "About": None,
        }
    share_chat_ttl_seconds: int = (60 * 60 * 24) * 60  # 60 days
    agent_configs: List[AgentConfig]

    @field_validator("menu_items", mode="after")
    @classmethod
    def validate_menu_items(cls, v):
        extra_keys = set(v) - ALLOWED_MENU_KEYS
        if extra_keys:
            raise ValueError(f"Invalid page menu keys: {extra_keys}. Only {ALLOWED_MENU_KEYS} are allowed.")
        return v


    @field_validator("agent_configs")
    @classmethod
    def check_non_empty(cls, v):
        if not v:
            raise ValueError("At least one AgentConfig is required")
        return v
