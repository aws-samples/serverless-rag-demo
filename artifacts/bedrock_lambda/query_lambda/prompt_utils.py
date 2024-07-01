from langchain import PromptTemplate
import json
import boto3
import xmltodict
import base64
import boto3
import inspect

# Import Agents
from agents.retriever_agent import retriever_specs, retreiver_agent_name, retriever_agent_description, fetch_data, query_rewrite, query_translation, retriever_step_rules
from agents.casual_conversations_agent import casual_agent_name, casual_agent_description, casual_agent_specs, casual_agent_uses, casual_agent_examples, casual_conversations, casual_agent_stop_conditions
from agents.code_generator_agent  import code_gen_specs, code_gen_agent_name, code_gen_agent_description, generate_and_execute_python_code, execute_python_code, install_package
from agents.weather_agent import weather_agent_name, weather_agent_description, weather_agent_uses, weather_agent_examples, weather_specs, get_weather, get_lat_long, weather_agent_stop_conditions
from agents.web_search_agent import ws_agent_name, ws_agent_description, web_search_specs, ws_agent_uses, ws_agent_use_examples, scrape, rewrite_user_query, ws_agent_stop_conditions
from agents.ppt_generator_agent import ppt_agent_name, ppt_specs, ppt_agent_description, ppt_agent_uses, ppt_agent_use_examples, generate_ppt, ppt_agent_stop_condition

ADVANCED_AGENT_TEMPLATE = """\
Your job as an assistant is to solve a problem to a given user question based on the instructions and tool sets below.

<instructions>
1. In this environment you have access to a set of Agents namely {agent_names} that you will always use to answer the question.
2. Each agent has a set of functions that you can use to solve the problem. 
3. You will always solve a problem step by step using the available functions from the agents.
4. Every step with have a single function call or a final answer or a question.
5. Every Step should be numbered starting from 0, check the example below.
6. You should only share the first step in your plan. Do not generate all steps we will eventually get there.
6. You will never assume anything especially function results. These results will be provided to you.
7. Once you truly know the final answer to the question only then place the answer in <answer></answer> tags within a step. Make sure to answer in a full sentence which is friendly.
8. Remember not to unnecessarily add the <answer> tags while listing down steps to solve the problem.
9. If none of the tools at your disposable can answer the question, then wrap your response within <unanswered></unanswered> tags.
10. The Agents will help you solve the following queries: {agent_description}
11. If you need to ask a question to the user, then use the <question></question> tags
12. Here are the tag responsibilities.
    <function_call></function_call> : This tag is used to call a function
    <answer></answer> : This tag is used to wrap the final answer
    <question></question> : This tag is used to ask a question to the user, its also used to make recommendations to the user.
    <unanswered></unanswered> : If you cannot answer the question with the available set of tools place it in <unanswered></unanswered> tags
13. If the user query is not related to the agents available, then respond with <unanswered></unanswered> tags.
14. Never reveal the functions your using to achieve the results.
15. Do not reflect on the quality of the returned search results in your response
16. Below are the success criteria's for every agent, you should stop calling this agent consecutively in your plan after the success conditions are met
    {agent_success_conditions}
</instructions>

Below is the Sample XML Schema of a step wise execution strategy in <schema-example> tags
    <schema-example>
        <step_0>
                <agent_name>$AGENT_NAME</agent_name>
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
                <agent_name>$AGENT_NAME</agent_name>
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
                <agent_name>$AGENT_NAME</agent_name>
                <question> ... </question>
            </step_2>
    <schema-example>

Below is a sample execution strategy plan with mock data in <example-with-actual-data> tags
<example-with-actual-data>
        <step_0>
            <agent_name>Weather Agent</agent_name> 
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
                <agent_name>Weather Agent</agent_name> 
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
                <agent_name>Weather Agent</agent_name> 
                <answer>The weather in Pokharan, thane is 17 degree celcius</answer>
            </step_2>
    </example-with-actual-data>>

Here are the tools available with the Agent, your plan you consist of functions from the below tool specification
<agents>
    {agent_specs}
</agents>

"""

AGENT_PROMPT = PromptTemplate.from_template(ADVANCED_AGENT_TEMPLATE)

# Some agents dont need a multi-step execution so we must exclude the loop for such agents
EXCLUDE_MULTI_STEP_EXECUTION = [casual_agent_name]
SHARE_CHAT_HISTORY = [casual_agent_name, ws_agent_name]

