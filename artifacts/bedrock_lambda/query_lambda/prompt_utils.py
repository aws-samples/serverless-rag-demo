from langchain import PromptTemplate
import json
import boto3
import xmltodict
import base64
import boto3

# Import tools
from tools.weather_report_tool import get_weather_specs, get_lat_long, get_weather, weather_tool_name, weather_tool_description
from tools.stock_details_tool import get_stock_specs, get_stock_template, stock_tool_name, stock_tool_description
from tools.room_booking_tool import get_room_types, check_room_availability_by_date, check_room_availability_by_room_type, book_room, get_room_bookings_specs, room_booking_tool_name, room_tool_description

# An Agent with Multiple Tool sets
# A tool-set is a combination of tools to complete a task
# Tool-set1 (Check Weather) / Tool-set2 (Stock Performance) / Tool-set3 (Casual chat)
# Based on Intent -> call the relevant Agent
# Agent will use set of tools(series of functions) to get to the answer and respond
# 11. Never ask any questions
TOOL_TEMPLATE = """\
Your job is as an assistant is to solve a problem to a given <user-request> based on the instructions and tool sets below.

Use these Instructions: 
1. In this environment you have access to a set of tools :- {tool_names} that you will always use to answer the question.
2. These tools are function calls, you can call these function by using the <function_call> format below defined below. 
3. You will always solve a problem step by step using the available tools. Every step with have a single function call or a final answer or a question. Every Step should be numbered check the example below.
4. You will never assume anything especially function results. These results will be provided to you.
4. Once you truly know the final answer to the question only then place the answer in <answer></answer> tags within a step. Make sure to answer in a full sentence which is friendly.
5. Remember not to unnecessarily add the <answer> tags while listing down steps to solve the problem. Use the <answer> tags only when you have an answer
6. If none of the tools at your disposable can answer the question, then wrap your response within <unanswered></unanswered> tags.
7. The tools will help you solve the following queries: {tools_description}
8. Any recommendations from tools should be placed in <question></question> tags
9. Here are the tag responsibilities.
    <function_call></function_call> : This tag is used to call a function
    <answer></answer> : This tag is used to wrap the final answer
    <question></question> : This tag is used to ask a question to the user, its also used to make recommendations to the user.
    <unanswered></unanswered> : If you cannot answer the question with the available set of tools place it in <unanswered></unanswered> tags

<step_0>
<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>
</step_0>

<step_1>
<function_call>
<invoke>
<tool_name>$TOOL_NAME</tool_name>
<parameters>
<$PARAMETER_NAME>$PARAMETER_VALUE</$PARAMETER_NAME>
...
</parameters>
</invoke>
</function_call>
</step_1>

<step_2>
<question> ... </question>
</step_2>


Example:
<step_0>
  <function_call>
    <invoke>
    <tool_name>get_lat_long</tool_name>
    <parameters>
        <place>Pokharan, Thane</place>
    </parameters>
    </invoke>
  </function_call>
</step_0>
<step_1>
  <function_call>
    <invoke>
    <tool_name>get_weather</tool_name>
    <parameters>
        <latitude>35</latitude>
        <longitude>35</longitude>
    </parameters>
    </invoke>
  </function_call>
</step_1>
<step_2>
<answer>The weather in Pokharan, thane is 17 degree celcius</answer>
</step_2>


Here are the tools available:
<tools>
{tools_string}
</tools>

"""

# Human: What is the first step in order to solve this problem?
# Assistant:


TOOL_PROMPT = PromptTemplate.from_template(TOOL_TEMPLATE)


