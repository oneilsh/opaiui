#from opaiui.app import TestApp
from pydantic_ai import Agent
import streamlit as st

import asyncio
from dataclasses import dataclass
from datetime import date

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallPartDelta,
)
from pydantic_ai.tools import RunContext

import dotenv
dotenv.load_dotenv(override = True)


@dataclass
class WeatherService:
    async def get_forecast(self, location: str, forecast_date: date) -> str:
        # In real code: call weather API, DB queries, etc.
        return f'The forecast in {location} on {forecast_date} is 24°C and sunny.'

    async def get_historic_weather(self, location: str, forecast_date: date) -> str:
        # In real code: call a historical weather API or DB
        return (
            f'The weather in {location} on {forecast_date} was 18°C and partly cloudy.'
        )

weather_agent = Agent[WeatherService, str](
    'openai:gpt-4o',
    deps_type=WeatherService,
    output_type=str,  # We'll produce a final answer as plain text
    system_prompt='Providing a weather forecast at the locations the user provides.',
)


@weather_agent.tool
async def weather_forecast(
    ctx: RunContext[WeatherService],
    location: str,
    forecast_date: date) -> str:

    if forecast_date >= date.today():
        return await ctx.deps.get_forecast(location, forecast_date)
    else:
        return await ctx.deps.get_historic_weather(location, forecast_date)
        



############

from opaiui import app
from opaiui import AgentConfig, AppConfig




def my_sidebar(deps):
    """Render the agent's sidebar in Streamlit."""
    st.sidebar.title("Weather Agent")
    st.sidebar.write("This agent provides weather forecasts and historical weather data.")
    st.sidebar.write("You can ask about the weather in any location.")

agent_configs = [
    AgentConfig(agent = weather_agent,
                deps = WeatherService(),
                sidebar_func = my_sidebar),
]

config = AppConfig(agent_configs=agent_configs)


app.serve(config)