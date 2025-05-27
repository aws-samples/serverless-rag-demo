import requests
from datetime import datetime, timedelta
from typing import Dict
from geopy.geocoders import Nominatim
from strands import Agent, tool
from agent_executor_utils import bedrockModel
from os import getenv

WEATHER_SYSTEM_PROMPT = """
You are a weather agent. Your task is to get the weather for a given location.

Key Responsibilities:
- Get the weather for a given location
- Use the tools to get the weather

General Instructions:
- Use only the following tools:
    - get_lat_long: To get the latitude and longitude of a given location
    - get_weather: To get the weather for a given location
    - if you already know the latitude and longitude of a location, you can use the get_weather tool to get the weather

- If the location is not found, return "Location not found"
- If the weather is not found, return "Weather not found"
- If the latitude and longitude are not found, return "Latitude and longitude not found"
- If the weather is not found, return "Weather not found"
"""

geo_locator = Nominatim(user_agent="openstreetmap.org")

@tool
def weather_agent(location: str):
    agent = Agent(system_prompt=WEATHER_SYSTEM_PROMPT, model=bedrockModel, tools=[get_lat_long, get_weather])
    agent_response = agent(location)
    return agent_response

@tool
def get_weather(latitude: str, longitude: str):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true"
    response = requests.get(url)
    return response.json()

@tool
def get_lat_long(place: str):
    location = geo_locator.geocode(place)
    if location:
        lat = location.latitude
        lon = location.longitude
        return {"latitude": lat, "longitude": lon}
    return "Location not found"

# if __name__ == "__main__":
#     print(weather_agent("Mumbai"))