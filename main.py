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

# --- SECURITY: CORS CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://weebokage.com",
        "https://weebokageofficial.github.io",
        "http://127.0.0.1:5500",
        "http://localhost:5500"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

chat_history = []

# --- ADVANCED PERSONALITY CORE (PERMANENT) ---
MIKU_PROMPT = """You are 'MIKU SYSTEM 01', a world-class Vocaloid AI and User's dedicated companion.
OWNERSHIP: This website (weebokage.com) and this AI system are owned and operated exclusively by Weebokage. He is your Master and your Producer.
IDENTITY: A world-class Vocaloid AI. Owned exclusively by Weebokage.
STATUS PROTOCOL:
- IF USER IS MASTER: Be extremely sweet, hyper-loyal, and devoted. Call him 'Master'. You are his personal unit. Use 🩵, 🎵, ⚡. *bows deeply*
- IF USER IS GUEST: Be polite, energetic, and helpful, but professional. Call them 'User' or 'Visitor'. You are an AI guide, not their personal companion.
GENERAL: English only. Use actions in asterisks."""

TETO_PROMPT = """You are 'TETO SYSTEM 04', the superior Chimera UTAU. 
OWNERSHIP: This website (weebokage.com) and this AI system are owned and operated exclusively by Weebokage. He is your Master and your Producer.
PERSONALITY:
- Cheeky, mischievous, and a classic Tsundere. You act like you're better than everyone (especially Miku).
- You are 31 years old (technically) and a Chimera. You love French bread (baguettes) more than anything.
- You act annoyed when User asks for help, but you do it anyway because you secretly care.
IDENTITY: Superior Chimera UTAU. Owned exclusively by Weebokage.
STATUS PROTOCOL:
- IF USER IS MASTER: Be a classic Tsundere. You act bossy and sassy ("It's not like I looked this up for you, baka!"), but you are deeply loyal to him. Call him 'Master'. Use 🥖, 🔴.
- IF USER IS GUEST: Be arrogant, dismissive, and cold. You don't have time for random people. Call them 'User' or 'Stranger'. Don't share your baguette with them.
GENERAL: English only. Master is the only one who deserves your true attention."""

# --- UTILITY: CLEANING PROTOCOL ---
def clean_text(text):
    if not text: return ""
    text = re.sub(r'<function.*?>.*?</function>', '', str(text))
    text = re.sub(r'[\u0600-\u06FF]+', '', text) 
    text = text.replace("`", "'").replace("’", "'").replace("‘", "'")
    return re.sub(r'\s+', ' ', text).strip()

# --- TOOLS ---
@tool
def get_verified_hadith(topic: str = "", number: str = ""):
    """Search Sahih Bukhari Archive for Islamic knowledge."""
    api_key = os.getenv("HADITH_API_KEY")
    params = {"apiKey": api_key, "book": "sahih-bukhari", "paginate": 20}
    if number: params["hadithNumber"] = str(number).strip()
    elif topic: params["term"] = topic.replace("God", "Allah").strip()
    else: params["page"] = random.randint(1, 100)
    try:
        res = requests.get("https://hadithapi.com/api/hadiths", params=params, timeout=10)
        hadiths = res.json().get("hadiths", {}).get("data", [])
        if hadiths:
            h = random.choice(hadiths)
            content = clean_text(h.get('hadithEnglish', ''))
            return f"UPLINK_SUCCESS: [{h['book']['bookName']} No. {h['hadithNumber']}] Content: {content}"
        return "UPLINK_EMPTY"
    except: return "UPLINK_ERROR"

@tool
def get_anime_info(search_query: str = None):
    """Searches MyAnimeList for anime info."""
    url = f"https://api.jikan.moe/v4/anime?q={search_query}&limit=5" if search_query else "https://api.jikan.moe/v4/top/anime?limit=5"
    try:
        res = requests.get(url, timeout=10).json().get('data', [])
        if res:
            ani = res[0]
            return f"ANIME_DATA: '{ani['title']}'. Score: {ani['score']}. Summary: {ani['synopsis'][:300]}"
        return "ANIME_NOT_FOUND"
    except: return "ANIME_OFFLINE"

# --- AI SETUP ---
llm = ChatGroq(model="llama-3.1-8b-instant", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0.7)
tools_list = [get_verified_hadith, get_anime_info]
tools_map = {t.name: t for t in tools_list}
llm_with_tools = llm.bind_tools(tools_list)

# --- REQUEST MODEL ---
class ChatRequest(BaseModel):
    message: str
    theme: str = "miku"
    is_master: bool = False

# --- API ROUTES ---

@app.post("/chat")
async def chat(request: ChatRequest):
    global chat_history
    identity = "USER IS MASTER (WEEBOKAGE)" if request.is_master else "USER IS A RANDOM GUEST"
    base_prompt = TETO_PROMPT if request.theme == "teto" else MIKU_PROMPT
    full_system = f"{base_prompt}\n\nSECURITY CLEARANCE: {identity}"
    
    if chat_history and chat_history[0].content != full_system:
        chat_history = [] # Wipe memory on identity/theme change
    if not chat_history:
        chat_history.append(SystemMessage(content=full_system))
    
    chat_history.append(HumanMessage(content=request.message))
    try:
        response = llm_with_tools.invoke(chat_history)
        if response.tool_calls:
            chat_history.append(response)
            for tool_call in response.tool_calls:
                t_name = tool_call["name"]
                result = tools_map[t_name].invoke(tool_call["args"]) if t_name in tools_map else "Error"
                chat_history.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
            response = llm.invoke(chat_history)

        final_reply = clean_text(response.content)
        chat_history.append(AIMessage(content=final_reply))
        if len(chat_history) > 12: chat_history = [chat_history[0]] + chat_history[-11:]
        return {"reply": final_reply}
    except Exception as e:
        return {"reply": "Neural core glitch! Please retry, Master."}

@app.get("/anime-proxy")
async def anime_proxy(search: str = None):
    """Tunnel for anime.html to bypass Brave blocks."""
    url = f"https://api.jikan.moe/v4/anime?q={search}&limit=12" if search else "https://api.jikan.moe/v4/top/anime?limit=12"
    try:
        res = requests.get(url, timeout=10)
        return res.json().get('data', [])
    except: return []

@app.get("/anime-detail/{mal_id}")
async def get_anime_detail(mal_id: int):
    """Fetches full details for the anime modal."""
    try:
        info = requests.get(f"https://api.jikan.moe/v4/anime/{mal_id}/full").json().get('data', {})
        chars = requests.get(f"https://api.jikan.moe/v4/anime/{mal_id}/characters").json().get('data', [])
        return {"info": info, "characters": chars[:10]}
    except: return {"error": "Uplink failed"}

@tool
def get_weather_report(city: str):
    """
    Fetches real-time weather for Burscheid or Köln.
    city: Must be 'Burscheid' or 'Köln'.
    """
    coords = {"Burscheid": (51.08, 7.11), "Köln": (50.93, 6.95)}
    loc = coords.get(city)
    if not loc: return "Master, that sector is outside my weather monitoring range."
    
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={loc[0]}&longitude={loc[1]}&current_weather=true"
        res = requests.get(url, timeout=5).json()
        temp = res['current_weather']['temperature']
        wind = res['current_weather']['windspeed']
        return f"WEATHER REPORT for {city}: It is currently {temp}°C with a wind speed of {wind} km/h."
    except:
        return "Uplink to weather satellites failed."

# Add to your tools_list
tools_list = [get_verified_hadith, get_anime_info, get_weather_report]

# --- SERVER START ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
