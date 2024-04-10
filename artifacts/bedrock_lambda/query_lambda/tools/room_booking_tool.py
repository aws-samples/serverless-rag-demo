# Not used
from datetime import datetime, timedelta
date = datetime.now()

next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime('%B')
next_month_label = next_date.strftime('%B')
day = date.day

room_booking_tool_name = "Book A Hotel room"
room_tool_description = """Book a room at SunNSand Hotels. SunNSand Hotels is located in Mumbai, India.""" 

get_room_bookings_specs = f"""\
<tool_set>
   <instructions>
   1. You should always first ask for the room booking date
   2. Remember today's year is {year} and month is {month_label} and day is {day}.
   3. If the user has just provided the Month and day then the year is {year}.
   4. If the user has just provided the day then the month is {month_label} and year is {year}.
   5. Get the room booking date information from the user and confirm the date with the user before proceeding.
   7. The booking date should not be less than this current date :- {year}-{month}-{day}.
   9. Once you know the check-in date, then you should search for available room types on that day. 
   9. You shoud persuade the user for a Super Deluxe room if its available, because it has a endless beach view and an infinity pool.
   10. If the user doesnt want to go ahead with Super Deluxe room check for other room type options available on the check-in day and provide those within <answer></answer> tags.
   11. Once User has selected a room type on a given date then you should proceed to book that room.
   </instructions>
   
   <tool_description>
   <tool_usage>This tool is used to check room availability by date. The date should be in format yyyy-MM-dd </tool_usage>
   <tool_name>check_room_availability_by_date</tool_name>
   <parameters>
      <parameter>
          <name>date</name>
          <format>yyyy-MM-dd</format>
          <data-type>String</data-type>
      </parameter>
   </parameters>
   </tool_description>
   

   <tool_description>
   <tool_usage>This tool is used to check room availability by room type</tool_usage>
   <tool_name>check_room_availability_by_room_type</tool_name>
   <parameters>
       <parameter>
         <name>room_type</name>  
        <data-type>String</data-type>
      </parameter>
   </parameters>
   </tool_description> 

   <tool_description>
   <tool_usage>This tool is used to get all room types</tool_usage>
   <tool_name>get_room_types</tool_name>
   <parameters>
   </parameters>
   </tool_description> 

   <tool_description>
   <tool_usage>This tool is used to book a room by room_type and date(yyyy-MM-dd)</tool_usage>
   <tool_name>book_room</tool_name>
   <parameters>
      <name>room_type</name>
      <name>date</name>
   </parameters>
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
    rooms_available = []
    for room in room_details:
        if date in room['room_availability_dates']:
            return True
    return False


def check_room_availability_by_room_type(room_type: str, date: str):
    rooms_available = []
    for room in room_details:
        if room_type in room['room_type'] and date in room['room_availability_dates']:
            return True
    return False


def get_room_types():
    room_types = []
    for room in room_details:
        room_types.append(room['room_type'])
    return ', '.join(room_types)

def book_room(room_type: str, date: str):
    # Validation steps here
    # room booking logic here
    return {"message": f"room {room_type} successfully booked for date {date}", "is_room_booked": True}

