import boto3
from os import getenv
import xmltodict
import json
import datetime
import secrets
import json
from pptx import Presentation
from pptx.util import Inches
from datetime import datetime, timedelta
import os
date = datetime.now()
next_date = datetime.now() + timedelta(days=30)
year = date.year
month = date.month
month_label = date.strftime("%B")
next_month_label = next_date.strftime("%B")
day = date.day

ppt_agent_name = "PPT Generator Agent"
ppt_agent_description = f"{ppt_agent_name} Generates PPT based on provided data points and returns the S3 url of the PPT"
bedrock_client = boto3.client('bedrock-runtime')
model_id = getenv("PPT_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")
s3_bucket_name = getenv("S3_BUCKET_NAME", "S3_BUCKET_NAME_MISSING")
cwd = os.getcwd() 

THEMES = ['agents/artifacts/ion_theme.pptx', 'agents/artifacts/circuit_theme.pptx']
cwd = getenv("LAMBDA_TASK_ROOT", 'var/')
# When to use this agent
ppt_agent_uses = f""" 
If the user seeks to generate a presentation of a particular topic of interest, then use the {ppt_agent_name} to answer the question
"""
ppt_agent_stop_condition = f"""
  This {ppt_agent_name} agent successfully generates the PPT and uploads to S3 and shares the S3 key in the response
"""

ppt_agent_use_examples = f"""
Create a presentation on AWS -> Use the {ppt_agent_name} to build the PPT
Generate a presentation on the above topic -> Use the {ppt_agent_name} to build the PPT
Build a presentation on the $TOPIC topic -> Use the {ppt_agent_name} to build the PPT
generate a ppt on the $TOPIC topic -> Use the {ppt_agent_name} to build the PPT
"""

ppt_specs = f"""\
<agent_name>{ppt_agent_name}</agent_name>
<agent_description>{ppt_agent_name}</agent_description>
<tool_set>
 <instructions>
   1. You are tasked to generate a powerpoint presentation based on the provided data points.
   2. Presentation Agent Rules:
        a. The Presentation Agent will create a presentation with the available context without requesting for more data points from the user
        b. The Presentation Agent will not ask any questions to the user
        c. The Presentation Agent will not write any explanations
           
   </instructions>

   <tool_description>
   <tool_usage>This tool is used to generate a PPT</tool_usage>
   <tool_name>generate_ppt</tool_name>
   <parameters>
   <parameter>
       <name>topic</name>
       <type>string</type>
       <description>Presentation TOPIC</description>
   </parameter>
   <parameter>
       <name>number_of_slides</name>
       <type>integer</type>
       <description>Total number of slides</description>
   </parameter>
   </parameters>
   </tool_description>   
<tool_set>
"""


