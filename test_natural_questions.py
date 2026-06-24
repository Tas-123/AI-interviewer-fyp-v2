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
    print("Q:", r.get("ai_response_text"))
    print("TURN:", r.get("turn_count"))
    print("EVAL:", r.get("evaluation_summary"))
    return r

show("PROJECT", "I worked on a classification project using Random Forest and XGBoost on a labeled dataset.")
show("PYTHON", "I would use separate modules for data loading, preprocessing, training, evaluation, configuration, logging, and tests.")
show("OVERFITTING", "I detect overfitting by comparing training and validation scores, then use regularization, cross-validation, early stopping, simpler models, or more data.")