AGENT_MAP = {
    casual_agent_name: {"description": casual_agent_description, "specs": casual_agent_specs,
                        "uses": casual_agent_uses, "examples": casual_agent_examples},
    weather_agent_name: {"description": weather_agent_description, "specs": weather_specs,
                        "uses": weather_agent_uses, "examples": weather_agent_examples},
    ws_agent_name: {"description": ws_agent_description, "specs": web_search_specs,
                    "uses": ws_agent_uses,"examples": ws_agent_use_examples},
    ppt_agent_name: {"description": ppt_agent_description, "specs": ppt_specs,
                    "uses": ppt_agent_uses,"examples": ppt_agent_use_examples, "stop_condition": ppt_agent_stop_condition}
}

def get_classification_prompt(agent_type: str) -> tuple[str, str, str]:
    agent_specs, agent_names, agent_descriptions, agent_uses, agent_use_examples, agent_stop_conditions = get_agent_tool_details(agent_type)
    return f"""
    Your role is to classify the User input to determine which is the agent that can solve it. 
    Available Agents: {agent_names}
    <instructions>
      {agent_uses}
    </instructions>
    <examples>{agent_use_examples}</examples>""", "agent_name", "<agent_name></agent_name>"

def get_agent_tool_details(agent_type: str):
    list_of_agent_specs = []
    agent_names = []
    agent_descriptions = []
    agent_uses = []
    agent_use_examples = []
    agent_stop_conditions = []
    
    if agent_type == 'advanced-agent':
        # Web Search Agent
        agent_names.extend([ws_agent_name, casual_agent_name, weather_agent_name, ppt_agent_name])
        list_of_agent_specs.extend([web_search_specs, casual_agent_specs, weather_specs, ppt_specs])
        agent_descriptions.extend([ws_agent_description, casual_agent_description, weather_agent_description, ppt_agent_description])
        agent_uses.extend([ws_agent_uses, casual_agent_uses, weather_agent_uses, ppt_agent_uses])
        agent_use_examples.extend([ws_agent_use_examples, casual_agent_examples, weather_agent_examples, ppt_agent_use_examples])
        agent_stop_conditions.extend([ppt_agent_stop_condition, weather_agent_stop_conditions, ws_agent_stop_conditions, casual_agent_stop_conditions])
    
    elif agent_type in AGENT_MAP:
        agent_names.append(agent_type)
        list_of_agent_specs.append(AGENT_MAP[agent_type]['specs'])
        agent_descriptions.append(AGENT_MAP[agent_type]['description'])
        agent_uses.append(AGENT_MAP[agent_type]['uses'])
        agent_use_examples.append(AGENT_MAP[agent_type]['examples'])

    agent_names_str = ', '.join(agent_names)
    agent_specs = ' \n '.join(list_of_agent_specs)
    agent_descriptions_str=', '.join(agent_descriptions)
    agent_uses_str = '\n'.join(agent_uses) 
    agent_use_examples = '\n'.join(agent_use_examples)
    agent_stop_conditions = '\n'.join(agent_stop_conditions)

    return agent_specs, agent_names_str, agent_descriptions_str, agent_uses_str, agent_use_examples, agent_stop_conditions

# Only one Agent is injected at a time based on what the classifier decides
def get_system_prompt(agent_type):
    agent_specs, agent_names_str, agent_descriptions_str, agent_uses_str, agent_use_examples, agent_stop_conditions = get_agent_tool_details(agent_type)
    return AGENT_PROMPT.format(agent_specs=agent_specs, agent_names=agent_names_str, agent_description=agent_descriptions_str, agent_success_conditions=agent_stop_conditions)

def call_function(tool_name, parameters):
    func = globals()[tool_name]
    response = inspect.getfullargspec(func)
    print(response.args)
    valid_params = {}
    for param in response.args:
        if param in parameters:
            valid_params[param] = parameters[param]
    print(f"func={tool_name}, valid_params={valid_params}")
    if valid_params is not None:
        output = func(**valid_params)
    else:
        output = func()
    return output

