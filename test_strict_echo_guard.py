import sys
sys.path.insert(0, "backend")

from dialogue.dialogue_manager import DialogueManager

dm = DialogueManager({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning"],
    "experience": "Junior"
})

intro_q = "Good morning, welcome to the interview for the AI Engineer position. Can you start by introducing yourself and telling me about a recent AI or machine learning project you've worked on?"

real_answer = "I detect overfitting by comparing the gap between training and validation performance. If validation loss worsens while training loss keeps dropping, that is a red flag. To reduce it, I would simplify the model, use regularization, dropout, and early stopping."

overfit_q = "Suppose your training score is high but validation performance drops. How would you detect overfitting, and what would you do to reduce it?"

print("INTRO ECHO SHOULD BE TRUE:", dm._looks_like_bot_question_echo(intro_q, intro_q))
print("REAL ANSWER SHOULD BE FALSE:", dm._looks_like_bot_question_echo(real_answer, overfit_q))