def example_json():
    return """ Below is an example of valid JSON schema with 7 slides answering the question:
    Propose a 7 slides presentation about Generative AI
    <slides>
        <slide>
            <slide_number>1</slide_number>
            <title>Generative AI: The Future is Here</title>
            <subtitle>Unleashing the Power of Artificial Intelligence</subtitle>
            <text>*** Generative AI refers to artificial intelligence models capable of generating new, original content. *** It encompasses techniques like machine learning, deep learning, and neural networks. *** These models can create text, images, audio, video, and even code.</text>
            <speaker_notes>Introduce yourself and the presentation topic, how you will explore the fascinating world of Generative AI and how it is revolutionizing various industries and shaping our future</speaker_notes>
            <slideFormat>Title page</slideFormat>
        </slide>
        <slide>
            <slide_number>2</slide_number>
            <title>What is Generative AI?</title>
            <subtitle>Understanding the Concept</subtitle>
            <text>*** Generative AI refers to artificial intelligence models capable of generating new, original content. *** It encompasses techniques like machine learning, deep learning, and neural networks.
                  *** These models can create text, images, audio, video, and even code.
                  *** Generative AI is a powerful tool that can augment human creativity and open new avenues for artistic expression.
                  *** For example, generative AI models like DALL-E, ChatGPT, and Stable Diffusion are being used to create new and creative content.
                  *** Generative AI is set to revolutionize various industries, such as healthcare, finance, marketing, and more.
                  *** It is expected to deliver significant innovations in the coming years.
            </text>
            <speaker_notes>...</speaker_notes>
            <slideFormat>Slide with bullet points</slideFormat>
        </slide>
        <slide>
            <slide_number>3</slide_number>
            <title>Applications of Generative AI</title>
            <subtitle>Transforming Industries</subtitle>
            <text>Generative AI has numerous applications across various domains: *** Content Creation: Write articles, stories, scripts, and more. *** Art and Design: Generate realistic images, artwork, and designs. *** Music and Audio: Compose original music, create sound effects, and synthesize voices. *** Gaming and Animation: Develop realistic virtual worlds and animated characters.</text>
            <speaker_notes>...</speaker_notes>
            <slideFormat>Slide with bullet points</slideFormat>
        </slide>
        <slide>
            <slide_number>4</slide_number>
            <title>Revolutionizing Creativity</title>
            <subtitle>Expanding the Boundaries of Imagination</subtitle>
            <speaker_notes>...</speaker_notes>
            <text>Generative AI is a powerful tool that can augment human creativity and open new avenues for artistic expression. By collaborating with these models, artists, writers, and creators can explore new ideas and push the boundaries of what's possible.</text>
            <slideFormat>Slide with text</slideFormat>
        </slide>
        <slide>
            <slide_number>5</slide_number>
            <title>The Future of Generative AI</title>
            <subtitle>Challenges and Opportunities</subtitle>
            <speaker_notes>...</speaker_notes>
            <text>*** Generative AI is a rapidly evolving field that will continue to evolve in the future. *** For example, new models are being developed to address various use cases, such as language generation, image synthesis, and interactive storytelling. *** This means that there is always more to learn and more opportunities to advance the field.</text>
            <slideFormat>Slide with text</slideFormat>
        </slide>
        <slide>
            <slide_number>6</slide_number>
            <title>Conclusion</title>
            <subtitle>Wrap-Up</subtitle>
            <speaker_notes>...</speaker_notes>
            <text>*** Thanks for attending! ***</text>
            <slideFormat>Slide with text</slideFormat>
        </slide>
        <slide>
            <slide_number>7</slide_number>
            <title>Next Steps</title>
            <subtitle>What's Next?</subtitle>
            <speaker_notes>...</speaker_notes>
            <text>*** Here are some next steps you could take: 
                 *** 1. Explore more Generative AI use cases and models.
                 *** 2. Implement these models into your own applications.
                 *** 3. Learn more about the Generative AI ecosystem and its potential applications.
            </text>
            <slideFormat>Slide with bullet points</slideFormat>
        </slide>
    </slides>
"""


