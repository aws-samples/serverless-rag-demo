import base64

# Prompt template for Claude 3 to extract text from a given image
claude3_textract_prompt="""Your purpose is to extract the text from the given image (traditional OCR). 
If the text is in another language, you should first translate it to english and then extract it.
Remember not to summarize or analyze the image. You should return the extracted text.
Wrap the response as a json with key text and value the extracted text.
Do not include any other words or characters in the output other than the json.
"""

claude3_title_prompt="""Your purpose is to suggest a suitable title for the provided text.
The text is provided within the <text></text> tags.
You should suggest a title that is short, concise, and descriptive.
Remember not to summarize or analyze the text. You should return the title.
If the text is in another language, you should first translate it to english and then generate the title.
Wrap the response as a json with key text and value the title.
{
"text": "<title>"
}
Do not include any other words or characters in the output other than the json.
"""

def generate_claude_3_ocr_prompt(image_bytes_list):
    image_content_list = []
    if len(image_bytes_list) > 0:
        for image_bytes in image_bytes_list:
            image_content_list.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("utf-8")
                }
            })
        image_content_list.append({
                "type": "text",
                "text": claude3_textract_prompt
            })
    
    ocr_prompt = [
        {
        "role": "user",
        "content": image_content_list
    }]
    prompt_template= {"anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 600000,
                        "messages": ocr_prompt
                    }
    return prompt_template 



def generate_claude_3_title_prompt(text_value):
    title_prompt = [
        {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"""{claude3_title_prompt}
                        <text>{text_value}</text>"""
            }
        ]
    }]
    prompt_template= {"anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 100000,
                        "messages": title_prompt
                    }
    return prompt_template 
