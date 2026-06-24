# test_decision.py — Updated for v2.0
"""
Simulates a full interview flow through the DecisionEngine
using the updated InterviewContext with behavioral categories.
"""

from dialogue.decision_engine import DecisionEngine
from dialogue.context import InterviewContext

# ======= Resume Data =======
resume_data = {
    "experience": "3 years",
    "skills": ["Python", "Django"],
}

context = InterviewContext(resume_data)
engine = DecisionEngine()

# ======= Simulated Answers =======
sample_answers = [
    "",                                                          # INTRO → triggers greeting
    "I have used Python for building automation scripts and web apps for 3 years now across multiple projects",  # strong → python coverage +1
    "Python is great for data processing and I've used pandas and numpy extensively in my projects",            # strong → python coverage +1 (done)
    "Django is a web framework I use for REST APIs and admin panels with authentication",                       # strong → django coverage +1
    "I built a full e-commerce platform using Django with custom middleware and caching layers",                 # strong → django coverage +1 (done) → behavioral
    "I resolved a team conflict by facilitating a meeting where everyone shared their perspective",             # behavioral turn 1
    "I led a migration project from monolith to microservices with a team of 5 engineers",                     # behavioral turn 2
    "I failed at estimating a project timeline and learned to break tasks into smaller chunks",                 # behavioral turn 3
    "I decided to leave a comfortable job for a startup because I wanted more ownership",                      # behavioral turn 4
    "We collaborated across 3 teams to deliver a platform launch on time despite scope changes",               # behavioral turn 5 → wrapup
]

# ======= Run Simulation =======
print("=" * 60)
print("AI INTERVIEW SIMULATION — Decision Engine Test")
print("=" * 60)

for i, ans in enumerate(sample_answers):
    print(f"\n{'─' * 50}")
    print(f"Turn {i + 1}")
    print(f"State: {context.state.value}")
    print(f"Candidate says: \"{ans[:60]}{'...' if len(ans) > 60 else ''}\"")

    decision = engine.decide(context, ans)
    print(f"Decision: {decision}")

    # Simulate add_turn (normally done by DialogueManager)
    context.add_turn(f"[Question for turn {i+1}]", ans)

# ======= Final State =======
print(f"\n{'=' * 60}")
print("FINAL STATE")
print(f"{'=' * 60}")
print(f"State:                    {context.state.value}")
print(f"Turn Count:               {context.turn_count}")
print(f"Topic Coverage:           {context.topic_coverage}")
print(f"Behavioral Used:          {context.behavioral_categories_used}")
print(f"Behavioral Remaining:     {context.behavioral_categories_available}")