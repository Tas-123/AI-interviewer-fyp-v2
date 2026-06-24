import sys
sys.path.insert(0, "backend")

from dialogue.dialogue_manager import DialogueManager

def test_preprocessing_relevance():
    print("=" * 60)
    print("PREPROCESSING DOMAIN RELEVANCE REGRESSION TEST")
    print("=" * 60)
    
    # Initialize dialogue manager with mock candidate data
    dm = DialogueManager({
        "name": "Candidate",
        "role": "Junior AI Engineer",
        "skills": ["Python", "Machine Learning"],
        "experience": "Junior"
    })
    
    # 1. Simulate the start of the interview (greeting)
    dm.handle_turn("")
    
    # 2. Simulate a preprocessing question
    # This simulates a dynamic follow-up or specific question.
    question = "Can you walk me through your preprocessing steps?"
    dm.context.question_history.append(question)
    
    # 3. Simulate correct preprocessing answer (with STT variant standard scale)
    answer = "I imputed missing values with median, one-hot encoded categorical features, and applied standard scaling."
    
    # Check domain relevance output directly
    is_relevant = dm._is_answer_relevant_to_question(answer, question)
    print(f"Question: \"{question}\"")
    print(f"Answer: \"{answer}\"")
    print(f"Is Relevant: {is_relevant}")
    
    assert is_relevant, "Expected preprocessing answer to be classified as relevant to preprocessing question."
    
    # Check handling through handle_turn (should not return a DOMAIN_RELEVANCE_REDIRECT)
    # Mock llm.generate and evaluator.adaptive_evaluate to avoid real LLM calls
    from unittest.mock import patch
    with patch.object(dm.evaluator, 'adaptive_evaluate', return_value={
        "evaluation": {"overall_score": 4.0, "weighted_overall_score": 4.0},
        "decision": {"type": "ADVANCE", "next_question": "Next topic?"}
    }), patch.object(dm.llm, 'generate', return_value="Next question"):
        res = dm.handle_turn(answer)
        print("Response next question:", res.get("question"))
        print("Decision Type:", res.get("decision_type"))
        
        # Verify it wasn't redirected
        assert res.get("decision_type") != "DOMAIN_RELEVANCE_REDIRECT", "Answer was incorrectly redirected due to domain relevance."
        print("[PASS] test_preprocessing_relevance")

if __name__ == "__main__":
    try:
        test_preprocessing_relevance()
        sys.exit(0)
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
