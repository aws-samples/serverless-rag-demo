import boto3
from os import getenv
import json
from agent_executor_utils import upload_object_to_s3

code_gen_agent_name = "Code Generator Agent"
# When to use this agent
code_gen_agent_uses = f""" 
Use the {code_gen_agent_name} if:
   1. If the user wants to generate any kind of application or code.
"""

# Agent use examples
code_gen_agent_use_examples = f"""
How would I write a code to generate a fibonnaci series -> Use the {code_gen_agent_name} to generate the javascript html single page code
How would I create my own calculator -> Use the {code_gen_agent_name} to generate the javascript html single page code
How would I create a class that generates prime numbers -> Use the {code_gen_agent_name} to generate the javascript html single page code
Plot this chart ->  Use the {code_gen_agent_name} to generate the javascript html single page code
"""

# Agent success criteria
code_gen_agent_stop_condition = f"""
  This {code_gen_agent_name} agent successfully generates the javascript code
"""

code_gen_specs = f"""\
<agent_name>{code_gen_agent_name}</agent_name>
<tool_set>
	<instructions>
    1. You will generate the javascript html single page code.
    2. For other requirements, you could use other Javascript libraries as needed.
   </instructions>
	
    <tool_description>
		<tool_usage>This tool is used to generate structured python code</tool_usage>
		<tool_name>generate_HTML</tool_name>
		<parameters>
			<parameter>
				<name>user_query</name>
				<type>string</type>
				<description>Enter the user query based on which python code will be generated</description>
			</parameter>
            <parameter>
				<name>additional_data_points</name>
				<type>string</type>
				<description>Raw data points in the chat history that may be useful to create the HTML code</description>
			</parameter>
		</parameters>
	</tool_description>
	</tool_set>
"""

bedrock_client = boto3.client('bedrock-runtime')
model_id = getenv("CODE_GENERATOR_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")


def generate_HTML(user_query: str, additional_data_points: str =""):
    system_prompt = """You will generate structured syntactially correct HTML code only based on User query.
                    You will always generate syntactically correct single page HTML/Javascript/JQuery/CSS code.
                    The CSS/HTML/Javascript code should be part of a single file within the <html></html> tags.
                    <instructions>
                    1. You will generate the javascript html single page code.
                    2. For JQuery follow the process mentioned in <jq_steps> tags
                    <jq_steps>
                        a. Use JQuery by importing the below javascript. Do not use any other version of JQuery
                        <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.7.1/jquery.min.js"></script>
                    </jq_steps>
                    3. For CSS styling follow the process mentioned in <css_steps> tags
                    <css_steps>
                    a. Use Bootstrap by importing the below css
                    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@3.3.7/dist/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
                    </css_steps>
                    4.  For generating PDFs follow the process mentioned in <pdf_steps> tags.
                    <pdf_steps>
                    a. Use jsPDF by importing the below javascript. Do not use any other version of jsPDF
                    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/1.3.4/jspdf.min.js"></script>
                    </pdf_steps>
                    5. For icons follow the process mentioned in <icon_steps> tags
                    <icon_steps>
                    a. Use font-awesome by importing the below css
                    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
                    </icon_steps>
                    6. For other requirements, you could use other Javascript libraries as needed.
                    7. When generating Javascript code, you should not use any alert boxes that could freeze the UI.
                    8. Use the <html></html> tags to enclose the generated code.
                    </instructions>
                """
    
    user_prompt = user_query
    
    if additional_data_points != "":
        user_prompt = f"""The following context was provided by the user:
                        <context>
                        {additional_data_points} </context> 
                        <instructions>
                        When creating the HTML code you should consider the context available in <context></context> tags
                        You should generate a well formatted accurate presentation HTML
                        <instructions>  + {user_query}"""
    query_list = [
        {
            "role": "user",
            "content": user_prompt
        }
    ]

    prompt_template= {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 20000,
                        "system": system_prompt,
                        "messages": query_list
                    }
    
    print(f'Code Gen -> Prmpt template {prompt_template}')
    
    response = bedrock_client.invoke_model(
                body=json.dumps(prompt_template),
                modelId=model_id,
                accept='application/json',
                contentType='application/json'
    )

    llm_output = json.loads(response['body'].read())
    html_code = ''
    if 'content' in llm_output:
        html_code = llm_output['content'][0]['text']
        is_upload, upload_location = upload_object_to_s3(html_code, "html", "text/html")
    print(f'Code Gen -> HTML Code {html_code}')
    if(is_upload):
        return f"HTML Code created successfully at location <location>{upload_location}</location>"
    else:
        return f"HTML code generation failed {upload_location}"
