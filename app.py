from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage
from typing import Annotated, Sequence, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from PIL import Image, ImageDraw, ImageFont
import textwrap
from supabase import create_client
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.messages import SystemMessage
from dotenv import load_dotenv
import os
import requests
from langchain_groq import ChatGroq
import random
load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage],add_messages]


@tool 
def make_post_image(news_summary: str, font_path: str = "Lexend.ttf", font_size: int = 30, text_color: str = "black", padding: int = 60, line_spacing: float = 1.5, max_text_width: int = 1020, post_size: tuple = (1080, 1350)):
    """
    Helps in creating an image to post on instagram by passing the text in the post
    Args:
        news_summary: summary of latest news obtained
        
    Returns:
        Path to created image
    """
    bg_colors=["#F04A00", "#F6DE16", "#5E5CB2", "#94D2BD", "#E9D8A6","#BDB76B","#8FBC8B","#FFF8DC","#FFFFFF","#FFFAFA","#F0FFF0","#F5FFFA","#F0FFFF","#F0F8FF","#F8F8FF","#F5F5F5","#FFF0F5","#FFE4E1","#E1AFD1","#A7D7C5","#ADA2FF","#8E9775","#FFE1FF"]
    image_bg = random.choice(bg_colors)
    img = Image.new("RGB", post_size, color=image_bg)
    draw = ImageDraw.Draw(img)
    points = news_summary.split('\n')
    
    try:
        fonts = ['Lexend.ttf','Federo.ttf','IBMPlexMono.ttf','Montserrat.ttf','RobotoSlab.ttf','SourceSans3.ttf']
        font_path = random.choice(fonts)
        font = ImageFont.truetype(font_path, font_size)
    except OSError:
        print(f"Font {font_path} not found, using default font")
        font = ImageFont.load_default()

    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    avg_char_width = sum(dummy_draw.textlength(c, font=font) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ") / 26
    max_chars_per_line = max_text_width // avg_char_width
    lines = []
    
    for i in points:
        lines.extend(textwrap.wrap(i,width=int(max_chars_per_line)))
        lines.extend([''])

    base_line_height = font.getbbox("A")[3] - font.getbbox("A")[1]
    line_height = int(base_line_height * line_spacing)

    y = padding
    lines.insert(0,"Headlines: ")
    lines.insert(1,"")
    
    lines.append("")
    lines.append('-thenewsguybot')
    y += line_height
    for line in lines:
        draw.text((padding, y), line, font=font, fill=text_color)
        y += line_height
    image_path = os.path.abspath("insta_text_post.png")
    img.save(image_path)
    print(f"Image saved at: {image_path}")
    
    return image_path


@tool
def upload_image_to_supabase(image_path: str):
    """ Uploads image to supabase bucket instagram-posts as image.png 
        Args:
            image_path: Image path in local directory
        returns:
            public_url: url of uploaded image
    
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
    
    supabase = create_client(url, key)

    bucket_name = "instagram-posts"
    
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found at path: {image_path}")

    with open(image_path, "rb") as f:
        file_data = f.read()

    try:
        result = supabase.storage.from_(bucket_name).upload('image.png', file_data, {'upsert': 'true'})
        print(f"Upload result: {result}")
    except Exception as e:
        print(f"Upload error: {e}")
        raise e
    
    public_url = supabase.storage.from_(bucket_name).get_public_url('image.png')
    
    try:
        os.remove(image_path)
        print(f"Local file removed: {image_path}")
    except OSError as e:
        print(f"Warning: Could not remove local file {image_path}: {e}")
    
    return public_url.strip('?')

@tool
def fetch_news():
    """ Extracts latest Indian news from moneycontrol website and returns string of news content extracted"""
    try:
        news_source = os.get_env("NEWS_SOURCE")
        loader = WebBaseLoader(news_source) 
        docs = loader.load()
        return docs[0].page_content
    except Exception as e:
        print(f"Error fetching news: {e}")
        raise e

def create_container_for_post(image_url: str):
    instagram_id = os.getenv("INSTAGRAM_ID")
    instagram_access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    
    if not instagram_id or not instagram_access_token:
        raise ValueError("INSTAGRAM_ID and INSTAGRAM_ACCESS_TOKEN must be set in environment variables")
    
    url = f"https://graph.instagram.com/v23.0/{instagram_id}/media?image_url={image_url}&is_carousel_item=FALSE&caption=Headlines %23news %23indiannews&access_token={instagram_access_token}"
    res = requests.post(url)
    data = res.json()
    
    if 'id' not in data:
        raise KeyError(f"Instagram API error: {data}")
    
    return data['id']
    

@tool
def create_instagram_post(supabase_image_url: str):
    """ Creates an instagram post
        Args:
            supabase_image_url: public URL of image in supabase
        returns:
            id: id of uploaded post
    """
    try:
        creation_id = create_container_for_post(supabase_image_url)
        instagram_id = os.getenv("INSTAGRAM_ID")
        instagram_access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        
        url = f"https://graph.instagram.com/v23.0/{instagram_id}/media_publish?creation_id={creation_id}&access_token={instagram_access_token}"
        res = requests.post(url)
        data = res.json()
        
        if 'id' not in data:
            raise KeyError(f"Instagram publish API error: {data}")
        
        return data['id']
    except Exception as e:
        print(f"Error creating Instagram post: {e}")
        raise e
    
    
tools = [fetch_news, make_post_image, upload_image_to_supabase, create_instagram_post]
os.environ['GROQ_API_KEY'] = os.getenv("GROQ_API_KEY") #type:ignore
llm = ChatGroq(model='meta-llama/llama-4-maverick-17b-128e-instruct').bind_tools(tools=tools)


def journalist_agent(state: AgentState) -> AgentState:
    system_prompt = SystemMessage(content="""
    You are a journalist who posts news on instagram. You must call tools one at a time in the correct sequence:
    1. First call fetch_news() to get the latest news
    2. Then analyze the news and create a 8 point plain text summary 
    3. Call make_post_image() with the actual summary text
    4. Call upload_image_to_supabase() with the actual image path returned from make_post_image
    5. Finally call create_instagram_post() with the actual Supabase URL returned from upload_image_to_supabase
    
    Never call multiple tools at once. Wait for each tool's response before proceeding to the next step.
    Always use the actual return values from previous tools, not placeholder text.
    
    If you have already fetched news, proceed to create a summary and call make_post_image.
    If you have created an image, proceed to upload it to supabase.
    If you have uploaded to supabase, proceed to create the instagram post.
    Continue until all steps are complete.
    """)
    
    response = llm.invoke([system_prompt] + state['messages']) #type:ignore
    
    print(f"LLM Response: {response.content}")
    if hasattr(response, 'tool_calls') and response.tool_calls: #type:ignore
        print(f"Tool calls: {[call['name'] for call in response.tool_calls]}") #type:ignore
    
    return {"messages": [response]}
    

def should_go_to_tools(state: AgentState):
    messages = state['messages']
    
    if not messages:
        return 'stop'
    
    last_message = messages[-1]
    
    if hasattr(last_message, 'tool_calls') and len(last_message.tool_calls) > 0: #type:ignore
        return 'continue'
    return 'stop'


graph = StateGraph(AgentState)

graph.add_node('llm', journalist_agent)
graph.add_node('tools', ToolNode(tools=tools))

graph.add_edge(START, 'llm')
graph.add_edge('tools', 'llm') 


graph.add_conditional_edges(
    'llm',
    should_go_to_tools,
    {
        'continue': 'tools',
        'stop': END
    }
)

agent = graph.compile()

def run_agent():
    """Helper function to run the agent with better error handling"""
    try:
        response = agent.invoke({
            "messages": [HumanMessage(content="""Summarize the most latest news from internet into 8 point wise plain text summary. 
                                            Create an image with the summary generated. 
                                            Upload that image to supabase.
                                            Use the supabase public url to upload the image to instagram.
                                            Use all the relevant tools available with you. Follow the steps one by one.""")]
        })
        return response
    except Exception as e:
        print(f"Error running agent: {e}")
        return None

if __name__ == "__main__":
    response = run_agent() 
    if response:
        print("\nFinal Response:")
        print(response)
    else:
        print("Agent execution failed.")
