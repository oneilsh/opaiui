from pydantic_ai import Agent
from pydantic_ai.tools import RunContext
from pydantic_ai.mcp import MCPServerStdio

import streamlit as st
from opaiui import app
from opaiui import AgentConfig, AppConfig, AgentState


import dotenv
dotenv.load_dotenv(override = True)

###############
## Agent Definition
###############

semantic_scholar_mcp = MCPServerStdio(
    command = 'poetry',
    args = ["run", "python", "semantic_scholar_mcp.py"],
)

scholar_agent = Agent('openai:gpt-4o', mcp_servers = [semantic_scholar_mcp])


################
## Deps and Tools
################

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

@scholar_agent.tool
def add_to_library(ctx: RunContext[Library], article: str) -> str:
    """Add a given article to the library."""
    ctx.deps.add(article)
    return f"Article added. Current library size: {len(ctx.deps.state.library)}"

@scholar_agent.tool
def get_library(ctx: RunContext[Library]) -> str:
    """Get the current library as a markdown string."""
    return ctx.deps.as_markdown()


################
## Streamlit Sidebar
################

# will be given the deps object 
def scholar_sidebar(deps):
    """Render the agent's sidebar in Streamlit."""
    st.markdown("### Library")
    st.markdown(deps.as_markdown())


################
## Agent and App Configuration
################


# We configure UI elements and set dependencies for agents, as a dictionary
# mapping agent names to AgentConfig instances.

agent_configs = {
    "Semantic Scholar": AgentConfig(agent = scholar_agent,
                                    deps = Library(),
                                    sidebar_func = scholar_sidebar,
                                    description= "Semantic Scholar paper and author search, with a simple library memory.",
                                    greeting= "Hello! What should we learn about today?",
                                    agent_avatar= "📖")}

## Global app configuration configures page title, icon, default sidebar state, default function call visibility, etc.

app_config = AppConfig(sidebar_collapsed= False,
                       page_icon= "📖",
                       page_title= "Semantic Scholar Agent",)




#################
## Run the app
#################

app.serve(app_config, agent_configs)

