import requests


weather_tool_name = "Weather Reports"
weather_tool_description = "Gets the weather reports for various places" 

get_weather_description = """\
<tool_set>
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
    url = "https://nominatim.openstreetmap.org/search"
    params = {'q': place, 'format': 'json', 'limit': 1}
    response = requests.get(url, params=params).json()
    if response:
        lat = response[0]["lat"]
        lon = response[0]["lon"]
        return {"latitude": lat, "longitude": lon}
    else:
        return None