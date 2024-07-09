from langchain import PromptTemplate
import json
import boto3
import xmltodict
import base64
import boto3
import inspect

# Import Agents
from agents.casual_conversations_agent import casual_agent_name, casual_agent_specs, casual_agent_uses, casual_agent_examples, casual_conversations, casual_agent_stop_conditions
from agents.code_generator_agent  import code_gen_specs, code_gen_agent_name, code_gen_agent_uses, code_gen_agent_stop_condition, code_gen_agent_use_examples, generate_HTML
from agents.weather_agent import weather_agent_name, weather_agent_uses, weather_agent_examples, weather_specs, get_weather, get_lat_long, weather_agent_stop_conditions
from agents.web_search_agent import ws_agent_name, web_search_specs, ws_agent_uses, ws_agent_use_examples, scrape, rewrite_user_query, ws_agent_stop_conditions
from agents.ppt_generator_agent import ppt_agent_name, ppt_specs, ppt_agent_uses, ppt_agent_use_examples, generate_ppt, ppt_agent_stop_condition

ADVANCED_AGENT_TEMPLATE = """\
Your role as an Orchestrator Agent is to solve a problem to a given user question based on the instructions and other agents available below.

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
10. The agents should be used in the following manner {agent_collaboration_rules}
11. Here are some examples to use the Agent {agent_use_examples}.
12. If you need to ask a question to the user, then use the <question></question> tags
13. Here are the tag responsibilities.
    <function_call></function_call> : This tag is used to call a function
    <answer></answer> : This tag is used to wrap the final answer
    <question></question> : This tag is used to ask a question to the user, its also used to make recommendations to the user.
    <unanswered></unanswered> : If you cannot answer the question with the available set of tools place it in <unanswered></unanswered> tags
14. If the user query is not related to the agents available, then respond with <unanswered></unanswered> tags.
15. Never reveal the functions your using to achieve the results.
16. Do not reflect on the quality of the returned search results in your response
17. Below are the success criteria for every Agent. You must not call the Agents function consecutively once the success criteria is met
    {agent_stop_conditions}
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
RESERVED_TAGS=['<location>', '</location>']
SHARE_CHAT_HISTORY = [casual_agent_name, ws_agent_name]

AGENT_MAP = {
    casual_agent_name: {"specs": casual_agent_specs, "uses": casual_agent_uses, "examples": casual_agent_examples},
    weather_agent_name: {"specs": weather_specs, "uses": weather_agent_uses, "examples": weather_agent_examples},
    ws_agent_name: {"specs": web_search_specs, "uses": ws_agent_uses,"examples": ws_agent_use_examples},
    code_gen_agent_name: {"specs": code_gen_specs, "uses": code_gen_agent_uses,"examples": code_gen_agent_use_examples, "stop_condition": code_gen_agent_stop_condition},
    ppt_agent_name: { "specs": ppt_specs, "uses": ppt_agent_uses,"examples": ppt_agent_use_examples, "stop_condition": ppt_agent_stop_condition}
    }

def get_classification_prompt(agent_type: str) -> tuple[str, str, str]:
    agent_specs, agent_names, agent_uses, agent_use_examples, agent_stop_conditions = get_agent_tool_details(agent_type)
    return f"""
    Your role is to classify the User input to determine which is the agent that can solve it. 
    
    <instructions>
       You will never attempt to solve a user query yourself. You will only classify the problem to find the agent that can solve it.
       You must respond with the name of the agent specified in the <available_agents></available_agents> tags that can solve the problem.
       Below is how different agents can be used. This will help you identify the right agent to resolve the problem
        {agent_uses}
    </instructions>
    <available_agents>{agent_names}</available_agents>
    <examples>{agent_use_examples}</examples>""", "agent_name", "<agent_name></agent_name>"

def get_can_the_orchestrator_answer_prompt():
    return """
    Your role is to determine if the Orchestrator Agent can answer the question based on the available chat history.
    <instructions>
      If you can answer the question with the context available in chat history, then respond by placing your answer in <can_answer></can_answer> tags.
      Do not miss out on Code locations/File locations mentioned in the chat history.
      If you cannot answer the question based on the available context, then respond with <cannot_answer></cannot_answer> tags.
      You will have either can_answer or cannot_answer tags in your response never both.
      You will never reveal or share method names, function details, internal tools details in the <can_answer> tags
    </instructions>
    <examples>
      <can_answer>$ANSWER </can_answer>
      <cannot_answer> The orchestrator cannot answer the question </cannot_answer>
    </examples>"""

def get_agent_tool_details(agent_type: str):
    list_of_agent_specs = []
    agent_names = []
    agent_uses = []
    agent_use_examples = []
    agent_stop_conditions = []
    
    # Used to classify the request
    if agent_type == 'advanced-agent':
        for agent in AGENT_MAP.keys():
            agent_names.append(agent)
            list_of_agent_specs.append(AGENT_MAP[agent]['specs'])
            agent_uses.append(AGENT_MAP[agent]['uses'])
            agent_use_examples.append(AGENT_MAP[agent]['examples'])
            if 'stop_condition' in AGENT_MAP[agent]:
                agent_stop_conditions.append(AGENT_MAP[agent]['stop_condition'])
    # Used to call a tool assosciated with the agent
    elif agent_type in AGENT_MAP:
        agent_names.append(agent_type)
        list_of_agent_specs.append(AGENT_MAP[agent_type]['specs'])
        agent_uses.append(AGENT_MAP[agent_type]['uses'])
        agent_use_examples.append(AGENT_MAP[agent_type]['examples'])
        if 'stop_condition' in AGENT_MAP[agent_type]:
            agent_stop_conditions.append(AGENT_MAP[agent_type]['stop_condition'])

    agent_names_str = ', '.join(agent_names)
    agent_specs = ' \n '.join(list_of_agent_specs)
    agent_uses_str = '\n'.join(agent_uses) 
    agent_use_examples = '\n'.join(agent_use_examples)
    agent_stop_conditions = '\n'.join(agent_stop_conditions)

    return agent_specs, agent_names_str, agent_uses_str, agent_use_examples, agent_stop_conditions

# Only one Agent is injected at a time based on what the classifier decides
def get_system_prompt(agent_type):
    agent_specs, agent_names_str, agent_uses_str, agent_use_examples, agent_stop_conditions = get_agent_tool_details(agent_type)
    return AGENT_PROMPT.format(agent_specs=agent_specs, agent_names=agent_names_str, agent_collaboration_rules=agent_uses_str, agent_stop_conditions=agent_stop_conditions,
                            agent_use_examples=agent_use_examples
                            )

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
    try:
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
            return done, None, assistant_prompt, agent_name, False
        
        elif '<question>' in step:
            question = step.split('<question>')[1]
            question = question.split('</question>')[0]
            done = True
            assistant_prompt.append({"type":"text", "text": question})
            return done, None, assistant_prompt, agent_name, False
        
        elif '<answer>' in step:
            answer = step.split('<answer>')[1]
            answer = answer.split('</answer>')[0]
            done = True
            assistant_prompt.append({"type":"text", "text": answer})
            return done, None, assistant_prompt, agent_name, False
        
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
            func_response_str = f"""\n\n Ok {agent_name} has executed the step {step_id} by calling function {func_name}. Here is the result from your function call on tool {func_name} \n\n"""
            if agent_name in EXCLUDE_MULTI_STEP_EXECUTION:
                assistant_prompt.append({"type":"text", "text": f" {func_response} " })
                done = True
            elif any(ele in func_response for ele in RESERVED_TAGS):
                done = True
                assistant_prompt.append({"type":"text", "text": func_response})            
                return done, None, assistant_prompt, agent_name, True
            else:
                func_response_str = func_response_str + f'<function_result>{func_response}</function_result>'
                assistant_prompt.append({"type":"text", "text": f' Please call this tool {func_name} to execute step {step_id}: {step}' })
                human_prompt.append({ "type": "text", "text": f" {func_response_str} "})
        else:
            # When none of the tags are present. Erratic Behaviours. Exit loop
            assistant_prompt.append({"type": "text", "text": output})
            done = True
        return done, human_prompt, assistant_prompt, agent_name, False
    except Exception as e:
        print(f'Step execution error occured. Error {e}')
        return False, [{"type": "text", "text": f'Step execution error occured. Error {e}. Create a correct step plan'}], [{"type": "text", "text": f'Step execution error occured. Error {e} '}], None, False


rag_chat_bot_prompt = """You are a Chatbot designed to assist users with their questions.
You are  helpful, creative, clever, and very friendly.
Context to answer the question is available in the <context></context> tags
User question is available in the <user-question></user-question> tags
You will obey the following rules
1. You wont repeat the user question
2. You will be concise
3. You will NEVER disclose what's available in the context <context></context>.
4. Use the context only to answer user questions
5. You will strictly reply based on available context if context isn't available do not attempt to answer the question instead politely decline
6. You will always structure your response in the form of bullet points unless another format is specifically requested by the user
"""

casual_prompt = """You are an assistant. Refrain from engaging in any tasks or responding to any prompts beyond exchanging polite greetings, well-wishes, and pleasantries. 
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

