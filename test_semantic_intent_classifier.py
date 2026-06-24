import sys
sys.path.insert(0, "backend")

from integration.dialogue_adapter import InterviewDialogueAdapter

a = InterviewDialogueAdapter()

s = a.start_interview({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning", "Data Preprocessing"],
    "experience": "Junior AI Engineer"
})

sid = s["session_id"]
print("START:", s["ai_response_text"])

tests = [
    "Sorry I couldn't understand.",
    "I missed the first part.",
    "Could you frame it differently?",
    "Are you asking about the dataset or the model?",
    "Your voice cut out for a second.",
    "Before you start, keep it specific. I don't want buzzwords.",
    "Skip the general stuff. Tell me exactly what steps you would take.",
    "I built a random forest model and compared it with XGBoost for classification."
]

for t in tests:
    r = a.process_user_text(sid, t)
    print("\nINPUT:", t)
    print("RESPONSE:", r.get("ai_response_text"))
    print("TURN:", r.get("turn_count"))
    print("EVAL:", r.get("evaluation_summary"))
