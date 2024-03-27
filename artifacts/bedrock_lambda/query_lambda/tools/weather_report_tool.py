import requests


weather_tool_name = "Weather Reports"
weather_tool_description = "Gets the weather reports for various places" 

get_weather_specs = """\
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
    response = {"temp": "25.5", "units": "celcius", "windspeed": "25kmph"}
    return response
    

def get_lat_long(place: str):
    default = {"latitude": 25, "longitude": 35}
    return default