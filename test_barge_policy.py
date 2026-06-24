import sys
sys.path.insert(0, "backend")

from integration.dialogue_adapter import InterviewDialogueAdapter

a = InterviewDialogueAdapter()

s = a.start_interview({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning"],
    "experience": "Junior AI Engineer"
})

sid = s["session_id"]

print("\nSTART:")
print(s["ai_response_text"])

tests = [
    "Can you repeat the question?",
    "If you skip preprocessing, you're setting yourself up for garbage output.",
    "I'm here to challenge you, so let's get serious.",
    "I built a fraud detection model using Python and machine learning. I evaluated it using precision and recall."
]

for t in tests:
    r = a.process_user_text(sid, t)
    print("\nINPUT:", t)
    print("RESPONSE:", r.get("ai_response_text"))
    print("TURN:", r.get("turn_count"))
    print("EVAL:", r.get("evaluation_summary"))
