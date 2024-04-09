import requests
import subprocess
import sys
import json

subprocess.check_call([sys.executable, "-m", "pip", "install", "geopy", "--target", "/tmp"])
sys.path.append('/tmp')
from geopy.geocoders import Nominatim

geo_locator = Nominatim(user_agent="sample-weather-agent")


weather_tool_name = "Weather Reports"
weather_tool_description = "Gets the weather reports for various places" 

get_weather_specs = """\
<tool_set>
 <instructions>
   1. You will only provide the weather details such as temperature, windspeed for a given place
   </instructions>

   <tool_description>
   <tool_usage>This tool is used to get the weather details for a given latitude and longitude</tool_usage>
   <tool_name>get_weather</tool_name>
   <parameters>
   <name>latitude</name>
   <name>longitude</name>
   </parameters>
   </tool_description>
   

   <tool_description>
   <tool_usage>This tool is used to get the latitude and longitude for a given place</tool_usage>
   <tool_name>get_lat_long</tool_name>
   <parameters>
   <name>place</name>  
   </parameters>
   </tool_description> 
<tool_set>
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
    