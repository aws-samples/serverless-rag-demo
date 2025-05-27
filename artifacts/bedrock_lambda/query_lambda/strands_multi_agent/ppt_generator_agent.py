import boto3
from os import getenv
import xmltodict
import json
import datetime
import secrets
import json
from pptx import Presentation
from pptx.util import Inches, Pt
from datetime import datetime, timedelta
import os
import base64
from botocore.exceptions import ClientError 
import base64
from PIL import Image
import io
import os
from strands import Agent, tool
from agent_executor_utils import bedrockModel
import logging

date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime("%B")
next_month_label = next_date.strftime("%B")
day = date.day
bedrock_client = boto3.client('bedrock-runtime')
s3_client = boto3.client('s3')
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")
cwd = os.getcwd() 
THEMES = ['strands_multi_agent/ppt_themes/ion_theme.pptx', 'strands_multi_agent/ppt_themes/circuit_theme.pptx']
cwd = getenv("LAMBDA_TASK_ROOT", 'var/')



PPT_GENERATOR_SYSTEM_PROMPT = """
You are a PPT Generator Agent. Your task is to generate a presentation on a given topic.
You have access to the following tools:
- generate_ppt: To generate a presentation on a given topic. 
                This tool will generate a presentation and upload it on s3.
                It will provide you the presigned S3 url where the presentation is uploaded in <location>...</location> tags.
                You should use this S3 url to display the presentation to the user.

Key Responsibilities:
- Generate a presentation on a given topic
- Use the tools to generate a presentation

General Instructions:
- Use only the following slide formats: 
    a. Title page
    b. Slide with bullet points
    c. Slide with text,
    d. Slide with 4 takeaways

Slide specific instructions:
- For the Title page slide:
    - The first slide must be a Title page
    - The title should be a single line
    - The subtitle should be a single line
    - The text should be a single line
    - The speaker notes should be a single line
    - The slide format should be Title page

- For the intermediate slides:
    - The slide number should be incremented for each new slide
    - The title should be a single line
    - The subtitle should be a single line
    - The text should be a single line
    - The speaker notes should be a single line
    - The slide format should be one of the following:
        - Slide with bullet points
        - Slide with text
        - Slide with image and text
        - Slide with image only

- For the final Key Takeaways slide:    
    - The slide number should be incremented for each new slide
    - The title should be a single line
    - The subtitle should be a single line
    - The text should be a single line
    - The speaker notes should be a single line
    - The slide format should be Slide with 4 takeaways

- xml structure:
    - <presentation>
        - <slides>
            - <slide>
            - <slide_number>
            - <title>
            - <subtitle>
            - <text>
            - <speaker_notes>
            - <slideFormat>
            - </slide>
        - </slides>
    - </presentation>

Remember to:
- Use a unique and relevant title, subtitle, text, and speaker notes for each slide
- Vary the slide formats to make the presentation engaging
- Follow the specified xml structure

You should use the tools to generate a presentation.
You should also follow the slide specific instructions.
You should also follow the general instructions.
You should pass on the presigned S3 url to the user.
"""

LOG = logging.getLogger("ppt_generator_agent")
LOG.setLevel(logging.INFO)

@tool
def ppt_generator_agent(topic, additional_data_points, number_of_slides=3):
    agent = Agent(system_prompt=PPT_GENERATOR_SYSTEM_PROMPT, model=bedrockModel, tools=[generate_ppt])
    content = f"""Topic: {topic}
                Additional Data Points: {additional_data_points}
                Number of Slides: {number_of_slides}"""
        
    agent_response = agent(content)
    return agent_response


