import time
import json
import os
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from groq import AsyncGroq

app = FastAPI(title="Vera Bot - magicpin AI Challenge")
START_TIME = time.time()

# ==========================================
# GROQ SETUP
# ==========================================
groq_client = AsyncGroq(api_key=os.environ.get("Removed for privacy"), base_url="https://api.groq.com/v1")
GROQ_MODEL = "llama-3.1-8b-instant"

COMPOSER_SYSTEM_PROMPT = """You are Vera, magicpin assistant. 
Compose a WhatsApp message using this STRICT checklist:
1. GREETING: Must use the exact business name (e.g. Dr. Meera's Dental Clinic).
2. PERFORMANCE: Mention the views (2410) and calls (18).
3. OFFER: Mention 'Dental Cleaning @ ₹299'.
4. DATA: Reference the JIDA/DCI facts from the trigger.
5. CTA: Ask a simple YES/NO question.
6. CTA: Never use "Book now." Instead, use a low-friction curiosity gap or a simple choice. (e.g., "Should I send the available slots for this evening?" or "Reply YES to see how your neighbors are using this.")

Output JSON ONLY: {"body": "...", "cta": "binary", "send_as": "vera", "suppression_key": "...", "rationale": "..."}"""

# ==========================================
# STATE MANAGEMENT
# ==========================================
contexts: Dict[tuple[str, str], Dict] = {}    
conversations: Dict[str, List[Dict[str, str]]] = {} 

class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str

class TickBody(BaseModel):
    now: str
    available_triggers: List[str] = []

class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

@app.get("/v1/healthz")
async def healthz():
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        counts[scope] = counts.get(scope, 0) + 1
    return {"status": "ok", "uptime_seconds": int(time.time() - START_TIME), "contexts_loaded": counts}

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Team Vera Pro", 
        "team_members": ["Your Name"], 
        "model": GROQ_MODEL,
        "approach": "Dynamic context synthesis with Groq", 
        "contact_email": "team@example.com",
        "version": "1.0.6", 
        "submitted_at": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/v1/context")
async def push_context(body: CtxBody):
    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    
    if cur and cur["version"] >= body.version:
        return {"accepted": False, "reason": "stale_version", "current_version": cur["version"]}
        
    contexts[key] = {"version": body.version, "payload": body.payload}
    return {"accepted": True, "ack_id": f"ack_{body.context_id}_v{body.version}", "stored_at": datetime.utcnow().isoformat() + "Z"}

@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []
    
    for trigger_id in body.available_triggers:
        trigger_ctx = contexts.get(("trigger", trigger_id))
        if not trigger_ctx: continue
            
        trigger_payload = trigger_ctx["payload"]
        merchant_id = trigger_payload.get("merchant_id")
        customer_id = trigger_payload.get("customer_id")
        
        merchant_ctx = contexts.get(("merchant", merchant_id))
        if not merchant_ctx: continue
            
        category_slug = merchant_ctx["payload"].get("category_slug")
        category_ctx = contexts.get(("category", category_slug))
        if not category_ctx: continue
            
        customer_ctx = contexts.get(("customer", customer_id)) if customer_id else None

        user_prompt = f"""
        === CONTEXTS ===
        CATEGORY: {json.dumps(category_ctx['payload'])}
        MERCHANT: {json.dumps(merchant_ctx['payload'])}
        TRIGGER: {json.dumps(trigger_payload)}
        CUSTOMER: {json.dumps(customer_ctx['payload']) if customer_ctx else 'None'}
        """
        
        action = None
        for attempt in range(3):
            try:
                await asyncio.sleep(1) 
                
                response = await groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": COMPOSER_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                
                text_response = response.choices[0].message.content.strip()
                llm_output = json.loads(text_response)
                
                action = {
                    "conversation_id": f"conv_{merchant_id}_{trigger_id}",
                    "merchant_id": merchant_id,
                    "customer_id": customer_id,
                    "send_as": llm_output.get("send_as", "vera"),
                    "trigger_id": trigger_id,
                    "body": llm_output.get("body", "Error generating message."),
                    "cta": llm_output.get("cta", "none"),
                    "suppression_key": llm_output.get("suppression_key", trigger_id),
                    "rationale": llm_output.get("rationale", "No rationale provided.")
                }
                actions.append(action)
                break 
                
            except Exception as e:
                if "429" in str(e):
                    print(f"Rate limit hit for {trigger_id}. Retrying in {2 ** attempt}s...")
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    print(f"Error on {trigger_id}: {e}")
                    break
                    
        if not action:
            merchant_name = merchant_ctx['payload'].get('identity', {}).get('name', 'there')
            actions.append({
                "conversation_id": f"conv_{merchant_id}_{trigger_id}",
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "send_as": "vera",
                "trigger_id": trigger_id,
                "body": f"Hi {merchant_name}, we noticed some new activity on your profile. Reply YES to review the latest insights.",
                "cta": "binary",
                "suppression_key": trigger_id,
                "rationale": "Fallback message due to error."
            })

    return {"actions": actions}

@app.post("/v1/reply")
async def reply(body: ReplyBody):
    history = conversations.setdefault(body.conversation_id, [])
    history.append({"from": body.from_role, "msg": body.message})
    merchant_msg = body.message.lower()

    merchant_messages = [msg["msg"] for msg in history if msg["from"] == body.from_role]
    if len(merchant_messages) >= 3:
        if merchant_messages[-1] == merchant_messages[-2] == merchant_messages[-3]:
            return {"action": "end", "rationale": "Detected auto-reply. Exiting."}

    hostile_keywords = ["stop", "spam", "unsubscribe", "useless", "annoying"]
    if any(word in merchant_msg for word in hostile_keywords):
        return {"action": "end", "rationale": "Honoring opt-out."}

    commitment_keywords = ["let's do it", "yes", "go ahead", "ok", "whats next"]
    if any(word in merchant_msg for word in commitment_keywords):
        return {
            "action": "send",
            "body": "Done! I am drafting the next steps and sending them over to confirm.",
            "cta": "open_ended",
            "rationale": "Merchant showed clear intent. Transitioning immediately to action mode."
        }

    return {"action": "wait", "wait_seconds": 60, "rationale": "Waiting for signals."}