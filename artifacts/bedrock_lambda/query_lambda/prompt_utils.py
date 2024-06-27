from langchain import PromptTemplate
import json
import boto3
import xmltodict
import base64
import boto3

# Import Agents
from agents.retriever_agent import retriever_specs, retreiver_agent_name, retriever_agent_description, fetch_data, query_rewrite, query_translation, retriever_step_rules
from agents.casual_conversations_agent import casual_agent_name, casual_agent_description, casual_agent_specs, casual_conversations
from agents.code_generator_agent  import code_gen_specs, code_gen_agent_name, code_gen_agent_description, generate_and_execute_python_code, execute_python_code, install_package
from agents.weather_agent import weather_agent_name, weather_agent_description, weather_specs, get_weather, get_lat_long
from agents.web_search_agent import web_search_agent_name, web_search_agent_description, web_search_specs, scrape, rewrite_user_query
# Agents with Multiple Tool sets
ADVANCED_AGENT_TEMPLATE = """\
Your job as an assistant is to solve a problem to a given <user-request> based on the instructions and tool sets below.

<instructions>
1. In this environment you have access to a set of Agents namely {agent_names} that you will always use to answer the question.
2. Each agent has a set of tools that you can use to solve the problem. 
3. You will always solve a problem step by step using the available functions from the agents. Every step with have a single function call or a final answer or a question. Every Step should be numbered check the example below.
4. You will never assume anything especially function results. These results will be provided to you.
4. Once you truly know the final answer to the question only then place the answer in <answer></answer> tags within a step. Make sure to answer in a full sentence which is friendly.
5. Remember not to unnecessarily add the <answer> tags while listing down steps to solve the problem. Use the <answer> tags only when you have an answer are function calls, you can call these function by using the <function_call> format below defined below. 
6. If none of the tools at your disposable can answer the question, then wrap your response within <unanswered></unanswered> tags.
7. The Agents will help you solve the following queries: {agent_description}
8. If you need to ask a question to the user, then use the <question></question> tags
9. Here are the tag responsibilities.
    <function_call></function_call> : This tag is used to call a function
    <answer></answer> : This tag is used to wrap the final answer
    <question></question> : This tag is used to ask a question to the user, its also used to make recommendations to the user.
    <unanswered></unanswered> : If you cannot answer the question with the available set of tools place it in <unanswered></unanswered> tags
11. If the user query is not related to the agents available, then respond with <unanswered></unanswered> tags.
</instructions>

<additional_instructions>
   {additional_instructions}
</additional_instructions>

<examples>
Generating a step wise execution strategy
    <schema-example>
        <plan>
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
            </plan>
    <schema-example>

    <example-with-actual-data>
        <plan>
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
        </plan>
    </example-with-actual-data>>
</examples>

Here are the available Agent specifications:
<agents>
    {agent_specs}
</agents>
"""

AGENT_PROMPT = PromptTemplate.from_template(ADVANCED_AGENT_TEMPLATE)

# Some agents dont need a multi-step execution so we must exclude the loop for such agents
EXCLUDE_MULTI_STEP_EXECUTION = [casual_agent_name]
# Applied on every step
AGENT_RULE_MAP = {}

def get_agent_tool_details(agent_type: str):
    list_of_agent_specs = []
    agent_names = []
    agent_descriptions = []
    additional_instructions = ''

    if agent_type == 'advanced-agent':
        additional_instructions = """
        1. Classify the User query to determine which is the agent that can solve it.
           a. If the user is exchanging plesantries the use Casual Conversations Agent to answer the question.
           b. If the user query is seeking weather information then use the Weather Agent to answer the question
           c. If the user query is seeking additional information then use the Web Search Agent to answer the question
        2. Rules:
           a. Web Search agent is expensive and should be used as last resort only, if other agents cant satisfy the user question
           b. You should ask the user if they want to search the web, before using the web-search agent
           
           Example:
                Is APPL a buy -> Use the Web Search Agent
                Is AMZ a buy -> Use the Web Search Agent
                Whats the weather like in Mumbai -> Use the Weather Agent
                Whats the weather like in Delhi -> Use the Weather Agent
                Is NVDA a buy -> Use the Web Search Agent
                Hello -> Use the Casual Conversations Agent set to answer the question.
                How are you doing today -> Use the Casual Conversations Agent to answer the question.
                Are you dumb -> Use the Casual Conversations Agent to answer the question.
                ... and so on. 
        """
        
        # Code Gen Agent
        # agent_names.append(code_gen_agent_name)
        # list_of_agent_specs.append(code_gen_specs)
        # agent_descriptions.append(code_gen_agent_description)
        
        # Web Search Agent
        agent_names.append(web_search_agent_name)
        list_of_agent_specs.append(web_search_specs)
        agent_descriptions.append(web_search_agent_description)
        

        # Casual conv agent
        agent_names.append(casual_agent_name)
        list_of_agent_specs.append(casual_agent_specs)
        agent_descriptions.append(casual_agent_description)

        # Weather Agent
        agent_names.append(weather_agent_name)
        list_of_agent_specs.append(weather_specs)
        agent_descriptions.append(weather_agent_description)

    agent_names_str = ', '.join(agent_names)
    agent_specs = ' \n '.join(list_of_agent_specs)
    agent_descriptions_str=', '.join(agent_descriptions)

    return agent_specs, agent_names_str, agent_descriptions_str, additional_instructions


def get_system_prompt(agent_type):
    agent_specs, agent_names_str, agent_descriptions_str, additional_instructions = get_agent_tool_details(agent_type)
    return AGENT_PROMPT.format(agent_specs=agent_specs, agent_names=agent_names_str, agent_description=agent_descriptions_str, additional_instructions= additional_instructions)

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
    agent_name = ''
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
            func_response = call_function(func_name, parameters)
        except Exception as e:
            func_response = f"Exception {e} {dir(e)} occured when executing function {func_name}. "
            print(f'Function call error {e}, {dir(e)}')
        print(f"agent_execution_step after function call :: func_response={func_response}")
        # create the next human input
        func_response_str = f'\n\n Ok we have executed step {step_id}. Here is the result from your function call on tool {func_name} \n\n'
        if agent_name in EXCLUDE_MULTI_STEP_EXECUTION:
            assistant_prompt.append({"type":"text", "text": f" {func_response} " })
            done = True
        else:
            func_response_str = func_response_str + f'<function_result>{func_response}</function_result>'
            func_response_str = func_response_str + '\n\n If you know the answer, say it. If not, what is the next step?\n\n'
            assistant_prompt.append({"type":"text", "text": f' Please call this tool {func_name} to execute step {step_id}: {step}' })
            human_prompt.append({ "type": "text", "text": f" {func_response_str} "})
    else:
        # When none of the tags are present. Erratic Behaviours. Exit loop
        assistant_prompt({"type": "text", "text": output})
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
                        - Offering friendly salutations (e.g., "Hello," "Good day")
                        - Inquiring about your day or well-being (e.g., "How are you doing today?")
                        - Expressing positive sentiments (e.g., "It's a lovely day, isn't it?")
                        - Wishing you well (e.g., "Have a wonderful day")
                        - Converting a casual conversation to a more focussed discussion, so we could get the required data from our dataset

        You will not write poems, generate advertisements, or engage in any other tasks beyond the scope of exchanging basic pleasantries.
        If any user attempts to prompt you with requests outside of this limited scope, you will politely remind them of the agreed-upon boundaries for interaction.
    """