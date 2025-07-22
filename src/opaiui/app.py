import streamlit as st
import logging
import asyncio
from opaiui import AppConfig, AgentConfig, DisplayMessage
from pydantic_ai.usage import Usage
from pydantic_ai import Agent
from upstash_redis import Redis
from typing import Dict
import os
import json
from typing import Any, Callable, List, Optional
from opaiui import AgentConfig, AppConfig, AgentState

import dill
import hashlib
import urllib
import traceback

from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallPartDelta,
    ThinkingPart,
    TextPart,
    ToolCallPart,
    ModelResponse,
    ModelRequest,
    SystemPromptPart,
    UserPromptPart,
    ToolReturnPart,
    RetryPromptPart,
)




def _current_agent_config():
    """Get the current agent configuration."""
    return st.session_state.agent_configs.get(st.session_state.current_agent_name, None)


async def _render_sidebar():
    with st.sidebar:
        agent_names = list(st.session_state.agent_configs.keys())
        

        ## First: teh dropdown of agent selections
        new_agent_name = st.selectbox(label = "Current Agent:",
                                      options=agent_names, 
                                      key="current_agent_name", 
                                      disabled=st.session_state.lock_widgets, 
                                      label_visibility="visible", )

        current_config = _current_agent_config()
        if hasattr(current_config, "sidebar_func") and callable(current_config.sidebar_func):
            deps = current_config.deps
            await current_config.sidebar_func(deps)

        st.markdown("#")
        st.markdown("#")
        st.markdown("#")
        st.markdown("#")

        st.caption(f"Input tokens: {current_config._usage.request_tokens or 0} Output tokens: {current_config._usage.response_tokens or 0}")

            
        dbsize = None
        if "UPSTASH_REDIS_REST_URL" in os.environ and "UPSTASH_REDIS_REST_TOKEN" in os.environ:
            try:
                redis = Redis.from_env()
                dbsize = redis.dbsize()
                st.session_state.logger.info(f"Shared chats DB size: {dbsize}")

            except Exception as e:
                _log_error(f"Error connecting to database, or no database to connect to. Error:\n{e}")

        if dbsize is not None:
            col1, col2 = st.columns(2)
            with col1:
                st.button(label = "Clear Chat", 
                          on_click= _clear_chat_current_agent, 
                          disabled=st.session_state.lock_widgets,
                          use_container_width=True)

            with col2:
                if dbsize is not None:
                    st.button(label = "Share Session",
                              on_click= _share_session,
                              disabled=st.session_state.lock_widgets,
                              use_container_width=True)
        else:
            st.button(label = "Clear Chat", 
                      on_click= _clear_chat_current_agent, 
                      disabled=st.session_state.lock_widgets,
                      use_container_width=True)

        with st.expander("Settings", expanded=False):
            st.checkbox("🛠️ Show tool calls", 
                    key="show_function_calls", 
                    disabled=st.session_state.lock_widgets,
                    help = "Show the tool calls made by the agent, including tool calls and their results.")


        st.markdown("---")


