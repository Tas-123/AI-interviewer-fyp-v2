import sys
sys.path.insert(0, "backend")

from integration.dialogue_adapter import InterviewDialogueAdapter

a = InterviewDialogueAdapter()

s = a.start_interview({
    "name": "Candidate",
    "role": "Junior AI Engineer",
    "skills": ["Python", "Machine Learning"],
    "experience": "Junior AI Engineer"
})

sid = s["session_id"]

print("\nSTART:")
print(s["ai_response_text"])

print("\nREPEAT TEST:")
r1 = a.process_user_text(sid, "Can you repeat the question?")
print(r1)

print("\nECHO TEST:")
r2 = a.process_user_text(
    sid,
    "I'm not here for pleasantries. Just give me one AI or ML project that you worked on."
)
print(r2)

print("\nNORMAL ANSWER TEST:")
r3 = a.process_user_text(
    sid,
    "I built a fraud detection model using Python and machine learning. I evaluated it using precision and recall."
)
print(r3)