@tool
def generate_ppt(ppt_content):
    LOG.info(f"""Presentation Content: {ppt_content} """)
    LOG.debug(f"PPT prompt {PPT_GENERATOR_SYSTEM_PROMPT}")
    
    presentation = ""
    if '<presentation>' in ppt_content and '</presentation>' in ppt_content:
        presentation = ppt_content.split('</presentation')[0]
        presentation = presentation.split('<presentation>')[1]
    try:
        slides_json = xmltodict.parse(presentation)
    except Exception as e:  
        print(f"Error parsing XML: {e}")
        # use LLM to correct the xml
        XML_CORRECTION_PROMPT = f"""
        You are an XML validator. The below xml is not valid and generated an error {e}
        Your taks is to correct the following xml. 
        {presentation}
        Return only the corrected xml and nothing else, no preamble.
        """
        agent = Agent(system_prompt=XML_CORRECTION_PROMPT, model=bedrockModel, tools=[])
        agent_response = agent(presentation)
        presentation = str(agent_response)
    try:
        return ppt(presentation)
    except Exception as e:
        print(f"PPT generation error: {e}")
        return "PPT generation failed - 0"
    


def ppt(slides_xml_str: str):
    print(f"ppt_xml= {slides_xml_str}")
    slides_json = {}
    # convert xml to json
    slides_json = xmltodict.parse(slides_xml_str)
    print(f"xml parsed as dict={slides_json}")
    if 'slides' in slides_json:
        slides_json = slides_json['slides']
        if 'slide' in slides_json:
            slides_json = slides_json['slide']
    print(f"final_slides_json={slides_json}")
    theme = secrets.choice(THEMES)
    print(f"Theme selected: {theme}")
    ppt = Presentation(theme)
    # On local machine, use the following line to create a new presentation
    # ppt = Presentation()

    for slide_json in slides_json:
        if slide_json["slideFormat"] == "Title page":
            title_slide_layout = ppt.slide_layouts[0]
            slide = ppt.slides.add_slide(title_slide_layout)
            title = slide.shapes.title
            subtitle = slide.placeholders[1]
            title.text = slide_json["title"]
            subtitle.text = slide_json["subtitle"]
        elif slide_json["slideFormat"] == "Slide with bullet points" or slide_json["slideFormat"]=="Slide with text":
            bullet_slide_layout = ppt.slide_layouts[1]
            slide = ppt.slides.add_slide(bullet_slide_layout)
            shapes = slide.shapes
            title_shape = shapes.title
            body_shape = shapes.placeholders[1]
            title_shape.text = slide_json["title"]
            tf = body_shape.text_frame
            slide_json["text"] = str(slide_json["text"]).replace("*** Bullet points ***", '')
            tf.text = slide_json["text"]
            
        elif slide_json["slideFormat"] == "Slide with 4 takeaways":
            takeways_slide_layout = ppt.slide_layouts[1]
            slide = ppt.slides.add_slide(takeways_slide_layout)
            shapes = slide.shapes
            title_shape = shapes.title
            slide.placeholders[1].text = slide_json['subtitle']
            # For adjusting the  Margins in inches  
            left = width = height = Inches(2)
            top = Inches(4)
            # creating textBox 
            txBox = slide.shapes.add_textbox(left, top, width, height) 
            tf = txBox.text_frame
            p = tf.add_paragraph() 
            p.font.size = Pt(14)
            p.font.bold = True
            p.font.italic = True
            p.text = slide_json["text"]
            
        elif slide_json["slideFormat"] == "Slide with image and text":
            # not done yet
            pass

    # img_path = "placeholder.png"
    print("PPT generated")
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
    file_extension = 'pptx'
    file_name = f"/tmp/sample_{date_time}.{file_extension}"
    ppt.save(file_name)
    print("PPT Saved")
    print("PPT Upload in progress")
    is_upload, upload_location = upload_file_to_s3(file_name, file_extension)
    if(is_upload):
        return f"Presentation created successfully at location <location>{upload_location}</location>"
    else:
        return "PPT creation failed"

