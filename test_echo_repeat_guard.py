import sys
sys.path.insert(0, "backend")

from integration.dialogue_adapter import InterviewDialogueAdapter

a = InterviewDialogueAdapter()
s = a.start_interview({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning"],
    "experience": "Junior"
})

sid = s["session_id"]
intro = s["ai_response_text"]
print("START:", intro)

# Simulate bot/ChatGPT prompt echo
r = a.process_user_text(sid, intro)
print("\nECHO TEST")
print("Q:", r.get("ai_response_text"))
print("EVAL:", r.get("evaluation_summary"))
print("DECISION:", r.get("decision_type"))

# Simulate user saying they didn't understand
r = a.process_user_text(sid, "I did not understand your question, please repeat.")
print("\nREPEAT TEST")
print("Q:", r.get("ai_response_text"))
print("EVAL:", r.get("evaluation_summary"))
print("DECISION:", r.get("decision_type"))
