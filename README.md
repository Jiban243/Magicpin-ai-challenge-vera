Vera Pro - magicpin AI Assistant
This repository contains my submission for the magicpin AI Challenge, rebuilding "Vera" to be a smarter, highly contextual, and engaging WhatsApp AI assistant for merchants.

🧠 Approach & Architecture:- 
My goal was to build a robust, stateful bot capable of synthesizing multi-layered contexts and handling edge cases gracefully. The architecture relies on three core pillars:-


1) Stateful Foundation (FastAPI):-
I implemented a FastApi server to handle the strict 5-endpoint API contract (/v1/healthz, /v1/metadata, /v1/context, /v1/tick, /v1/reply). Contexts (Category, Merchant, Trigger, Customer) are ingested and stored in an in-memory dictionary contexts[(scope, context_id)] for rapid retrieval.


2) Composition Engine:-
I selected the Groq API as the reasoning engine due to its lightning-fast inference speeds and generous free tier. The bot leverages llama-3.1-8b-instant for rapid generation and llama-3.3-70b-versatile for complex evaluation logic. The /v1/tick endpoint uses a strict system prompt to synthesize the 4 context layers and output validated JSON. To prevent markdown parsing crashes, I implemented a JSON cleaner that strips out markdown backticks.

3) Rate-Limit Resilience (Smart Retry):-
To handle batch processing without hitting HTTP 429: Too Many Requests errors, the bot includes an Exponential Backoff engine. If a rate limit is detected, it waits and automatically retries. It also includes a "Savior Fallback" default message to ensure it never returns a zero score during timeouts.


4) Multi-Turn State Machine:- The /v1/reply endpoint is explicitly programmed to handle complex conversational routing, successfully navigating the "Boss Level" edge cases: gracefully ending on auto-reply loops, transitioning to action mode upon explicit intent, and exiting on hostile messages.

⚖️ Tradeoffs Made
In-Memory Storage vs. Persistent Database:-
I opted for in-memory dictionaries rather than a persistent database (like Redis or PostgreSQL). While this maximizes speed for the challenge's strict timeout limits, it would need to be swapped for a persistent layer in a real production environment to prevent data loss on server restarts.


Latency vs. Model Size:-
I chose Gemini 2.5 Flash over larger frontier models to guarantee responses within the judge's timeout limits, prioritizing conversational speed over extreme reasoning depth.

🔮 What Additional Context Would Have Helped Most

More Real-World Logs:-
While the anonymized Patterns A-D were incredibly helpful, having a larger dataset of actual failed intent-handoffs or generic-copy misses would have allowed for even more refined few-shot prompting.

Action Execution Limits: More detailed documentation on exactly how Vera currently executes the "action mode" (e.g., the specific API calls it makes to update a Google Business Profile or draft a campaign) would have allowed the bot to simulate the final transaction more realistically.

🚀 Setup & Installation
To run this bot locally for evaluation:

1. Create & Activate Virtual Environment
Bash
python3 -m venv venv
source venv/bin/activate

2. Install Dependencies
Bash
pip install fastapi uvicorn google-generativeai pydantic

4. Set API Key
Bash
export GEMINI_API_KEY="your_api_key_here"

6. Start the Server
Bash
uvicorn bot:app --host 0.0.0.0 --port 8080

5. Expose for Grading (Optional)
If testing via external webhook, use ngrok to expose the local server:
Bash
ngrok http 8080
