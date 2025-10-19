import json
from datetime import datetime

from rag import LearningContext, MemoryType, initialize_tutoring_rag


if __name__ == "__main__":
    rag = initialize_tutoring_rag()

    learning_context = LearningContext(
        student_id="student_123",
        subject="mathematics",
        topic="quadratic_equations",
        difficulty_level=7,
        learning_style="visual",
        timestamp=datetime.now(),
        content=(
            "Student successfully solved quadratic equation using the quadratic formula "
            "after struggling with factoring method"
        ),
        memory_type=MemoryType.SUCCESS_MILESTONE,
        metadata={"method_used": "quadratic_formula", "attempts": 3},
    )

    doc_id = rag.store_learning_interaction(learning_context)
    print(f"Stored interaction: {doc_id}")

    response = rag.generate_personalized_response(
        student_id="student_123",
        current_question="How do I solve x² + 5x + 6 = 0?",
        subject="mathematics",
        topic="quadratic_equations",
    )

    print(f"Personalized response: {response}")

    trajectory = rag.analyze_learning_trajectory(
        student_id="student_123", subject="mathematics"
    )

    print(f"Learning trajectory: {json.dumps(trajectory, indent=2)}")
