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

# 1. Correct project answer
r = a.process_user_text(sid, "I built a random forest model and compared it with XGBoost for classification.")
print("\nPROJECT ANSWER")
print("Q:", r.get("ai_response_text"))
print("TURN:", r.get("turn_count"))
print("EVAL:", r.get("evaluation_summary"))

# 2. Wrong-domain answer to Python question
r = a.process_user_text(sid, "I used recall and F1 score because accuracy can be misleading.")
print("\nWRONG ANSWER TO PYTHON QUESTION")
print("Q:", r.get("ai_response_text"))
print("TURN:", r.get("turn_count"))
print("EVAL:", r.get("evaluation_summary"))
print("DECISION:", r.get("decision_type"))

# 3. Correct Python answer
r = a.process_user_text(sid, "I would use separate folders and modules for data loading, preprocessing, training, evaluation, configuration, logging, and tests.")
print("\nCORRECT PYTHON ANSWER")
print("Q:", r.get("ai_response_text"))
print("TURN:", r.get("turn_count"))
print("EVAL:", r.get("evaluation_summary"))

# 4. Wrong-domain answer to ML question
r = a.process_user_text(sid, "I would expose the model through a FastAPI endpoint with JSON request and response.")
print("\nWRONG ANSWER TO ML QUESTION")
print("Q:", r.get("ai_response_text"))
print("TURN:", r.get("turn_count"))
print("EVAL:", r.get("evaluation_summary"))
print("DECISION:", r.get("decision_type"))

# 5. Correct ML answer
r = a.process_user_text(sid, "I detect overfitting by comparing training and validation performance. If validation is worse, I reduce complexity, use regularization, cross validation, or more data.")
print("\nCORRECT ML ANSWER")
print("Q:", r.get("ai_response_text"))
print("TURN:", r.get("turn_count"))
print("EVAL:", r.get("evaluation_summary"))