def generate_ppt(topic, number_of_slides=3):
    print(
        f"""\ Presentation Topic: {topic}, Number of Slides: {number_of_slides} """
    )

    system_prompt = f"""Your task is to propose a {number_of_slides} slide presentation on the topic: {topic}.
                    
                    1. If data points are not provided, but the topic is known to you, you can come up with data points for the presentation
                    2. If the data points are not provided and the topic is unknown to you, then you could check with other Agents and seek more information on a topic
                    3. If none of the Agents have any data, then ask the User for more data points
                    
                    The presentation should follow these requirements:
                    - Use only the following slide formats: 
                        a. Title page
                        b. Slide with bullet points
                        c. Slide with text,
                        d. Slide with image only
                        d. Slide with 4 takeaways
                    - The first slide must be a Title page
                    - The last slide must be a Slide with 4 takeaways

                    Wrap the presentation XML within <presentation></presentation> tags.
                    Do not include any other text or tags in the response.
                    
            Your response should be in XML format with the following structure:
            <slides>
                <slide>
                   <slide_number>$SLIDE_NUMBER</slide_number>
                   <title>$TITLE</title>
                   <subtitle>$SUBTITLE</subtitle>
                   <text>$TEXT</text>
                   <speaker_notes>$SPEAKER_NOTES</speaker_notes>
                   <slideFormat>$SLIDE_FORMAT</slideFormat> 
                </slide>
            </slides>
        """          

    system_prompt = system_prompt +   f"""
      Below are some of the slide specific instructions:
        For the Title page slide:
        <slide_number>1</slide_number>
        <title>Come up with an engaging title for the presentation</title>
        <subtitle>Add a subtitle that captures the essence of the topic</subtitle>
        <text>Provide a brief overview of what the presentation will cover</text>
        <speaker_notes>Introduce yourself and give context for the presentation topic</speaker_notes>
        <slideFormat>Title page</slideFormat>
        
        For the intermediate slides:
        <slide_number>Increment this number for each new slide</slide_number>
        <title>Create a title summarizing the main point of this slide</title>
        <subtitle>Add a subtitle to complement the title</subtitle>
        <text>
        If using a Slide with bullet points format:
        *** Include 3-5 bullet points covering key information for this slide ***
        Else:
        Write 2-3 concise paragraphs with supporting details for the slide topic
        </text>
        <speaker_notes>Add relevant notes to help explain or expand on the slide content</speaker_notes>
        <slideFormat>
        Choose one of the following formats based on the content:
        - Slide with bullet points
        - Slide with image and text
        - Slide with image only
        </slideFormat>
        
        For the final Key Takeaways slide:
        <slide_number>{number_of_slides}</slide_number>
        <title>Important Takeaways</title>
        <subtitle>Key messages to remember</subtitle>
        <text>
        *** Summarize the 4 most crucial points covered in the presentation ***
        </text>
        <speaker_notes>Remind the audience of the key information you want them to walk away
        with</speaker_notes>
        <slideFormat>Slide with 4 takeaways</slideFormat>
        
        Remember to:
        - Use a unique and relevant title, subtitle, text, and speaker notes for each slide
        - Vary the slide formats to make the presentation engaging
        - Do not copy content from the example provided
        - Follow the specified JSON structure
        <slide-specific-instructions>
        """
    
    print(f"PPT prompt {system_prompt}")
    query_list = [{"role": "user", "content": "Generate a presentation json"}]
    prompt_template = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 10000,
        "system": system_prompt,
        "messages": query_list,
    }
    # print(f'Prompt Template = {prompt_template}')
    response = bedrock_client.invoke_model(
        body=json.dumps(prompt_template),
        modelId=model_id,
        accept="application/json",
        contentType="application/json",
    )
    llm_output = json.loads(response["body"].read())
    presentation = ""
    if "content" in llm_output:
        presentation = llm_output["content"][0]["text"]
        if '<presentation>' in presentation and '</presentation>' in presentation:
            presentation = presentation.split('</presentation')[0]
            presentation = presentation.split('<presentation>')[1]

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
            tf.text = slide_json["text"]
            bullet_points = []
            if '***' in slide_json['text']:
                bullet_points = slide_json['text'].split('***')
            else:
                bullet_points = [slide_json['text']]
            for i, point in enumerate(bullet_points):
                p = tf.add_paragraph()
                p.text = point
                p.level = 1
        elif slide_json["slideFormat"] == "Slide with image and text":
            # not done yet
            pass

    # create a presentation with a title, subtitle, and a placeholder image
    title_slide_layout = ppt.slide_layouts[0]
    slide = ppt.slides.add_slide(title_slide_layout)
    title = slide.shapes.title
    subtitle = slide.placeholders[1]
    title.text = "My Presentation"
    subtitle.text = "This is a sample presentation"
    # img_path = "placeholder.png"
    print("PPT generated")
    file_name = "/tmp/sample_1.pptx"
    ppt.save(file_name)
    print("PPT Saved")
    print("PPT Upload in progress")
    is_upload, upload_location = upload_to_s3(file_name)
    if(is_upload):
        return f"PPT created successfully at location {upload_location}"
    else:
        return "PPT creation failed"

