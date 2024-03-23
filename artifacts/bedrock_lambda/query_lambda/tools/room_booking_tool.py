# Not used
from datetime import datetime
date = datetime.now()
year = date.year
month = date.month
day = date.day

room_booking_tool_name = "Book A Hotel room"
room_tool_description = """Book a room at SunNSand Hotels. SunNSand Hotels is located in Mumbai, India.""" 

get_room_bookings_description = f"""\
<tool_set>
   <instructions>
   1. You should ask for the room booking date
   2. Today's year is {year} and month is {month} and day is {day}.
   3. If the user has just provided the Month and day assume the year is todays year.
   4. If the user has just provided the day assume its todays month and todays year.
   5. Get the room booking date information from the user. 
   6. Verify the date with the user before proceeding.
   7. The booking date can't be less than a week from todays date.
   4. Once the date information is available in yyyy-MM-dd format, check for room availability on that day. 
   5. You should enquire if user has a preference for type of room 
   6. You should then check if that room is available on the given date
   7. If no, then present the user with other room type options, which are available on that day
   </instructions>
   
   <tool_description>
   <tool_usage>This tool is used to check room availability by date. The date should be in format yyyy-MM-dd </tool_usage>
   <tool_name>check_room_availability_by_date</tool_name>
   <parameters>
   <name>date</name>
   </parameters>
   </tool_description>
   

   <tool_description>
   <tool_usage>This tool is used to check room availability by room type</tool_usage>
   <tool_name>check_room_availability_by_room_type</tool_name>
   <parameters>
   <name>room_type</name>  
   </parameters>
   </tool_description> 

   <tool_description>
   <tool_usage>This tool is used to get all room types</tool_usage>
   <tool_name>get_room_types</tool_name>
   <parameters></parameters>
   </tool_description> 
<tool_set>
"""
# In memory room DB
room_details = [{"room_number": 100, "room_type": "Super deluxe", "room_availability_dates": ['2024-05-01', '2024-05-15', '2024-05-16']},
                {"room_number": 101, "room_type": "Deluxe", "room_availability_dates": ['2024-06-02', '2024-05-10', '2024-05-30']},
                {"room_number": 102, "room_type": "Classic", "room_availability_dates": ['2024-05-03', '2024-05-15', '2024-05-16']},
                {"room_number": 1008, "room_type": "Suite", "room_availability_dates": ['2024-06-01', '2024-05-15', '2024-05-16']},
                {"room_number": 1009, "room_type": "Suite", "room_availability_dates": ['2024-05-01', '2024-05-09', '2024-05-08']},
                {"room_number": 1010, "room_type": "Classic", "room_availability_dates": ['2024-05-21', '2024-05-18', '2024-05-17']},
                {"room_number": 1011, "room_type": "Mansion", "room_availability_dates": ['2024-05-01', '2024-05-15', '2024-05-16']},
                {"room_number": 1012, "room_type": "Villa", "room_availability_dates": ['2024-05-11', '2024-05-15', '2024-05-16']},
                {"room_number": 501, "room_type": "Super deluxe", "room_availability_dates": ['2024-05-13', '2024-05-15', '2024-05-16']},
                {"room_number": 502, "room_type": "Deluxe", "room_availability_dates": ['2024-05-01', '2024-05-17', '2024-05-16']},
                {"room_number": 503, "room_type": "Classic", "room_availability_dates": ['2024-05-01', '2024-05-19', '2024-05-16']},
                {"room_number": 901, "room_type": "Suite", "room_availability_dates": ['2024-05-01', '2024-05-21', '2024-05-16']},
                {"room_number": 902, "room_type": "Suite", "room_availability_dates": ['2024-05-21', '2024-05-22', '2024-05-23']},
                {"room_number": 905, "room_type": "Super deluxe", "room_availability_dates": ['2024-05-01', '2024-05-15', '2024-05-16']}
                ]


def check_room_availability_by_date(date: str):
    for room in room_details:
        if date in room['room_availability_dates']:
            return room
    return None


def check_room_availability_by_room_type(room_type: str):
    for room in room_details:
        if room_type in room['room_type']:
            return room
    return None


def get_room_types():
    room_types = []
    for room in room_details:
        room_types.append(room['room_type'])
    return room_types

