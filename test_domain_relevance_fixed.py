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

def show(label, text):
    r = a.process_user_text(sid, text)
    print("\n" + label)
    print("INPUT:", text)
    print("Q:", r.get("ai_response_text"))
    print("TURN:", r.get("turn_count"))
    print("EVAL:", r.get("evaluation_summary"))
    print("DECISION:", r.get("decision_type"))
    return r

# 1. Correct project overview answer
show(
    "PROJECT OVERVIEW ANSWER",
    "I built a random forest model and compared it with XGBoost for a classification problem. The goal was to improve prediction accuracy and compare model performance."
)

# 2. Answer the project follow-up properly
show(
    "PROJECT FOLLOW-UP ANSWER",
    "The dataset had labeled records with features and target classes. I trained both models, compared precision, recall, and accuracy, and selected the better performing model."
)

# 3. Now likely Python question. Give wrong-domain answer first.
show(
    "WRONG ANSWER TO PYTHON QUESTION",
    "I used recall and F1 score because accuracy can be misleading."
)

# 4. Now answer Python question correctly.
show(
    "CORRECT PYTHON ANSWER",
    "I would use separate folders and modules for data loading, preprocessing, training, evaluation, configuration, logging, and tests."
)

# 5. If Python context follow-up comes, answer it properly.
show(
    "PYTHON FOLLOW-UP ANSWER",
    "For testing, I would test preprocessing functions, model input validation, and API response formats. For logging, I would log errors, metrics, and pipeline steps."
)

# 6. Now likely ML question. Give wrong-domain answer first.
show(
    "WRONG ANSWER TO ML QUESTION",
    "I would expose the model through a FastAPI endpoint with JSON request and response."
)

# 7. Correct ML answer.
show(
    "CORRECT ML ANSWER",
    "I detect overfitting by comparing training and validation performance. If training is high but validation is low, I reduce complexity, use regularization, cross validation, or more data."
)