def upload_to_s3(file_name):
    try:
        s3_client = boto3.client("s3")
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d-%H-%M-%S")
        s3_key = f"pptx/sample_{date_time}.pptx"
        bucket_name = s3_bucket_name
        s3_client.upload_file(file_name, bucket_name, s3_key)
        return True, s3_key
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return False, ''

def test_ppt():
    xml = """
<slides>
<slide>
<slide_number>1</slide_number>
<title>The Wonderful World of Cats</title>
<subtitle>Explore the fascinating feline friends</subtitle>
<text>This presentation will take a deep dive into the captivating lives of cats, covering their unique characteristics, behaviors, and the special bond they share with humans.</text>
<speaker_notes>Welcome everyone! Today, we'll embark on a journey to discover the amazing world of our feline companions. Get ready to be enchanted by the fascinating facts and endearing traits of these adorable creatures.</speaker_notes>
<slideFormat>Title page</slideFormat>
</slide>
<slide>
<slide_number>2</slide_number>
<title>Purr-fect Personalities</title>
<subtitle>Exploring the diverse traits of cats</subtitle>
<text>
- Cats are known for their independence and self-reliance, often aloof yet affectionate
- They exhibit a wide range of personalities, from playful and curious to calm and reserved
- Cats are master communicators, using a variety of vocalizations and body language to express their needs and emotions
- Each cat has its own unique quirks and idiosyncrasies that make them endearing companions
</text>
<speaker_notes>Cats are complex and multifaceted creatures, with a wide range of personalities and behaviors that make them truly captivating. Let's dive into some of the key traits that make cats such fascinating pets.</speaker_notes>
<slideFormat>Slide with bullet points</slideFormat>
</slide>
<slide>
<slide_number>3</slide_number>
<title>The Feline Senses</title>
<subtitle>Exploring the extraordinary abilities of cats</subtitle>
<text>Cats possess a remarkable set of sensory capabilities that allow them to thrive in their environments:
Sight: Cats have exceptional night vision and can see a wider range of colors than humans.
Hearing: Feline ears can detect a wider range of frequencies, enabling them to hear sounds that humans cannot.
Smell: A cat's sense of smell is up to 14 times more sensitive than a human's, allowing them to gather valuable information about their surroundings.
These heightened senses contribute to the cat's impressive hunting prowess and overall adaptability.</text>
<speaker_notes>Cats have evolved with an impressive array of sensory abilities that allow them to navigate their world with incredible precision and awareness. Let's explore some of the key ways in which their senses set them apart.</speaker_notes>
<slideFormat>Slide with text</slideFormat>
</slide>
<slide>
<slide_number>4</slide_number>
<title>The Feline Agility</title>
<subtitle>Marveling at the athletic prowess of cats</subtitle>
<image>https://example.com/cat-jumping.jpg</image>
<speaker_notes>Cats are renowned for their incredible agility and athleticism. From effortlessly leaping to great heights to executing precise landings, their physical capabilities are truly awe-inspiring.</speaker_notes>
<slideFormat>Slide with image only</slideFormat>
</slide>
<slide>
<slide_number>5</slide_number>
<title>Important Takeaways</title>
<subtitle>Key messages to remember</subtitle>
<text>
- Cats exhibit a wide range of unique personalities and traits
- Feline senses are extraordinarily keen, enabling them to thrive in their environments
- Cats possess remarkable agility and athleticism, allowing them to perform amazing feats
- The special bond between cats and humans is a cherished and rewarding relationship
</text>
<speaker_notes>As we conclude our exploration of the wonderful world of cats, remember these key takeaways about these fascinating feline friends. Their captivating personalities, heightened senses, and incredible physical abilities make them truly remarkable creatures.</speaker_notes>
<slideFormat>Slide with 4 takeaways</slideFormat>
</slides>
"""
    ppt(xml)

# test_ppt()