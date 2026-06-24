import sys
sys.path.insert(0, "backend")

from pipecat_integration.interview_processor import InterviewProcessor

p = InterviewProcessor(adapter=None, session_id="test")

tests = [
    "I'm Thymore, and one project I worked on was I'm Thymore, and one project I worked on was comparing random forest and XGBoost on a classification problem.",
    "I'd break it into modules. For data loading, one for preprocessing, another for model training, and separate ones for evaluation another for model training, and separate ones for evaluation, configuration, and logging.",
    "For scaling, I applied standard scaling to numerical features For scaling, I applied standard scaling to numerical features when the model required it.",
    "I usually pick the median if the data has outliers because it's more robust. If the distribution looks fairly normal it's more robust. If the distribution looks fairly normal, then mean works fine.",
    "I detect overfitting by comparing training and validation scores. If training is high and validation is low, I use regularization and cross validation."
]

for i, s in enumerate(tests, 1):
    print(f"\\nTEST {i}")
    print("ORIGINAL:", s)
    print("CLEANED :", p._clean_transcript_for_evaluation(s))
