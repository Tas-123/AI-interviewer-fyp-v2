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

# Project answer
show("PROJECT ANSWER", "I worked on a classification project where I compared Random Forest and XGBoost models using a labeled dataset.")

# Project follow-up answer
show("PROJECT FOLLOWUP", "The goal was to compare model performance. XGBoost performed slightly better in recall and F1 score.")

# Python question should now come
show("WRONG PYTHON ANSWER METRICS", "I used recall and F1 score because accuracy can be misleading.")

show("CORRECT PYTHON ANSWER", "I would structure it using separate modules for data loading, preprocessing, training, evaluation, configuration, logging, and tests.")

# ML/overfitting question should now come
show("WRONG OVERFITTING ANSWER PYTHON STRUCTURE", "After structuring into modules, I keep separate scripts for training, testing, and configuration so debugging is easier.")

show("CORRECT OVERFITTING ANSWER", "I detect overfitting by comparing training and validation scores. If training is high and validation is low, I use regularization, cross-validation, early stopping, simpler models, or more data.")