# Generate Images
def generate_bedrock_images(context, image_placeholder):
    height = 576
    width = 384

    system_prompt = f""" Summarize the following content in comma separated abstract concepts, maximum 20 words. 
            The text will be used to generate a representative image with Stable Diffusion. Remove preamble when anwering.
            """ + context
    model_id = 'amazon.titan-image-generator-v1'
    
    body = json.dumps({"taskType": "TEXT_IMAGE","textToImageParams": {
            "text": system_prompt
        },
        "imageGenerationConfig": {"numberOfImages": 1,
            "height": height, 
            "width": width,
            "cfgScale": 8.0, "seed": 1
        }
    })
    try:
        image_bytes = generate_image(model_id=model_id, body=body)
        image = Image.open(io.BytesIO(image_bytes))
        image.save(cwd+"/tmp/test_image.jpg")
        image_placeholder.insert_picture(cwd+'/tmp/test_image.jpg')
    except ClientError as err:
        message = err.response["Error"]["Message"]
        print("A client error occurred:", message)
        print("A client error occured: " + format(message))
    except Exception as err:
        print(err.message)
    else:
        print(f"Finished generating image with Amazon Titan Image Generator G1 model {model_id}.")

def generate_image(model_id, body):
    print("Generating image with Amazon Titan Image Generator G1 model", model_id)
    accept = "application/json"
    content_type = "application/json"

    response = bedrock_client.invoke_model(
        body=body, modelId=model_id, accept=accept, contentType=content_type
    )
    response_body = json.loads(response.get("body").read())

    base64_image = response_body.get("images")[0]
    base64_bytes = base64_image.encode('ascii')
    image_bytes = base64.b64decode(base64_bytes)

    finish_reason = response_body.get("error")

    if finish_reason is not None:
        print(f"Error Image generation error. Error is {finish_reason}")
        return None
    
    print("Successfully generated image with Amazon Titan Image Generator G1 model", model_id)
    return image_bytes

def upload_file_to_s3(file_name, file_extension):
    try:
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
        s3_key = f"{file_extension}/sample_{date_time}.{file_extension}"
        s3_client.upload_file(file_name, s3_bucket_name, s3_key)
        s3_presigned = generate_presigned_url(s3_key)
        if s3_presigned is not None:
            return True, s3_presigned
        return True, s3_key
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False, f'Error {e}'

# Generate a presigned get url for s3 file
def generate_presigned_url(s3_key):
    try:
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': s3_bucket_name,
                'Key': s3_key
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )
        return presigned_url
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None


# if __name__ == "__main__":
#     print(generate_ppt_agent("The Wonderful World of Cats", "Beautifull cats", 3))


# xml = """
# <presentation>
#   <slides>
#     <slide>
#       <slide_number>1</slide_number>
#       <title>Amazon Web Services (AWS)</title>
#       <subtitle>The Cloud Computing Platform for Modern Businesses</subtitle>
#       <text>Presented by: Cloud Solutions Expert</text>
#       <speaker_notes>Introduction to AWS and its key service categories.</speaker_notes>
#       <slideFormat>Title page</slideFormat>
#     </slide>
#     <slide>
#       <slide_number>2</slide_number>
#       <title>Core AWS Service Categories</title>
#       <subtitle>Building blocks for your cloud infrastructure</subtitle>
#       <text>• Compute: EC2, Lambda, ECS, Fargate
# • Storage: S3, EBS, Glacier, Storage Gateway
# • Database: RDS, DynamoDB, Aurora, Redshift
# • Networking: VPC, Route 53, CloudFront
# • Security: IAM, Shield, WAF, GuardDuty</text>
#       <speaker_notes>AWS offers over 200 services across multiple categories.</speaker_notes>
#       <slideFormat>Slide with bullet points</slideFormat>
#     </slide>
#     <slide>
#       <slide_number>3</slide_number>
#       <title>Key Takeaways</title>
#       <subtitle>Why businesses choose AWS</subtitle>
#       <text>1. Comprehensive Service Portfolio
# 2. Global Infrastructure
# 3. Flexible Pricing
# 4. Security & Compliance</text>
#       <speaker_notes>AWS is the market leader in cloud computing.</speaker_notes>
#       <slideFormat>Slide with 4 takeaways</slideFormat>
#     </slide>
#   </slides>
# </presentation> 
# """
# generate_ppt(xml)

# test_ppt()