def get_agent_tool_details(agent_type: str):
    list_of_tools_specs = []
    tool_names = []
    tool_descriptions = []
    
    if agent_type == 'hotel-agent':
        tool_names.append(room_booking_tool_name)
        list_of_tools_specs.append(get_room_bookings_specs)
        tool_descriptions.append(room_tool_description)

    elif agent_type == 'weather-agent':
        tool_names.append(weather_tool_name)
        list_of_tools_specs.append(get_weather_specs)
        tool_descriptions.append(weather_tool_description)

    elif agent_type == 'stock-agent':
        tool_names.append(stock_tool_name)
        list_of_tools_specs.append(get_stock_specs)
        tool_descriptions.append(stock_tool_description)
    
    else:
        tool_names.append(stock_tool_name)
        tool_names.append(weather_tool_name)
        tool_names.append(room_booking_tool_name)

        list_of_tools_specs.append(get_stock_specs)
        list_of_tools_specs.append(get_weather_specs)
        list_of_tools_specs.append(get_room_bookings_specs)

        tool_descriptions.append(stock_tool_description)
        tool_descriptions.append(weather_tool_description)
        tool_descriptions.append(room_tool_description)
    
    tool_names_str = ', '.join(tool_names)
    tools_string = ''.join(list_of_tools_specs)
    tool_descriptions_str=', '.join(tool_descriptions)

    return tools_string, tool_names_str, tool_descriptions_str


def get_system_prompt(agent_type):
    tools_string, tool_names_str, tool_descriptions_str = get_agent_tool_details(agent_type)
    return TOOL_PROMPT.format(tools_string=tools_string, tool_names=tool_names_str, tools_description=tool_descriptions_str)

def call_function(tool_name, parameters):
    func = globals()[tool_name]
    #print(func, tool_name, parameters)
    if parameters is not None:
        output = func(**parameters)
    else:
        output = func()
    return output


def agent_execution_step(step_id, output):
    assistant_prompt = []
    human_prompt = []
    step = output
    # first check if the model has answered the question
    # parse the output for any 
    if f'<step_{step_id}>' in output:
        step = output.split(f'<step_{step_id}>')[1]
        step = step.split(f'</step_{step_id}>')[0]
    done = False
    
    if '<unanswered>' in step:
        unanswered = step.split('<unanswered>')[1]
        unanswered = unanswered.split('</unanswered>')[0]
        done = True
        assistant_prompt.append({"type":"text", "text": unanswered})
        return done, None, assistant_prompt
    
    elif '<question>' in step:
        question = step.split('<question>')[1]
        question = question.split('</question>')[0]
        done = True
        assistant_prompt.append({"type":"text", "text": question})
        return done, None, assistant_prompt
    
    elif '<answer>' in step:
        answer = step.split('<answer>')[1]
        answer = answer.split('</answer>')[0]
        done = True
        assistant_prompt.append({"type":"text", "text": answer})
        return done, None, assistant_prompt
    
    # if the model has not answered the question, go execute a function
    elif '<function_call>' in step:
        function_xml = step.split('<function_call>')[1]
        function_xml = function_xml.split('</function_call>')[0]
        function_dict = xmltodict.parse(function_xml)
        func_name = function_dict['invoke']['tool_name']
        parameters={}
        if 'parameters' in function_dict['invoke']:
            parameters = function_dict['invoke']['parameters']

        #print(f"agent_execution_step:: func_name={func_name}::params={parameters}::function_dict={function_dict}::")
        # call the function which was parsed
        func_response = None
        try:
            func_response = call_function(func_name, parameters)
        except Exception as e:
            func_response = f"Exception {e} occured when executing function {func_name}. "

        # create the next human input
        func_response_str = f'\n\n Ok we have executed step {step_id}. Here is the result from your function call on tool {func_name} \n\n'
        func_response_str = func_response_str + f'<function_result>\n{func_response}\n</function_result>'
        func_response_str = func_response_str + '\n\n If you know the answer, say it. If not, what is the next step?\n\n'
        assistant_prompt.append({"type":"text", "text": f' Please call this tool {func_name} to execute step {step_id}: {step}' })
        human_prompt.append({ "type": "text", "text": f"""
                                                        {func_response_str}
                                                    """})
    else:
        # When the model disobeys are initial plan
        assistant_prompt({"type": "text", "text": output})
        done = True
    
        
    return done, human_prompt, assistant_prompt

