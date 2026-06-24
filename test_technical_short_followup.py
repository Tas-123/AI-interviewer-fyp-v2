import sys
sys.path.insert(0, "backend")

from integration.dialogue_adapter import InterviewDialogueAdapter

a = InterviewDialogueAdapter()
s = a.start_interview({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning", "Data Preprocessing", "Model Evaluation", "NLP", "APIs", "Deployment"],
    "experience": "Junior AI Engineer"
})

sid = s["session_id"]
print("START:", s["ai_response_text"])

def show(label, ans):
    r = a.process_user_text(sid, ans)
    print("\n" + label)
    print("INPUT:", ans)
    print("Q:", r.get("ai_response_text"))
    print("TURN:", r.get("turn_count"))
    print("EVAL:", r.get("evaluation_summary"))
    return r

# Move from project to Python question
show("PROJECT", "I worked on a classification project using Random Forest and XGBoost on a labeled dataset.")

# Now answer current technical/Python question too short
show("SHORT TECHNICAL ANSWER", "Modules.")

