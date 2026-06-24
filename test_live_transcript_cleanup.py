import sys
sys.path.insert(0, "backend")

from dialogue.dialogue_manager import DialogueManager

dm = DialogueManager({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning"],
    "experience": "Junior"
})

tests = [
    "I worked on a classification project I worked on a classification project using Random Forest.",
    "For scaling, I applied standard scaling to numerical features For scaling, I applied standard scaling to numerical features when needed.",
    "I detect overfitting by comparing training and validation scores."
]

for t in tests:
    print("\nRAW:", t)
    print("CLEAN:", dm._clean_live_transcript(t))
