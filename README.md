# opaiui: Opinionated Pydantic.AI User Interface

Opaiui (*oh-pie-you-eye*) provides a simple but flexible [Streamlit](https://streamlit.io) user interface 
for [Pydantic.AI](https://ai.pydantic.dev/) agents. The following features are supported:

- ➡️ Streaming responses
- 🛠️ Realtime tool-calling status display
- ☑️ Agent selection
- ✉️ Shareable sessions (via [Upstash](https://upstash.com/))
- ⚙️ Customizable sidebar user interface
- 🖥️ In-chat rendering of streamlit components via agent tool call
- ℹ️ Toggleable full message context

<br />
<p align="center">
  <img src="assets/screenshot.png" width="70%" alt="Screenshot">
</p>

*Known limitations:*

- While Pydantic.AI [MCP toolsets](https://ai.pydantic.dev/mcp/client/) are supported, the context manager implementation requires reinialization for each message loop. This may cause UI delays if MCP server connections are slow to initialize.
- The chat input box loses focus between messages, as a side effect of disabling it to prevent interruption during streaming responses, a [known limitation and workaround](https://github.com/streamlit/streamlit/issues/8323#issuecomment-2456773202). A future version may implement an unsafe-don't-disable option.


## Installation

Via pip/poetry/whatever:

```bash
pip install opaiui
```

## Usage

An opaiui application consists of:

1. A dictionary of `AgentConfig` objects, keyed by agent name, each specifying:
   1. A Pydantic.AI [agent](https://ai.pydantic.dev/agents/), with or without tools (including MCP)
   1. A `deps` object to use with the agent, as described by [Pydantic.AI](https://ai.pydantic.dev/dependencies/). The `deps`
   may also be used to store agent state across messages
   1. A sidebar function for agent-specific sidebar rendering (which may read state from `deps`)
   1. Other agent metadata, such as avatar and initial greeting
1. An `AppConfig`, specifying:
   1. A set of Streamlit-based rendering functions, which an agent may execute to display widgets in the chat
   1. Other page metadata, such as tab title and icon

<p align="center">
  <img src="assets/architecture.png" width="85%" alt="Screenshot">
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

We can optionally define a function to render a sidebar component for the agent when active. **This function must be async**, and take a `deps` (which will be passed from the agent `deps`, see below).

```python
async def agent_sidebar(deps):
    st.markdown("A basic agent with no special functionality.")
```

If we like, we could define multiple agents, and a unique sidebar rendering function for each. To use them with the app,
we collect them into a dictionary of `AgentConfig`s. Keys are used for identifying the agent by name in the UI:

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
(see below), and `rendering_functions` specifies a set of functions agents may call to render Streamlit widgets to the chat (see below).

With these basic configurations in place, we can serve the app:

```python
serve(app_config, agent_configs)
```

Run the app with `streamlit run`, or deploy to the Streamlit hosted cloud:

```bash
streamlit run main_app.py
```

### Sharing Sessions

Sessions and chats are sharable, backed by [Upstash](https://upstash.com/) serverless storage. To enable, simply create
a Redis database on Upstash, and add `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` to your `.env` or environment variable cloud config.

Sessions are saved for 30 days by default; this is configurable with `share_chat_ttl_seconds` in `AppConfig`, and
visiting a shared session URL will reset the timer.

### `deps` and State

Pydantic.AI utilizes a [dependencies](https://ai.pydantic.dev/dependencies/) injection pattern, whereby each interaction with an agent may be provided a `deps` object; this object is passed to agent tools when they are called, allowing for usage of external functionality such as database connections or API calls. While Pydantic.AI allows these dependencies to change between agent 'runs', opaiui stores `deps` in the `AgentConfig` and provides it for every run (message to the agent).

Opaiui also utilizes `deps` for state management; agent tools may write to `deps`, and `deps` is passed to the sidebar rendering
function for stateful UI components. In fact, if `deps.state` is an object serializable with `dill`, it will be saved and reloaded on session sharing! Opaiui provides an `AgentState` class for this purpose (but it's really just a Pydantic model allowing extra fields).

To see how this works, we can create an agent with access to a Library, and some tools to read and write from it.

```python
# new imports only:
from pydantic_ai import RunContext
from opaiui.app import AgentState

library_agent = Agent('gpt-4o')

# Defines Library objects with sharable AgentState
class Library():
    def __init__(self):
        self.state = AgentState()
        self.state.library = []

    def add(self, article: str):
        """Save an article to the library."""
        self.state.library.append(article)

    def as_markdown(self) -> str:
        if not self.state.library:
            return "None"
        return "\n".join(f"- {entry}" for entry in self.state.library)

@library_agent.tool
async def add_to_library(ctx: RunContext[Library], article: str) -> str:
    """Add a given article to the library."""
    ctx.deps.add(article)
    return f"Article added. Current library size: {len(ctx.deps.state.library)}"

@library_agent.tool
async def count_library(ctx: RunContext[Library]):
    """Get the number of articles currently in the library."""
    return len(ctx.deps.state.library)
```

Now, our `library_agent` can choose to call its `add_to_library` tool, providing a string to store in the library, or get a count of library items with `count_library`.

We define a new sidebar function to rendering the library contents, as well as a button to clear it. As before,
this function must be `async` and take the `deps` parameter:

```python
async def library_sidebar(deps):
    """Render the agent's sidebar in Streamlit."""
    st.markdown("### Library")
    st.markdown(deps.as_markdown())

    def clear_library():
        """Clear the library."""
        deps.state.library = []
    
    if st.button("Clear Library"):
        clear_library()
        st.rerun()
```

This `clear_library` function and button are a bit advanced, but highlight the flexibility allowed by incorporating Streamlit
components. The call to `st.rerun()` forces the UI to re-render after the button executes, updating the sidebar display.

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

Last but not least, opaiui allows for arbitrary rendering of Streamlit components directly in the chat by agent tool call.
Streamlit provides a wide range of easy-to-use UI [elements](https://docs.streamlit.io/develop/api-reference) and community-built [components](https://streamlit.io/components).

This functionality is enabled by providing a list of rendering functions to the `AppConfig`, and in agent tool calls,
using them via `opaiui.app.call_render_func`. Rendering functions must be `async`.

```python
# new imports only
import pandas
from opaiui.app import call_render_func

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

To trigger a render if the chat, an agent tool may call `call_render_func` - the first argument is the name of the
rendering function to call (as a string), the second are arguments to pass (as a dictionary), and finally, `before_agent_response`, a boolean indicating if the render should be before or after the agents' response in the chat 
(after is the default).

```python
@library_agent.tool
async def show_library(ctx: RunContext[Library]) -> str:
    """Displays the current library to the user as a dataframe when executed."""
    if not ctx.deps.state.library:
        await call_render_func("show_warning", {"message": "Library is empty."}, before_agent_response = True)
        return "Library is empty. A warning has been displayed to the user prior to this response."
    
    library_df = pandas.DataFrame(ctx.deps.state.library, columns=["Articles"])
    await call_render_func("render_df", {"df": library_df})
    return "Library will be displayed as a DataFrame *below* your response in the chat. You may refer to it, but do not repeat the library contents in your response."
```

In the example above, asking the agent to show the library will either render a warning about the library being empty
prior to the agents' response, or a dataframe with the library contents after the agents' response. Note that
the agent does not 'see' the rendered result as part of its view of the chat history; return values may be used to provide
relevant information or data to the agent. In the current implementation, the rendering is not visible in the chat until
the agent has completed responding.

## Changelog

- 0.8.1: First public release