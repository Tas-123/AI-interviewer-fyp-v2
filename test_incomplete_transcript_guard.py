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

def show(label, text):
    r = a.process_user_text(sid, text)
    print("\n" + label)
    print("INPUT:", text)
    print("Q:", r.get("ai_response_text"))
    print("TURN:", r.get("turn_count"))
    print("EVAL:", r.get("evaluation_summary"))
    print("DECISION:", r.get("decision_type"))
    return r

show("INCOMPLETE PROJECT FRAGMENT", "For missing")
show("INCOMPLETE MODEL FRAGMENT", "The model")
show("INCOMPLETE CONNECTOR ENDING", "I would use preprocessing and")
show("VALID SHORT PROJECT ANSWER", "I built a random forest model for classification.")
show("VALID PYTHON ANSWER", "I would structure it using separate modules, folders, logging, configuration, and tests.")
