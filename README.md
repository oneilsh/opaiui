# opaiui: Opinionated Pydantic.AI User Interface

Opaiui (oh-pie-you-eye) provides a simple but flexible [Streamlit](https://streamlit.io) user interface 
for [Pydantic.AI](https://ai.pydantic.dev/) agents. The following features are supported:

- Streaming responses
- Realtime tool-calling status display
- Agent selection
- Shareable sessions ([Upstash](https://upstash.com/) key required)
- Customizable sidebar user interface
- In-chat rendering of streamlit components via agent tool call
- Toggleable full message context

## Installation

Via pip/poetry/whatever:

```bash
pip install opaiui
```

## Usage

An opaiui application consists of:

1. A list of `AgentConfig` objects, each specifying:
   1. Basic agent metadata, such as avatar and initial greeting
   1. A Pydantic.AI [agent](https://ai.pydantic.dev/agents/), with or without tools (including MCP)
   1. A `deps` object to use with the agent, as described by [Pydantic.AI](https://ai.pydantic.dev/dependencies/). The `deps`
   may also be used to store agent state
   1. A sidebar function for agent-specific sidebar rendering
1. An `AppConfig`, specifying:
   1. Global page metadata, such as tab title and icon
   1. A set of Streamlit-based rendering functions, which an agent may execute to display widgets

### Basic Application

We'll start with some imports and a basic agent, assuming we have a defined `OPENAI_API_KEY` in `.env` (or the key
stored in an environment variable or secret, if deploying in the cloud).

```python
from pydantic_ai import Agent
from opaiui import AgentConfig, AppConfig, AgentState
from opaiui.app import call_render_func
import streamlit as st
import dotenv

# put OPENAI_API_KEY=<key> in .env
dotenv.load_dotenv()

basic_agent = Agent('openai:gpt-4o')
```

We can optionally define a function to render a sidebar component for the agent when active. **This function must be async**, and take a `deps` (which will be passed from the agent `deps`, see below).

```python
async def agent_sidebar(deps):
    st.markdown("", allow_unsafe_html = True)
```

If we like, we could define multiple agents, and a unique sidebar rendering function for each. To use them with the app,
we collect them into a dictionary of `AgentConfig`s. Keys are used for identifying the agent by name in the UI:

```python
agent_configs = {
    "Basic Agent": AgentConfig(
        agent = basic_agent,
        deps = None,
        description = "A basic agent.",

    )
}
```


## Changelog

- 0.8.0: First public release