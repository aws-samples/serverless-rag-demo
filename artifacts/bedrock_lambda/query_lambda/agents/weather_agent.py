import requests
import subprocess
import sys
import json
from datetime import datetime, timedelta
from typing import Dict
import subprocess
import sys


def install_package(package_name: str):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", package_name, "--target", "/tmp"]
    )
    sys.path.append("/tmp")


install_package("geopy")

from geopy.geocoders import Nominatim

geo_locator = Nominatim(user_agent="sample-weather-agent")

weather_agent_name = "Weather Reports"
weather_agent_description = "Gets the weather reports for various places"

weather_specs = f"""\
<agent_name>{weather_agent_name}</agent_name>
<agent_description>{weather_agent_description}</agent_description>
<tool_set>
	<instructions>
	  You will only provide the weather details such as temperature, windspeed for a given place
	</instructions>

    
    <tool_description>
   <tool_usage>This tool is used to get the weather details for a given latitude and longitude</tool_usage>
   <tool_name>get_weather</tool_name>
   <parameters>
   <parameter>
   <name>latitude</name>
   <type>float</type>
   <description>The latitude of a given place</description>
   </parameter>
   <parameter>
   <name>longitude</name>
   <type>float</type>
   <description>The longitude of a given place</description>
   </parameter>
   
   </parameters>
   </tool_description>

   <tool_description>
   <tool_usage>This tool is used to get the latitude and longitude for a given place</tool_usage>
   <tool_name>get_lat_long</tool_name>
   <parameters>
   <parameter>  
   <name>place</name>
   <type>string</type>
   <description>The name of a given place</description>
   </parameter>
   </parameters>
   </tool_description> 
	
	</tool_set>
"""


def get_weather(latitude: str, longitude: str):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current_weather=true"
    response = requests.get(url)
    return response.json()


def get_lat_long(place: str):
    location = geo_locator.geocode(place)
    if location:
        lat = location.latitude
        lon = location.longitude
        return {"latitude": lat, "longitude": lon}

    return {"latitude": 25, "longitude": 30}
