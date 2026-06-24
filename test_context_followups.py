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
print("\nSTART:")
print(s["ai_response_text"])

answers = [
    "I built a credit card fraud detection model using Python and machine learning. I used transaction data, trained a classifier, evaluated it with precision and recall, and added explainability for flagged transactions.",

    "The precision was around 92 percent and recall was around 86 percent. I focused more on recall because missing fraudulent transactions was more risky than false alerts.",

    "I would separate the project into modules for data loading, preprocessing, training, evaluation, and configuration. I would also use logging and tests so bugs are easier to trace.",

    "For logging, I would log input file paths, preprocessing steps, model parameters, metrics, and errors. For testing, I would test preprocessing functions and API validation.",

    "I detect overfitting by comparing training and validation performance. If training is high but validation is low, I use regularization, cross validation, simpler models, or more data.",

    "Early stopping monitors validation loss during training. If validation loss stops improving for a few epochs, training stops and the best model weights are restored.",

    "I handle missing values with imputation or removal, encode categorical features, and scale numerical features when the model needs it."
]

for ans in answers:
    r = a.process_user_text(sid, ans)
    print("\nTURN:", r.get("turn_count"))
    print("QUESTION:", r.get("ai_response_text"))
    print("EVAL:", r.get("evaluation_summary"))

end = a.end_interview(sid)
report = end.get("final_report", {})

print("\nTRACE:")
for t in report.get("adaptive_questioning_trace", []):
    print(
        t.get("turn"),
        "| decision=", t.get("decision_type"),
        "| domain=", t.get("domain"),
        "| next=", t.get("next_domain"),
        "| reason=", t.get("engine_reason"),
        "| q=", (t.get("next_question") or "")[:120]
    )