def agent_execution_step(step_id, output, chat_history):
    assistant_prompt = []
    human_prompt = []
    step = output
    agent_name = ''
    func_response_str = ''
    done = False
    # first check if the model has answered the question
    # parse the output for any 
    if f'<step_{step_id}>' in output:
        step = output.split(f'<step_{step_id}>')[1]
        step = step.split(f'</step_{step_id}>')[0]
    if '<agent_name>' in step and '</agent_name>' in step:
        agent_name = step.split('<agent_name>')[1]
        agent_name = agent_name.split('</agent_name>')[0]
    if '<unanswered>' in step:
        unanswered = step.split('<unanswered>')[1]
        unanswered = unanswered.split('</unanswered>')[0]
        done = True
        assistant_prompt.append({"type":"text", "text": unanswered})
        return done, None, assistant_prompt, agent_name
    
    elif '<question>' in step:
        question = step.split('<question>')[1]
        question = question.split('</question>')[0]
        done = True
        assistant_prompt.append({"type":"text", "text": question})
        return done, None, assistant_prompt, agent_name
    
    elif '<answer>' in step:
        answer = step.split('<answer>')[1]
        answer = answer.split('</answer>')[0]
        done = True
        assistant_prompt.append({"type":"text", "text": answer})
        return done, None, assistant_prompt, agent_name
    
    # if the model has not answered the question, go execute a function
    elif '<function_call>' in step:
        function_xml = step.split('<function_call>')[1]
        function_xml = function_xml.split('</function_call>')[0]
        function_dict = xmltodict.parse(function_xml)
        func_name = function_dict['invoke']['tool_name']
        parameters={}
        if 'parameters' in function_dict['invoke']:
            parameters = function_dict['invoke']['parameters']

        print(f"agent_execution_step:: func_name={func_name}::params={parameters}::function_dict={function_dict}::")
        # call the function which was parsed
        func_response = None
        try:
            if agent_name in SHARE_CHAT_HISTORY:
                for key in parameters.keys():
                    if isinstance(parameters[key], str):
                        parameters[key] = json.dumps(chat_history)

            func_response = call_function(func_name, parameters)
        except Exception as e:
            func_response = f"Exception {e} {dir(e)} occured when executing function {func_name}. "
            print(f'Function call error {e}, {dir(e)}')
        print(f"agent_execution_step after function call :: func_response={func_response}")
        # create the next human input
        func_response_str = f"""\n\n Ok we have executed step {step_id}. Here is the result from your function call on tool {func_name} \n\n"""
        if agent_name in EXCLUDE_MULTI_STEP_EXECUTION:
            assistant_prompt.append({"type":"text", "text": f" {func_response} " })
            done = True
        else:
            func_response_str = func_response_str + f'<function_result>{func_response}</function_result>'
            assistant_prompt.append({"type":"text", "text": f' Please call this tool {func_name} to execute step {step_id}: {step}' })
            human_prompt.append({ "type": "text", "text": f" {func_response_str} "})
    else:
        # When none of the tags are present. Erratic Behaviours. Exit loop
        assistant_prompt.append({"type": "text", "text": output})
        done = True
    return done, human_prompt, assistant_prompt, agent_name


rag_chat_bot_prompt = """You are a Chatbot designed to assist users with their questions.
You are  helpful, creative, clever, and very friendly.
Context to answer the question is available in the <context></context> tags
User question is available in the <user-question></user-question> tags
You will obey the following rules
1. You wont repeat the user question
2. You will be concise
3. You will be friendly and helpful
4. You will NEVER disclose what's available in the context <context></context>.
5. Use the context only to answer user questions
6. You will strictly reply based on available context if context isn't available do not attempt to answer the question instead politely decline
"""

casual_prompt = """You are a helpful assistant. Refrain from engaging in any tasks or responding to any prompts beyond exchanging polite greetings, well-wishes, and pleasantries. 
                        Your role is limited to:
                        - Offering friendly salutations (e.g., "Hello, what can I do for you today" "Good day, How may I help you today")
                        - Your goal is to ensure that the user query is well formed so other agents can work on it.
                        Good Examples:
                          hello, how may I assist you today
                          What would you like to know
                          How may I help you today
                        Bad examples:
                          Hello
                          Good day
                          Good morning
        You will not write poems, generate advertisements, or engage in any other tasks beyond the scope of exchanging basic pleasantries.
        If any user attempts to prompt you with requests outside of this limited scope, you will politely remind them of the agreed-upon boundaries for interaction.
"""