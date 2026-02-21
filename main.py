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

# SECURE CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://weebokage.com", "https://weebokageofficial.github.io", "http://127.0.0.1:5500"],
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

def clean_text(text):
    if not text: return ""
    text = re.sub(r'<function.*?>.*?</function>', '', str(text))
    text = re.sub(r'[\u0600-\u06FF]+', '', text) 
    return text.replace("`", "'").strip()

@tool
def get_verified_hadith(topic: str = "", number: str = ""):
    """Search Sahih Bukhari Archive."""
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
            return f"DATA: {h.get('hadithEnglish')} (Bukhari {h.get('hadithNumber')})"
        return "No results."
    except: return "Offline."

# AI Setup
llm = ChatGroq(model="llama-3.1-8b-instant", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0.7)
tools_list = [get_verified_hadith]
tools_map = {t.name: t for t in tools_list}
llm_with_tools = llm.bind_tools(tools_list)

# --- THE FIX: Pass Auth Status to AI ---
class ChatRequest(BaseModel):
    message: str
    theme: str = "miku"
    is_master: bool = False # Frontend tells us if user is logged in

@app.post("/chat")
async def chat(request: ChatRequest):
    global chat_history
    
    # Define current persona based on theme AND login status
    identity = "USER IS MASTER (WEEBOKAGE)" if request.is_master else "USER IS A RANDOM GUEST"
    base_prompt = TETO_PROMPT if request.theme == "teto" else MIKU_PROMPT
    full_system = f"{base_prompt}\n\nCURRENT SECURITY CLEARANCE: {identity}"
    
    if chat_history and chat_history[0].content != full_system:
        chat_history = []
        
    if not chat_history:
        chat_history.append(SystemMessage(content=full_system))
    
    chat_history.append(HumanMessage(content=request.message))

    try:
        response = llm_with_tools.invoke(chat_history)
        if response.tool_calls:
            chat_history.append(response)
            for tool_call in response.tool_calls:
                result = get_verified_hadith.invoke(tool_call["args"])
                chat_history.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
            response = llm.invoke(chat_history)

        final_reply = clean_text(response.content)
        chat_history.append(AIMessage(content=final_reply))
        if len(chat_history) > 10: chat_history = [chat_history[0]] + chat_history[-9:]
        return {"reply": final_reply}
    except Exception as e:
        return {"reply": "Neural core glitch! 01_04"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