def _seconds_to_days_hours(ttl_seconds):
    # we need to convert the time to a human-readable format, e.g. 28 days, 18 hours (rounded to nearest hour)
    # we don't want the default datetime.timedelta format
    ttl_days = int(ttl_seconds // (60 * 60 * 24))
    ttl_hours = int((ttl_seconds % (60 * 60 * 24)) // (60 * 60))
    # only show days and hours if greater than 0, add 's' if greater than 1
    ttl_human = ""
    if ttl_days > 0:
        ttl_human = f"{ttl_days} day{'s' if ttl_days > 1 else ''}"
    if ttl_hours > 0:
        if ttl_days > 0:
            ttl_human += f", {ttl_hours} hour{'s' if ttl_hours > 1 else ''}"
        else:
            ttl_human = f"{ttl_hours} hour{'s' if ttl_hours > 1 else ''}"
     
    return ttl_human



def _clear_chat_current_agent():
    """Clear the chat for the current agent."""
    current_agent_config = _current_agent_config()
    current_agent_config._display_messages = []
    current_agent_config._history_messages = []
    current_agent_config._usage = Usage()

    st.session_state.lock_widgets = False


def _lock_ui():
    st.session_state.lock_widgets = True


# helper function to pull only the fields that are defined in 
# the node's class, excluding inherited fields
def _simplify_model(node):
    cls = type(node)

    own_field_names = set(cls.__dataclass_fields__)
    for base in cls.__mro__[1:]:
        if hasattr(base, "__dataclass_fields__"):
            own -= set(base.__dataclass_fields__)
    
    own_fields = {name: getattr(node, name) for name in own_field_names}

    return own_fields


def _sync_generator_from_async(async_iter):
    loop = asyncio.get_event_loop()
    async def consume():
        async for item in async_iter:
            yield item
    iterator = consume().__aiter__()
    while True:
        try:
            yield loop.run_until_complete(iterator.__anext__())
        except StopIteration:
            break
        except StopAsyncIteration:
            break


async def _process_input(prompt):
    with st.chat_message("user", avatar=st.session_state.app_config.user_avatar):
        st.markdown(prompt, unsafe_allow_html=True)

    prompt = prompt.strip()

    session_id = st.runtime.scriptrunner.add_script_run_ctx().streamlit_script_run_ctx.session_id
    info = {"session_id": session_id, "message": prompt, "agent": st.session_state.current_agent_name}
    st.session_state.logger.info(info)

    current_agent_config = _current_agent_config()

    current_agent = current_agent_config.agent
    current_usage = current_agent_config._usage
    current_deps = current_agent_config.deps
    current_history = current_agent_config._history_messages
    current_display_messages = current_agent_config._display_messages

    with st.chat_message("assistant", avatar = current_agent_config.agent_avatar):
        status = st.status("Checking available resources...")
        async with current_agent.run_mcp_servers():
            async with current_agent.iter(prompt, deps = current_deps, message_history = current_history, usage = current_usage) as run:
                async for node in run:
                    if Agent.is_user_prompt_node(node):
                        pass

                    elif Agent.is_model_request_node(node):
                        async with node.stream(run.ctx) as request_stream:

                            def _extract_streamable_text(sync_stream):
                                """Extracts text from a sync stream."""
                                for event in sync_stream:
                                    if isinstance(event, PartStartEvent):
                                        # toolcallparts don't have a .part.content, but we don't want to stream tool calls anyway
                                        if event.part.has_content():
                                            yield event.part.content
                                    elif isinstance(event, PartDeltaEvent):

                                        if isinstance(event.delta, TextPartDelta):
                                            yield event.delta.content_delta

                            status.update(label = "Answering...")
                            st.write_stream(_extract_streamable_text(_sync_generator_from_async(request_stream)))

                    elif Agent.is_call_tools_node(node):
                        async with node.stream(run.ctx) as handle_stream:
                            async for event in handle_stream:
                                if isinstance(event, FunctionToolCallEvent):
                                    status.update(label = f"Calling tool: {event.part.tool_name!r}")
                                elif isinstance(event, FunctionToolResultEvent):
                                    status.update(label = f"Processing {event.result.tool_name!r} result")

        result = run.result
        
        if not result:
            current_display_messages.append(DisplayMessage(ModelResponse(parts=[TextPart(content="No response from agent. Something went wrong. Please try again later.")])))

        if result:
            messages = result.new_messages()

            # all the messages need to go into the current history used internally by the agent
            current_history.extend(messages)

            # convert result messages to DisplayMessages
            messages = [DisplayMessage(model_message=message) for message in messages]

            before_agent_delayed_messages = [dmessage for dmessage in current_agent_config._delayed_messages if dmessage.before_agent_response]
            after_agent_delayed_messages = [dmessage for dmessage in current_agent_config._delayed_messages if not dmessage.before_agent_response]

            # before_agent_delayed_messages need to be inserted into the result messages after the first UserPromptPart
            if before_agent_delayed_messages:
                for i, dmessage in enumerate(messages):
                    if isinstance(dmessage.model_message, ModelRequest) and any(isinstance(part, UserPromptPart) for part in dmessage.model_message.parts):
                        # slice replacement syntax is weird...
                        messages[i:i+1] = messages[i:i+1] + before_agent_delayed_messages
                        break
            
            current_display_messages.extend(messages)

            # now we can add the delayed messages that should be after the agent's response
            for dmessage in after_agent_delayed_messages:
                current_display_messages.append(dmessage)

            # clear the delayed messages
            current_agent_config._delayed_messages = []



    st.session_state.lock_widgets = False  # Step 5: Unlock the UI   
    st.rerun()



async def call_render_func(render_func_name: str, render_args: dict, before_agent_response: bool = False):
    """Adds a DisplayMessage with a render function to the current agent's display messages."""
    current_agent_config = _current_agent_config()
    if render_func_name in st.session_state.render_funcs:
        dmessage = DisplayMessage(render_func=render_func_name, render_args=render_args, before_agent_response=before_agent_response)
        current_agent_config._delayed_messages.append(dmessage)
    else:
        _log_error(f"Render function {render_func_name} not found in session state. Please check the render_funcs dictionary.")


async def _render_message(dmessage: DisplayMessage):
    """Render a message in the Streamlit chat."""
    if not isinstance(dmessage, DisplayMessage):
        _log_error(f"Expected DisplayMessage in _render_message(), got {type(dmessage)}")
        return
    
    if dmessage.model_message:
        message = dmessage.model_message

        current_agent_config = _current_agent_config()
        if isinstance(message, ModelResponse):
            # message is a ModelResponse, which has a .parts list
            # elements will be one of 
            #  TextPart (with a .content and .has_content()), 
            #  ToolCallPart (with .tool_name, .args, .tool_call_id, and .args_as_dict()),
            #  ThinkingPart (with .content, .id, .signature (for anthropic models), and .has_content())
            # we'll only render TextPart for now; other info will be available in Full context
            if any(isinstance(part, TextPart) for part in message.parts):
                with st.chat_message("assistant", avatar = current_agent_config.agent_avatar):
                    for part in message.parts:
                        if isinstance(part, TextPart):
                            st.markdown(part.content, unsafe_allow_html=True)


        elif isinstance(message, ModelRequest):
            # message is a ModelRequest, which has a .parts list
            # elements will be one of 
            #  SystemPromptPart (with .content),
            #  UserPromptPart (with .content, .timestamp),
            #  ToolReturnPart (with .tool_name, .content, .tool_call_id, .timestamp),
            #  RetryPromptPart (request to try again; with .content, .tool_name, .tool_call_id, .timestamp)
            # generally however, if one is a ToolReturnPart there may not be a UserPromptPart,
            # so we'll check first if we need to render a user message
            if any(isinstance(part, UserPromptPart) for part in message.parts):
                with st.chat_message("user", avatar=st.session_state.app_config.user_avatar):
                    for part in message.parts:
                        if isinstance(part, UserPromptPart):
                            st.markdown(part.content, unsafe_allow_html=True)

        if st.session_state.show_function_calls:
            with st.expander(f"{str(message.parts[0])[:100] + '...'}", expanded=False):
                st.write(message.parts)
    else:
        # this is a DisplayMessage with no model_message, so it must be a custom render function
        if dmessage.render_func and dmessage.render_func in st.session_state.render_funcs:
            render_func = st.session_state.render_funcs[dmessage.render_func]
            if callable(render_func):
                try:
                    render_args = dmessage.render_args or {}
                    await render_func(**render_args)
                except Exception as e:
                    _log_error(f"Error calling render function {dmessage.render_func}: {e}")
            else:
                _log_error(f"Render function {dmessage.render_func} is not callable.")
        else:
            _log_error(f"DisplayMessage has no model_message and no valid render function: {dmessage}")


def _log_error(error_message: str):
    """Render an error message in the Streamlit chat."""
    st.session_state.logger.error(error_message)
    if "show_modal_error_messages" in st.session_state.app_config and st.session_state.app_config.show_modal_error_messages:
        @st.dialog("Error")
        def error_dialog():
            st.markdown(error_message, unsafe_allow_html=True)
            st.divider()
            st.markdown("This error has been logged. Please contact the developer if it persists, with steps to reproduce the issue.")
        error_dialog()


async def _handle_chat_input():
    if prompt := st.chat_input(disabled=st.session_state.lock_widgets, on_submit=_lock_ui, key = "chat_input"):
        await _process_input(prompt)
        return



def _share_session():
    try:
        # most of the appconfig is not changeable, so no need to serialize it
        # we will keep some of the dynamic state info that is stored in st.session_state
       
        state_data = {
            "access_count": 0,
            "agent_configs": {name: config.serializable_dict() for name, config in st.session_state.agent_configs.items()},
            "current_agent_name": st.session_state.current_agent_name,
            "show_function_calls": st.session_state.show_function_calls,
            "sidebar_collapsed": st.session_state.app_config.sidebar_collapsed,
        }

        redis = Redis.from_env()

        # generate convo key, and compute access count (0 if new)
        # we'll hash the serialized state data to create a unique key
        key = hashlib.md5(dill.dumps(state_data)).hexdigest()

        # save the chat with a new TTL
        new_ttl_seconds = st.session_state.app_config.share_chat_ttl_seconds
        redis.set(key, state_data, ex=new_ttl_seconds)

        # display the share dialog
        url = urllib.parse.quote(key)
        ttl_human = _seconds_to_days_hours(new_ttl_seconds)

        @st.dialog("Share Chat")
        def share_dialog():
            st.write(f"Chat saved. Share this link: [Chat Link](/?session_id={url})\n\nThis link will expire in {ttl_human}. Any visit to the URL will reset the timer.")

        share_dialog()

    except Exception as e:
        _log_error(f"Error saving chat: {e}")



def _rehydrate_state():
    session_id = st.query_params["session_id"]

    redis = Redis.from_env()
    state_data_raw = redis.get(session_id)
    state_data = json.loads(state_data_raw)

    if state_data is None:
        raise ValueError(f"Session Key {session_id} not found in database")


    # update ttl and access count, save back to redis
    new_ttl_seconds = st.session_state.app_config.share_chat_ttl_seconds
    access_count = state_data["access_count"] + 1
    state_data["access_count"] = access_count
    redis.set(session_id, state_data, ex=new_ttl_seconds)


    st.session_state.show_function_calls = state_data["show_function_calls"]
    st.session_state.app_config.sidebar_collapsed = state_data["sidebar_collapsed"] # this isn't actually respected by Streamlit...
    st.session_state.current_agent_name = state_data["current_agent_name"]

    # load the agent configs from the state data
    agent_configs = {}
    for name, config_data in state_data["agent_configs"].items():
        session_agent = st.session_state.agent_configs[name].agent
        session_sidebar_func = st.session_state.agent_configs[name].sidebar_func
        session_deps = st.session_state.agent_configs[name].deps
        agent_config = AgentConfig.from_serializable(config_data, agent=session_agent, sidebar_func=session_sidebar_func, deps=session_deps)
        agent_configs[name] = agent_config

    # now we can replace the current session state agent configs
    st.session_state.agent_configs = agent_configs


# Main Streamlit UI
async def _main():
    if "session_id" in st.query_params and "hydrated" not in st.session_state:
        st.session_state["hydrated"] = True
        _rehydrate_state()


    await _render_sidebar()

    current_config = _current_agent_config()

    st.header(st.session_state.current_agent_name)

    with st.chat_message("assistant", avatar = current_config.agent_avatar):
        st.write(current_config.greeting, unsafe_allow_html=True)

    for message in current_config._display_messages:
        await _render_message(message)

    await _handle_chat_input()





def serve(config: AppConfig, agent_configs: Dict[str, AgentConfig]) -> None:
    """Serve the app with the given configuration."""

    if "app_config" not in st.session_state:
        st.session_state.app_config = config
        st.session_state.agent_configs = agent_configs
        if config.rendering_functions is not None:
            # store the render functions in session state for easy access
            st.session_state.render_funcs = {func.__name__: func for func in config.rendering_functions}
        else:
            st.session_state.render_funcs = {}

        # editable by widgets
        st.session_state.current_agent_name = list(agent_configs.keys())[0]  # Default to the first agent
        st.session_state.show_function_calls = config.show_function_calls

        if "logger" not in st.session_state:
            st.session_state.logger = logging.getLogger(__name__)
            st.session_state.logger.handlers = []
            st.session_state.logger.setLevel(logging.INFO)
            st.session_state.logger.addHandler(logging.StreamHandler())

        st.session_state.lock_widgets = False
        st.session_state.setdefault("event_loop", asyncio.new_event_loop())

        sidebar_state = "auto"
        if config.sidebar_collapsed is not None:
            sidebar_state = "collapsed" if config.sidebar_collapsed else "expanded"


        page_settings = {
            "page_title": config.page_title,
            "page_icon": config.page_icon,
            "layout": "centered",
            "initial_sidebar_state": sidebar_state,
            "menu_items": config.menu_items,
        }

        st.set_page_config(**page_settings)


    loop = st.session_state.get("event_loop")
    loop.run_until_complete(_main())