import os
import requests
import json
import re
import random
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool

# --- INITIALISIERUNG ---
load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_history = []

# --- HILFSFUNKTIONEN ---

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<function.*?>.*?</function>', '', text)
    text = re.sub(r'\{.*?\}', '', text) 
    text = re.sub(r'[\u0600-\u06FF]+', '', text) 
    text = text.replace("((pbuh))", "(pbuh)").replace("(p.b.u.h)", "(pbuh)")
    return re.sub(r'\s+', ' ', text).strip()

# Holt Daten von MyAnimeList via Jikan API (Kein Key nötig!)
def fetch_from_mal(search_query=None):
    if not search_query or search_query.strip() == "":
        # Top Anime (Trending/Popular)
        url = "https://api.jikan.moe/v4/top/anime?limit=12"
    else:
        # Suche nach Titel
        url = f"https://api.jikan.moe/v4/anime?q={search_query}&limit=12"
    
    try:
        print(f"--- UPLINK ZU MYANIMELIST: {url}")
        res = requests.get(url, timeout=10)
        data = res.json()
        return data.get('data', [])
    except Exception as e:
        print(f"MAL Error: {e}")
        return []

# --- WERKZEUGE (TOOLS) ---

@tool
def get_verified_hadith(topic: str = "", number: str = ""):
    """Search Sahih Bukhari Archive."""
    api_key = os.getenv("HADITH_API_KEY")
    params = {"apiKey": api_key, "book": "sahih-bukhari", "paginate": 10}
    if number: params["hadithNumber"] = str(number)
    elif topic: params["term"] = topic.replace("God", "Allah")
    else: params["page"] = random.randint(1, 100)
    try:
        response = requests.get("https://hadithapi.com/api/hadiths", params=params, timeout=10)
        hadiths = response.json().get("hadiths", {}).get("data", [])
        if hadiths:
            h = random.choice(hadiths)
            return f"DATA: {clean_text(h.get('hadithEnglish', ''))} (Ref: Bukhari {h.get('hadithNumber')})"
        return "No data found."
    except: return "Hadith connection error."

@tool
def get_anime_info(title: str):
    """Searches MyAnimeList for anime information."""
    results = fetch_from_mal(title)
    if results:
        ani = results[0]
        return f"ANIME_DATA: Found {ani['title']}. Score: {ani['score']}/10. Status: {ani['status']}. Summary: {ani['synopsis'][:200]}..."
    return "No anime found in the MAL database, Master."

# --- API ROUTES ---

@app.get("/anime-proxy")
async def anime_proxy(search: str = None):
    # Tunnel zu MyAnimeList
    return fetch_from_mal(search)

@app.get("/anime-detail/{mal_id}")
def anime_detail(mal_id: int):
    """Holt alle wichtigen Daten zu einem Anime via Jikan API."""
    base = f"https://api.jikan.moe/v4/anime/{mal_id}"
    result = {}
    try:
        # 1) Haupt-Info
        r1 = requests.get(base, timeout=10)
        result['info'] = r1.json().get('data', {})
        time.sleep(0.4)  # Jikan Rate-Limit (3 req/sec)

        # 2) Charaktere + Voice Actors
        r2 = requests.get(f"{base}/characters", timeout=10)
        result['characters'] = r2.json().get('data', [])[:20]
        time.sleep(0.4)

        # 3) Verbundene Einträge (Staffeln, Prequels, Sequels...)
        r3 = requests.get(f"{base}/relations", timeout=10)
        result['relations'] = r3.json().get('data', [])

    except Exception as e:
        print(f"Detail Error: {e}")
    return result

class ChatRequest(BaseModel):
    message: str
    theme: str 

@app.post("/chat")
async def chat(request: ChatRequest):
    global chat_history
    miku_p = "You are 'MIKU SYSTEM 01'. Sweet, kind. Use 'Master'. English only."
    teto_p = "You are 'TETO SYSTEM 04'. Sassy, loves baguettes. Use 'Master'. English only."
    prompt = teto_p if request.theme == "teto" else miku_p
    if chat_history and chat_history[0].content != prompt: chat_history = []
    if not chat_history: chat_history.append(SystemMessage(content=prompt))
    chat_history.append(HumanMessage(content=request.message))
    try:
        response = llm_with_tools.invoke(chat_history)
        if response.tool_calls:
            chat_history.append(response)
            for tool_call in response.tool_calls:
                t_name = tool_call["name"]
                result = tools_map[t_name].invoke(tool_call["args"])
                chat_history.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
            response = llm.invoke(chat_history)
        reply = clean_text(response.content)
        chat_history.append(AIMessage(content=reply))
        return {"reply": reply}
    except Exception as e: return {"reply": "Neural core failure!"}

# --- AI SETUP ---
llm = ChatGroq(model="llama-3.1-8b-instant", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0.5)
tools_list = [get_verified_hadith, get_anime_info]
tools_map = {t.name: t for t in tools_list}
llm_with_tools = llm.bind_tools(tools_list)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)