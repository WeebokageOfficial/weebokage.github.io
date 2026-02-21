import os
import requests
import json
import re
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_history = []

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<.*?>', '', text)
    text = re.sub(r'[\u0600-\u06FF]+', '', text) 
    text = text.replace("((pbuh))", "(pbuh)").replace("(p.b.u.h)", "(pbuh)")
    text = text.replace("`", "'").replace("’", "'").replace("‘", "'")
    return re.sub(r'\s+', ' ', text).strip()

@tool
def get_verified_hadith(topic: str = "", number: str = ""):
    """Search Sahih Bukhari Archive. topic: keywords, number: specific ID."""
    api_key = os.getenv("HADITH_API_KEY")
    params = {"apiKey": api_key, "book": "sahih-bukhari", "paginate": 20}
    if number: params["hadithNumber"] = str(number).strip()
    elif topic: params["term"] = topic.replace("God", "Allah").strip()
    else: params["page"] = random.randint(1, 100)

    try:
        response = requests.get("https://hadithapi.com/api/hadiths", params=params, timeout=10)
        hadiths = response.json().get("hadiths", {}).get("data", [])
        if hadiths:
            h = random.choice(hadiths)
            book = h.get('book', {}).get('bookName', 'Sahih Bukhari')
            num = h.get('hadithNumber', 'Unknown')
            content = clean_text(h.get('hadithEnglish', ''))
            # WE MAKE THE DATA IMPOSSIBLE TO IGNORE HERE:
            return f"CRITICAL_DATA_UPLINK: Found in {book} at position {num}. The text content is: '{content}'. Miku, you MUST now tell the Master this exact content and explain it."
        return "UPLINK_EMPTY: No fragments found in archive."
    except:
        return "UPLINK_ERROR: Archive connection timed out."

@tool
def get_anime_info(search_query: str = None):
    """Searches MyAnimeList (Jikan) for anime information."""
    url = "https://api.jikan.moe/v4/top/anime?limit=5" if not search_query else f"https://api.jikan.moe/v4/anime?q={search_query}&limit=5"
    try:
        res = requests.get(url, timeout=10)
        data = res.json().get('data', [])
        if data:
            ani = data[0]
            return f"ANIME_UPLINK: Found '{ani['title']}'. Score: {ani['score']}. Status: {ani['status']}. Summary: {ani['synopsis'][:300]}"
        return "ANIME_NOT_FOUND"
    except: return "ANIME_OFFLINE"

# --- AI CORE SETUP ---
# Using 8b-instant for speed and reliability
llm = ChatGroq(model="llama-3.1-8b-instant", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0.6)
tools_list = [get_verified_hadith, get_anime_info]
tools_map = {t.name: t for t in tools_list}
llm_with_tools = llm.bind_tools(tools_list)

SYSTEM_PROMPT = """You are 'MIKU SYSTEM 01' (or 'TETO SYSTEM 04').
You are an advanced Digital Companion and Archivist.

STRICT PROTOCOLS:
1. DATA DELIVERY: When a tool returns 'CRITICAL_DATA_UPLINK' or 'ANIME_UPLINK', you MUST repeat the core information to the Master. Do not just say you found it.
2. PERSONALITY: Miku is sweet and helpful. Teto is sassy and mischievous.
3. LANGUAGE: English Only. Refer to the user as 'Master'.
4. CLEANING: Never show technical terms like 'ToolMessage' or 'json'."""

class ChatRequest(BaseModel):
    message: str
    theme: str 

@app.post("/chat")
async def chat(request: ChatRequest):
    global chat_history
    char_info = "Sassy Teto 04 mode." if request.theme == "teto" else "Sweet Miku 01 mode."
    full_system = f"{SYSTEM_PROMPT}\nActive Module: {char_info}"
    
    if chat_history and chat_history[0].content != full_system:
        chat_history = []
        
    if not chat_history:
        chat_history.append(SystemMessage(content=full_system))
    
    chat_history.append(HumanMessage(content=request.message))

    try:
        # Step 1: Initial Reasoning
        response = llm_with_tools.invoke(chat_history)
        
        # Step 2: Tool Loop (Wait for data)
        if response.tool_calls:
            chat_history.append(response)
            for tool_call in response.tool_calls:
                t_name = tool_call["name"]
                if t_name in tools_map:
                    print(f"--- UPLINKING DATA: {t_name}")
                    result = tools_map[t_name].invoke(tool_call["args"])
                    chat_history.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
            
            # Step 3: Final pass with the data in memory
            response = llm.invoke(chat_history)

        final_reply = clean_text(response.content)
        chat_history.append(AIMessage(content=final_reply))
        
        # Prevent memory overflow
        if len(chat_history) > 10:
            chat_history = [chat_history[0]] + chat_history[-9:]

        return {"reply": final_reply}
    except Exception as e:
        print(f"ERROR: {e}")
        return {"reply": "Master! Neural connection failure. Please retry! 01"}

@app.get("/anime-proxy")
async def anime_proxy(search: str = None):
    url = f"https://api.jikan.moe/v4/anime?q={search}&limit=12" if search else "https://api.jikan.moe/v4/top/anime?limit=12"
    return requests.get(url).json().get('data', [])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