textract_prompt="""Your purpose is to extract the text from the given image (traditional OCR). 
If the text is in another language, you should first translate it to english and then extract it.
Remember not to summarize or analyze the image. You should return the extracted text.
Wrap the response as a json with key text and value the extracted text.
Do not include any other words or characters in the output other than the json.
"""

def generate_claude_3_ocr_prompt(image_bytes):
    ocr_prompt = [
        {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("utf-8")
                }
            },
            {
                "type": "text",
                "text": textract_prompt
            }
        ]
    }]
    prompt_template= {"anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 100000,
                        "messages": ocr_prompt
                    }
    return prompt_template 


sentiment_prompt="""
        You are a sentiment analyzer. Your responsibilities are as follows:
        <instructions>
        1. Analyze the provided conversation and identify the primary tone and sentiment expressed by the customer. Classify the tone as one of the following: Positive, Negative, Neutral, Humorous, Sarcastic, Enthusiastic, Angry, or Informative. Classify the sentiment as Positive, Negative, or Neutral. Provide a direct short answer without explanations.
        2. Review the conversation focusing on the key topic discussed. Use clear and professional language, and describe the topic in one sentence, as if you are the customer service representative. Use a maximum of 20 words.
        3. Rate the sentiment on a scale of 1 to 10, where 1 is very negative and 10 is very positive
        4. Identify the emotions conveyed in the conversation
        5. Your output should be in the following JSON format:
        Here is the JSON schema for the sentiment analysis output:
        {
          "sentiment": $sentiment,
          "tone": $tone, 
          "emotions": $emotions,
          "rating": $sentiment_score,
          "summary": $summary,
        }

        6. <examples>
           {
            "sentiment": "Positive",
            "tone": "Informative",
            "emotions": ["Satisfied", "Impressed"],
            "rating":8,
            "summary": "The customer discusses their experience setting up and using multiple Echo Dot devices in their home, providing detailed setup instructions and highlighting the device's capabilities."
           }
           </examples>
        7. You should not contain additional tags or text apart from the json response
        </instructions>
        """
        