"""
ws_client_simulation.py — Example WebSocket client for the AI Interviewer.

Simulates a complete voice interview session using text-based WebSocket
messages. Run this after starting the server with:

    uvicorn main:app --reload

Usage:

    python backend/ws_client_simulation.py
"""

import asyncio
import json
import uuid

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    exit(1)


# ── Configuration ────────────────────────────────────────────────
SERVER_URL = "ws://localhost:8000/ws/interview"
RESUME_DATA = {
    "skills": ["Python", "Django", "PostgreSQL", "REST APIs"],
    "experience": "4 years",
    "role": "Backend Engineer",
}

# Simulated candidate answers (one per turn)
SIMULATED_ANSWERS = [
    "I have been working as a backend engineer for four years, "
    "primarily with Python and Django. I've built several REST APIs "
    "and worked extensively with PostgreSQL databases.",

    "In my previous role, I led a team of three developers to rebuild "
    "our payment processing pipeline. We reduced processing time by 40% "
    "and eliminated a recurring data consistency issue.",

    "When we faced a critical production outage, I took ownership of "
    "the incident response. I coordinated with the DevOps team, "
    "identified the root cause within 30 minutes, and deployed a fix. "
    "We reduced our MTTR from 4 hours to under 1 hour.",
]


async def simulate_interview():
    """Run a simulated voice interview session."""
    session_id = str(uuid.uuid4())
    url = f"{SERVER_URL}/{session_id}"

    print(f"\n{'~' * 60}")
    print(f"AI INTERVIEWER -- Voice Session Simulation")
    print(f"Session: {session_id}")
    print(f"{'~' * 60}\n")

    try:
        async with websockets.connect(url) as ws:
            # ── Step 1: Start interview ──────────────────────────
            print("[CLIENT] Sending start_interview...")
            await ws.send(json.dumps({
                "type": "start_interview",
                "resume_data": RESUME_DATA,
            }))

            # Receive all response chunks + full response
            while True:
                response = json.loads(await ws.recv())
                if response["type"] == "ai_response_chunk" and response.get("is_final"):
                    continue
                if response["type"] == "ai_response_chunk":
                    continue  # Skip streaming chunks in demo output
                if response["type"] == "ai_response":
                    print(f"\n[AI] {response['text']}")
                    print(f"     Stage: {response.get('stage', 'N/A')}")
                    break

            # ── Step 2: Simulated turns ──────────────────────────
            for i, answer in enumerate(SIMULATED_ANSWERS):
                print(f"\n{'- ' * 30}")
                print(f"[TURN {i + 1}]")

                # Send answer as speech chunks (simulating streaming)
                words = answer.split()
                chunk_size = 5
                for j in range(0, len(words), chunk_size):
                    chunk_text = " ".join(words[j:j + chunk_size])
                    await ws.send(json.dumps({
                        "type": "speech_chunk",
                        "text": chunk_text,
                    }))
                    await asyncio.sleep(0.1)  # Simulate speaking pace

                print(f"[CANDIDATE] {answer[:80]}...")

                # Signal end of speech
                await ws.send(json.dumps({"type": "speech_end"}))

                # Receive response(s)
                while True:
                    response = json.loads(await ws.recv())

                    if response["type"] == "interruption":
                        print(f"[INTERRUPT] {response['reason']}: "
                              f"{response['message']}")
                        continue

                    if response["type"] == "ai_response_chunk":
                        continue  # Skip chunks in demo

                    if response["type"] == "ai_response":
                        print(f"[AI] {response['text']}")
                        if response.get("evaluation_summary"):
                            es = response["evaluation_summary"]
                            print(f"     Score: {es.get('overall_score', 'N/A')} | "
                                  f"Hire: {es.get('hire_signal', 'N/A')}")
                        if response.get("is_complete"):
                            print("\n[SESSION] Interview complete!")
                        break

                    if response["type"] == "report":
                        print(f"[REPORT] Received final report")
                        break

                    if response["type"] == "error":
                        print(f"[ERROR] {response['message']}")
                        break

            # ── Step 3: Request report ───────────────────────────
            print(f"\n{'- ' * 30}")
            print("[CLIENT] Requesting final report...")
            await ws.send(json.dumps({"type": "get_report"}))
            response = json.loads(await ws.recv())
            if response["type"] == "report":
                report = response["data"]
                ws_summary = report.get("weighted_score_summary", {})
                print(f"[REPORT] Final hire signal: "
                      f"{ws_summary.get('final_hire_signal', 'N/A')}")
                print(f"[REPORT] Total turns: "
                      f"{report.get('interview_metadata', {}).get('total_turns', 'N/A')}")

            # ── Step 4: Close session ────────────────────────────
            await ws.send(json.dumps({"type": "close"}))
            response = json.loads(await ws.recv())
            print(f"\n[SESSION] {response.get('message', 'Closed')}")

    except ConnectionRefusedError:
        print("[ERROR] Cannot connect to server. Start with:")
        print("        uvicorn main:app --reload")
    except Exception as e:
        print(f"[ERROR] {e}")

    print(f"\n{'~' * 60}")
    print("Simulation complete.")
    print(f"{'~' * 60}")


if __name__ == "__main__":
    asyncio.run(simulate_interview())
