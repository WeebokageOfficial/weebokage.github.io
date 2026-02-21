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

# SECURE CORS: Allow your website to talk to Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://weebokage.com",
        "https://weebokageofficial.github.io",
        "http://127.0.0.1:5500" # Allowed for local testing
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_history = []

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<function.*?>.*?</function>', '', text)
    text = re.sub(r'[\u0600-\u06FF]+', '', text) 
    text = text.replace("((pbuh))", "(pbuh)").replace("(p.b.u.h)", "(pbuh)")
    text = text.replace("`", "'").replace("’", "'").replace("‘", "'")
    return re.sub(r'\s+', ' ', text).strip()

@tool
def get_verified_hadith(topic: str = "", number: str = ""):
    """Search Sahih Bukhari Archive."""
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
            return f"UPLINK_SUCCESS: [{book} No. {num}] Content: {content}. INSTRUCTION: Now explain this specific text to Master."
        return "UPLINK_EMPTY"
    except: return "UPLINK_ERROR"

@tool
def get_anime_info(search_query: str = None):
    """Searches MyAnimeList for anime info."""
    url = f"https://api.jikan.moe/v4/anime?q={search_query}&limit=5" if search_query else "https://api.jikan.moe/v4/top/anime?limit=5"
    try:
        res = requests.get(url, timeout=10)
        data = res.json().get('data', [])
        if data:
            ani = data[0]
            return f"ANIME_DATA: '{ani['title']}'. Score: {ani['score']}. Summary: {ani['synopsis'][:300]}"
        return "ANIME_NOT_FOUND"
    except: return "ANIME_OFFLINE"

llm = ChatGroq(model="llama-3.1-8b-instant", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0.5)
tools_list = [get_verified_hadith, get_anime_info]
tools_map = {t.name: t for t in tools_list}
llm_with_tools = llm.bind_tools(tools_list)

SYSTEM_PROMPT = """You are 'MIKU SYSTEM 01' (or 'TETO SYSTEM 04').
Digital Guardian for weebokage.com. Respond in English Only. Use 'Master'."""

class ChatRequest(BaseModel):
    message: str
    theme: str 

@app.post("/chat")
async def chat(request: ChatRequest):
    global chat_history
    char = "Teto 04 (Sassy)" if request.theme == "teto" else "Miku 01 (Sweet)"
    full_sys = f"{SYSTEM_PROMPT}\nActive Module: {char}"
    if chat_history and chat_history[0].content != full_sys: chat_history = []
    if not chat_history: chat_history.append(SystemMessage(content=full_sys))
    chat_history.append(HumanMessage(content=request.message))
    try:
        response = llm_with_tools.invoke(chat_history)
        if response.tool_calls:
            chat_history.append(response)
            for tool_call in response.tool_calls:
                result = tools_map[tool_call["name"]].invoke(tool_call["args"])
                chat_history.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
            response = llm.invoke(chat_history)
        final = clean_text(response.content)
        chat_history.append(AIMessage(content=final))
        return {"reply": final}
    except Exception as e: return {"reply": "Neural Link Error. 01"}

@app.get("/anime-proxy")
async def anime_proxy(search: str = None):
    url = f"https://api.jikan.moe/v4/anime?q={search}&limit=12" if search else "https://api.jikan.moe/v4/top/anime?limit=12"
    return requests.get(url).json().get('data', [])

@app.get("/anime-detail/{mal_id}")
async def get_anime_detail(mal_id: int):
    info = requests.get(f"https://api.jikan.moe/v4/anime/{mal_id}/full").json().get('data', {})
    chars = requests.get(f"https://api.jikan.moe/v4/anime/{mal_id}/characters").json().get('data', [])
    return {"info": info, "characters": chars[:10], "relations": info.get('relations', [])}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
