import streamlit as st
import logging
import asyncio
from opaiui import AppConfig, AgentConfig
from upstash_redis import Redis

def initialize_config(**kwargs):
    _initialize_session_state(**kwargs)

    # this is kind of a hack, we want the user to be able to configure the default settings for
    # which needs to be set in the session state, so we pass in kwargs to _initialize_session_state() above, but they can't 
    # go to set_page_config below, so we remove them here
    if "show_function_calls" in kwargs:
        del kwargs["show_function_calls"]
    if "share_chat_ttl_seconds" in kwargs:
        del kwargs["share_chat_ttl_seconds"]
    if "show_function_calls_status" in kwargs:
        del kwargs["show_function_calls_status"]

    defaults = {
        "page_title": "Kani AI",
        "page_icon": None,
        "layout": "centered",
        "initial_sidebar_state": "collapsed",
        "menu_items": {
            "Get Help": "https://github.com/monarch-initiative/agent-smith-ai",
            "Report a Bug": "https://github.com/monarch-initiative/agent-smith-ai/issues",
            "About": "Agent Smith (AI) is a framework for developing tool-using AI-based chatbots.",
        }
    }

    # set the page title to the session_state as we'll need it later
    st.session_state.page_title = kwargs.get("page_title", defaults["page_title"])

    st.set_page_config(
        **{**defaults, **kwargs}
    )

# Initialize session states
def _initialize_session_state(**kwargs):
    if "logger" not in st.session_state:
        st.session_state.logger = logging.getLogger(__name__)
        st.session_state.logger.handlers = []
        st.session_state.logger.setLevel(logging.INFO)
        st.session_state.logger.addHandler(logging.StreamHandler())

    st.session_state.setdefault("event_loop", asyncio.new_event_loop())
    st.session_state.setdefault("default_api_key", None)  # Store the original API key
    st.session_state.setdefault("ui_disabled", False)
    st.session_state.setdefault("lock_widgets", False)
    ttl_seconds = kwargs.get("share_chat_ttl_seconds", 60*60*24*30)  # 30 days default
    st.session_state.setdefault("share_chat_ttl_seconds", ttl_seconds)

    st.session_state.setdefault("show_function_calls", kwargs.get("show_function_calls", False))
    st.session_state.setdefault("show_function_calls_status", kwargs.get("show_function_calls_status", True))



def serve_app(config: AppConfig):
    """Serve the app with the given configuration."""
    if "app_config" not in st.session_state:
        st.session_state.app_config = config

    # there will be at least one AgentConfig (validated in AppConfig)
    st.session_state.current_agent_config = config.agent_configs[0]
    st.session_state.current_agent_name = st.session_state.current_agent_config.name

    # we need to call initialize_config to set the page title and other defaults
    initialize_config(
        page_title=config.page_title,
        page_icon=config.page_icon,
        show_function_calls=config.show_function_calls,
        show_function_calls_status=config.show_function_calls_status,
        initial_sidebar_state="expanded" if not config.sidebar_collapsed else "collapsed",
        menu_items=config.menu_items,
        share_chat_ttl_seconds=config.share_chat_ttl_seconds,
    )

    loop = st.session_state.get("event_loop")
    
    loop.run_until_complete(_main())



def _render_sidebar():
    current_agent_config = st.session_state.current_agent_config

    with st.sidebar:
        agent_names = [agent.name for agent in st.session_state.app_config.agent_configs]
        

        ## First: teh dropdown of agent selections
        current_agent_name = st.selectbox(label = "**Assistant**", 
                                          options=agent_names, 
                                          key="current_agent_name", 
                                          disabled=st.session_state.lock_widgets, 
                                          label_visibility="visible")


        ## then the agent gets to render its sidebar info
        if hasattr(current_agent_config, "sidebar_func") and callable(current_agent_config.sidebar_func):
           current_agent_config.render_sidebar()

        st.markdown("#")
        st.markdown("#")
        st.markdown("#")
        st.markdown("#")

        ## global UI elements
        col1, col2 = st.columns(2)

        with col1:
            st.button(label = "Clear Chat", 
                      on_click=_clear_chat_current_agent, 
                      disabled=st.session_state.lock_widgets,
                      use_container_width=True)
            
        # Try to get the database size from redis and log it
        dbsize = None
        # if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are both set, we can connect to the Redis database
        # otherwise, we assume no database is configured
        if "UPSTASH_REDIS_REST_URL" in os.environ and "UPSTASH_REDIS_REST_TOKEN" in os.environ:
            try:
                redis = Redis.from_env()
                dbsize = redis.dbsize()
                st.session_state.logger.info(f"Shared chats DB size: {dbsize}")

            except Exception as e:
                st.session_state.logger.error(f"Error connecting to database, or no database to connect to. Error:\n{e}")
            
        if dbsize is not None:
            with col2:
                st.button(label = "Share Chat",
                          on_click=_share_chat,
                          disabled=st.session_state.lock_widgets,
                          use_container_width=True)
        
        st.checkbox("🛠️ Show full context", 
                    key="show_function_calls", 
                    disabled=st.session_state.lock_widgets)
        
        st.markdown("---")



# Main Streamlit UI
async def _main():
    if "session_id" in st.query_params:
        _render_shared_chat()
        return
    
    else:
        _render_sidebar()

        current_agent_config = st.session_state.agents[st.session_state.current_agent_config]

        st.header(current_agent_config.name)

        with st.chat_message("assistant", avatar = current_agent_config.avatar):
            st.write(current_agent_config.greeting, unsafe_allow_html=True)

        for message in current_agent_config.display_messages:
            _render_message(message)

        await _handle_chat_input()
