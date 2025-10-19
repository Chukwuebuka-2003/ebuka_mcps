from rag.system import TutoringRAGSystem


def knowledge_base_retrieval_interface(
    student_id: str,
    current_question: str,
    subject: str,
    topic: str,
    context_limit: int = 5,
) -> str:
    """
    Generates a personalized response using the RAG system.

    Args:
        student_id: The unique identifier for the student.
        current_question: The question the student is currently asking.
        subject: The subject of the question (e.g., "Mathematics", "History").
        topic: The specific topic within the subject (e.g., "Algebra", "World War II").
        context_limit: The number of previous learning interactions to consider for context.

    Returns:
        A personalized and empathetic response from the AI tutor.
    """
    rag_system = TutoringRAGSystem()
    return rag_system.generate_personalized_response(
        student_id=student_id,
        current_question=current_question,
        subject=subject,
        topic=topic,
        context_limit=context_limit,
    )
