# opaiui: Opinionated Pydantic.AI User Interface

Table of Contents:
1. [Overview](#overview)
2. [Installation](#installation)
3. [Usage](#usage)
   - [Basic Application](#basic-application)
   - [Sharing Sessions](#sharing-sessions)
   - [`deps` and State](#deps-and-state)
   - [Agent-based UI Component Rendering](#agent-based-ui-component-rendering)
   - [Logging](#logging)
4. [Changelog](#changelog)

## Overview

Opaiui (*oh-pie-you-eye*) provides a simple but flexible [Streamlit](https://streamlit.io) user interface 
for [Pydantic.AI](https://ai.pydantic.dev/) agents. The following features are supported:

- ➡️ Streaming responses
- 🛠️ Realtime tool-calling status display
- ☑️ Agent selection
- ✉️ Shareable sessions (via [Upstash](https://upstash.com/))
- ⚙️ Customizable sidebar user interface
- 🖥️ In-chat rendering of streamlit components via agent tool call
- ℹ️ Toggleable full message context

A demo repo is available at [https://github.com/oneilsh/opaiui-demo](https://github.com/oneilsh/opaiui-demo), with live deployment at [https://opaiui-demo.streamlit.app/](https://opaiui-demo.streamlit.app/).

<br />
<p align="center">
  <a href="https://opaiui-demo.streamlit.app"><img src="assets/screenshot.png" width="90%" alt="Screenshot"></a>
</p>

*Known limitations:*

- While Pydantic.AI [MCP toolsets](https://ai.pydantic.dev/mcp/client/) are supported, the context manager implementation requires reinialization for each message loop. This may cause UI delays if MCP server connections are slow to initialize.
- The chat input box loses focus between messages, as a side effect of disabling it to prevent interruption during streaming responses, a [known limitation and workaround](https://github.com/streamlit/streamlit/issues/8323#issuecomment-2456773202). A future version may implement an unsafe-don't-disable option.
- There's a lot of async code and the package uses `nest_asyncio`, which may not be playing as well as it could with Streamlit (see also discussion [here](https://github.com/streamlit/streamlit/issues/8488)).


## Installation

Via pip/poetry/whatever:

```bash
pip install opaiui
```

## Usage

An opaiui application consists of:

1. An `AppConfig`, specifying:
   1. A set of Streamlit-based rendering functions, which an AI agent may execute to display widgets in the chat
   1. Other page metadata, such as tab title and icon
1. A dictionary of `AgentConfig` objects, keyed by agent name, each specifying:
   1. A Pydantic.AI [agent](https://ai.pydantic.dev/agents/), with or without tools (including MCP)
   1. A `deps` object to use with the agent, as described by [Pydantic.AI](https://ai.pydantic.dev/dependencies/). The `deps`  may also be used to store and retrieve agent state across messages and components.
   1. A sidebar function for agent-specific sidebar rendering
   1. Other agent metadata, such as avatar and initial greeting


<p align="center">
  <img src="assets/architecture.png" width="85%" alt="Architecture">
</p>

### Basic Application

We'll start with some imports and a basic agent, assuming we have a defined `OPENAI_API_KEY` in `.env` (or the key
stored in an environment variable or secret, if deploying in the cloud).

```python
# file main_app.py
from pydantic_ai import Agent, RunContext
from opaiui.app import AgentConfig, AppConfig, serve
import streamlit as st

# put OPENAI_API_KEY=<key> in .env
import dotenv
dotenv.load_dotenv()

basic_agent = Agent('openai:gpt-4o')
```

We can optionally define a function to render a sidebar component for the agent when active. **This function must be async**.

```python
async def agent_sidebar():
    st.markdown("A basic agent with no special functionality.")
```

If we like, we could define multiple agents, and a unique sidebar rendering function for each. To use them with the app, we collect them into a dictionary of `AgentConfig`s; only `agent` is required here, others have basic defaults. Keys are used for identifying the agent by name in the UI:

```python
agent_configs = {
    "Basic Agent": AgentConfig(
        # agent and deps as defined by Pydantic.AI
        agent = basic_agent,
        deps = None,
        # greeting is shown as the first message to the user, 
        # but is not part of the chat log the agent sees
        greeting = "Hello! How can I help you today?" 
        # avatar can be an image url, or emoji
        agent_avatar = "🧠"
        sidebar_func = agent_sidebar
    )
}
```

Next we create an `AppConfig`, which specifies various global page settings. Note that `menu_items` are those [supported by Streamlit](https://docs.streamlit.io/develop/api-reference/configuration/st.set_page_config), and only accept keys `"Get Help"`, `"Report a Bug"`, and `"About"`.

```python
app_config = AppConfig(
    page_title = "Basic App",
    # icon and avatar may be emoji or urls
    page_icon = "🖥️",
    user_avatar = "👤",
    menu_items = {"Get Help": "Get help at https://github.com/oneilsh/opaiui", 
                  "Report a Bug": "Report bugs at https://github.com/oneilsh/opaiui/issues",
                  "About": "Made with Streamlit, Pydantic.AI, and opaiui."}

    ## advanced options
    # whether to show the sidebar as collapsed on app load
    # (default None for auto based on device size)
    sidebar_collapsed = False
    # whether to show all message contexts by default
    # (toggleable via settings dropdown in sidebar)
    show_function_calls = False
    # whether to display application exceptions via modal dialogs
    # (False = hidden from user by default)
    show_modal_error_messages = False
)
```

In addition to the advanced options documented above, `share_chat_ttl_seconds` configures time-to-live for shared sessions
(see below), and `rendering_functions` specifies a set of functions agents may call to render UI components to the chat (see below).

With these basic configurations in place, we can serve the app:

```python
serve(app_config, agent_configs)
```

Run the app with `streamlit run`, or deploy to the hosted cloud.

```bash
streamlit run main_app.py
```

### Sharing Sessions

Sessions and chats are sharable, backed by [Upstash](https://upstash.com/) serverless storage. To enable, simply create a Redis database on Upstash, and add `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` to your `.env` or environment variable cloud config.

<p align="center">
  <img src="assets/share_screenshot.png" width="50%" alt="Sharing screenshot">
</p>

Sessions are saved for 30 days by default; this is configurable with `share_chat_ttl_seconds` in `AppConfig`, and visiting a shared session URL will reset the timer.

### `deps` and State

Pydantic.AI utilizes a [dependencies](https://ai.pydantic.dev/dependencies/) injection pattern, whereby each interaction with an agent may be provided a `deps` object; this object is passed to agent tools when they are called, for use in accessing external resouces (database connetion, API call, file access, etc). While Pydantic.AI allows these dependencies to change between agent 'runs', this is not possible with opaiui, which stores `deps` in the `AgentConfig` and provides it for every run (message to the agent).

Opaiui also utilizes `deps` for state management, and agent tools as well as the sidebar and other functions can access the current `deps` via `current_deps()`, in addition to the pydantic.ai standard `ctx.deps` which is limited to invoked tools. When sharing a chat, `deps` in general are not saved, because `dill` cannot serialize arbitrary objects. However, if *`deps.state`* is serializable, it will be saved and reloaded on session sharing. Opaiui provides an `AgentState` convenince class for this purpose, but it's really just a Pydantic model allowing extra fields. *Adding unserializable data to `deps.state` will result in an error if the session is shared.*

*Usage note: if you plan to use Pydantic models in `deps.state`, you will encouter an [error](https://github.com/uqfoundation/dill/issues/650) if they are defined in the main app file. The
simples workaround is to define them in another module and import them.*

To see how this works, we can create an agent with access to a Library, and some tools to read and write from it.

```python
# new imports only:
from pydantic_ai import RunContext
from opaiui.app import AgentState, current_deps


# Defines Library objects with sharable AgentState
class Library():
    def __init__(self):
        self.state = AgentState()
        self.state.library = []

    def add_article(self, article: str):
        self.state.library.append(article)

    def as_markdown(self) -> str:
        if not self.state.library:
            return "None"
        return "\n".join(f"- {entry}" for entry in self.state.library)


library_agent = Agent('gpt-4o')

@library_agent.tool
async def add_to_library(ctx: RunContext[Library], article: str) -> str:
    """Add a given article to the library."""
    # here in a tool we could also use the pydantic.ai standard: deps = ctx.deps
    deps = current_deps()

    deps.add_article(article)
    return f"Article added. Current library size: {len(ctx.deps.state.library)}"

@library_agent.tool
async def count_library(ctx: RunContext[Library]):
    """Get the number of articles currently in the library."""
    # pydantic.ai standard: return len(ctx.deps.state.library)
    return len(current_deps().state.library)
```

Now, our `library_agent` can choose to call its `add_to_library` tool, providing a string to store, or get a count of library items with `count_library`.

We define a new sidebar function to render the library contents, as well as a button to clear it. As before, this function must be `async`:

```python
async def library_sidebar():
    deps = current_deps()

    st.markdown("### Library")
    st.markdown(deps.as_markdown())

    if st.button("Clear Library"):
        deps.state.library = []
        st.rerun()
```

This `clear_library` button a bit advanced, but shows the flexibility of incorporating interactive components. The call to `st.rerun()` forces the UI to re-render after the button executes, forcing an update to the UI.

*Usage note:* The "Clear Chat" button clears out the chat history and token usage count, but does not clear the agent's `deps.state`.*

To make use of these, we need to create a `deps` as a new library object for the `AgentConfig`:

```python
agent_configs = {
    "Basic Agent": AgentConfig(
        agent = library_agent,
        deps = Library(),
        greeting = "Hello! How can I help you today?" 
        agent_avatar = "🧠"
        sidebar_func = library_sidebar
    )
}
```

### Agent-based UI Component Rendering

Last but not least, opaiui allows for arbitrary rendering of UI components directly in the chat by agent tool call. Streamlit provides a wide range of easy-to-use UI [elements](https://docs.streamlit.io/develop/api-reference) and community-built [components](https://streamlit.io/components).

This functionality is enabled by providing a list of rendering functions to the `AppConfig`, and in agent tool calls, using them via `opaiui.app.render_in_chat`. Rendering functions must be `async`.

```python
# new imports only
import pandas
from opaiui.app import render_in_chat

async def render_df(df: pandas.DataFrame):
    """Render a DataFrame in Streamlit."""
    st.dataframe(df, use_container_width=True)

async def show_warning(message: str):
    """Display a warning message in Streamlit."""
    st.warning(message)


app_config = AppConfig(
    page_title = "Library App",
    page_icon = "📚",
    rendering_functions = [render_df, show_warning]
)
```

To use these rendering functions, an agent tool may call `render_in_chat`, which adds the execution of a given rendering function to the history. The first argument is the name of the registered rendering function to call as a string, the second is a dictionary of arguments, and finally, `before_agent_response`, a boolean indicating if the render should be before or after the agents' response in the chat (after is the default).

```python
@library_agent.tool
async def show_library(ctx: RunContext[Library]) -> str:
    """Displays the current library to the user as a dataframe when executed."""
    deps = current_deps()

    if deps.state.library is None or len(deps.state.library) == 0:
        await render_in_chat("show_warning", {"message": "Library is empty."}, before_agent_response = True)
        return "Library is empty. A warning has been displayed to the user prior to this response."
    
    library_as_df = pandas.DataFrame(deps.state.library, columns=["Articles"])
    await render_in_chat("render_df", {"df": library_as_df})
    return "Library will be displayed as a DataFrame *below* your response in the chat. You may refer to it, but do not repeat the library contents in your response."
```

*Usage note: these dynamic messages are not part of the conversation history that the LLM is given, prompt accordingly.*

In the example above, asking the agent to show the library will either render a warning about the library being empty prior to the agents' response, or a dataframe with the library contents after the agents' response. In the current implementation, the rendering is not visible in the chat until
the agent has completed responding.

<p align="center">
  <img src="assets/widget_render.png" width="85%" alt="Widget Rendering">
</p>

### Logging

Logging is handled as part of the streamlit session; the default logging level is set to `"INFO"`. You can access the logger
via the app's `get_logger()` function.

```python
from opaiui.app import get_logger

logger = get_logger()
logger.info("Hello from opaiui")
```


## Changelog

- 0.11.0: added `current_deps()`, deprecated `call_render_func` in favor of `render_in_chat`, deprecated accepting `deps` as input to sidebar func, added `ui_locked()` for checking UI status.
- 0.10.3: no cache event loop (possibly cleaner? see also [here](https://github.com/streamlit/streamlit/issues/8488)), cleanup upstash connections
- 0.10.0: Relaxed python dep to >=3.10
- 0.9.1: Added `get_logger()`
- 0.8.1: First public release