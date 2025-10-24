from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json

from dotenv import load_dotenv
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import (
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

from rag.identity.checker import ConsentLevel, Student, check_identity_and_consent_sync
from rag.intent.parser import RiskFlag, parse_intent
from rag.types import LearningContext, MemoryType
import time
from rag.utils import sanitize_pinecone_metadata
import logging

load_dotenv()

pinecone_api_key = os.getenv("PINECONE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
pinecone_environment = os.getenv("PINECONE_ENVIRONMENT")


class TutoringRAGSystem:
    def __init__(
        self,
        index_name: str = "llamarag",
        embedding_model: str = "text-embedding-3-small",
        llm_model: str = "gpt-4o-mini",
        index_dimension: Optional[int] = None,
    ) -> None:
        self.pc = Pinecone(api_key=pinecone_api_key)

        def _infer_embedding_dimension(model_name: str) -> int:
            name = (model_name or "").lower()
            if "text-embedding-3-large" in name:
                return 3072
            return 1536

        expected_dimension = index_dimension or _infer_embedding_dimension(
            embedding_model
        )

        existing_indexes = [index.name for index in self.pc.list_indexes()]

        if index_name in existing_indexes:
            try:
                desc = self.pc.describe_index(index_name)
                current_dim = getattr(desc, "dimension", None)
                if current_dim is None and isinstance(desc, dict):
                    current_dim = desc.get("dimension")
            except Exception:
                current_dim = None

            if current_dim is not None and current_dim != expected_dimension:
                self.pc.delete_index(index_name)
                self.pc.create_index(
                    name=index_name,
                    dimension=expected_dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws", region=pinecone_environment or "us-east-1"
                    ),
                )
        else:
            self.pc.create_index(
                name=index_name,
                dimension=expected_dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws", region=pinecone_environment or "us-east-1"
                ),
            )

        self.pinecone_index = self.pc.Index(index_name)

        self.embedding_model = OpenAIEmbedding(model=embedding_model)
        self.llm = OpenAI(model=llm_model, temperature=0.1)

        Settings.embed_model = self.embedding_model
        Settings.llm = self.llm

        self.vector_store = PineconeVectorStore(pinecone_index=self.pinecone_index)
        self.vector_index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store
        )

    def store_learning_interaction(self, context: LearningContext) -> str:
        metadata: Dict[str, Any] = {
            "student_id": context.student_id,
            "subject": context.subject,
            "topic": context.topic,
            "difficulty_level": context.difficulty_level,
            "learning_style": context.learning_style,
            "memory_type": context.memory_type.value,
            "timestamp": context.timestamp.isoformat(),
            "document_title": context.document_title,
            **(context.metadata or {}),
        }
        # sanitize the metadata
        sanitized_metadata = sanitize_pinecone_metadata(metadata=metadata)

        document = Document(
            text=context.content,
            metadata=sanitized_metadata,
            doc_id=f"{context.student_id}_{context.memory_type.value}_{context.timestamp.timestamp()}",
        )
        print(f"Attempting to insert document: {document.doc_id}")
        start = time.time()

        try:
            self.vector_index.insert(document)
            print(f"Insert completed in {time.time() - start:.2f} seconds")
        except Exception as e:
            print(f"Insert failed: {e}")
            raise

        return document.doc_id

    def _get_student_current_difficulty(
        self, student_id: str, topic: str, subject: str, default_level: int = 3
    ) -> int:
        """
        Retrieves the student's most recent difficulty level for a specific topic.
        """
        filters: List[MetadataFilter] = [
            MetadataFilter(
                key="student_id", value=student_id, operator=FilterOperator.EQ
            ),
            MetadataFilter(key="topic", value=topic, operator=FilterOperator.EQ),
            MetadataFilter(key="subject", value=subject, operator=FilterOperator.EQ),
        ]

        # Retrieve a small number of recent, relevant documents to find the latest
        retriever = VectorIndexRetriever(
            index=self.vector_index,
            similarity_top_k=10,
            filters=MetadataFilters(filters=filters),
        )

        nodes = retriever.retrieve(f"interactions about {topic}")

        if not nodes:
            return default_level

        # Sort nodes by timestamp to find the most recent one
        nodes.sort(key=lambda n: n.metadata.get("timestamp", ""), reverse=True)

        return nodes[0].metadata.get("difficulty_level", default_level)

    def retrieve_student_context(
        self,
        student: Student,
        current_topic: str,
        subject: Optional[str] = None,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
        recency_alpha: float = 0.5,  # Balances similarity and recency
    ) -> tuple[list[NodeWithScore], int]:
        # The method now returns a tuple: (list_of_nodes, difficulty_level)
        if student.consent_level == ConsentLevel.MINIMAL_PSEUDONYMOUS:
            return [], self._get_student_current_difficulty(
                student.student_id, current_topic, subject
            )

        # Get student's current difficulty level for the topic
        current_difficulty = self._get_student_current_difficulty(
            student_id=student.student_id, topic=current_topic, subject=subject
        )

        # Define difficulty range for filtering
        difficulty_range = list(
            range(max(1, current_difficulty - 1), min(10, current_difficulty + 1) + 1)
        )

        # Build metadata filters including dynamic difficulty
        filters: List[MetadataFilter] = [
            MetadataFilter(
                key="student_id", value=student.student_id, operator=FilterOperator.EQ
            ),
            MetadataFilter(
                key="difficulty_level",
                value=difficulty_range,
                operator=FilterOperator.IN,
            ),
        ]

        if subject:
            filters.append(
                MetadataFilter(key="subject", value=subject, operator=FilterOperator.EQ)
            )

        if memory_types:
            memory_type_values = [mt.value for mt in memory_types]
            filters.append(
                MetadataFilter(
                    key="memory_type",
                    value=memory_type_values,
                    operator=FilterOperator.IN,
                )
            )

        # Retrieve a larger pool of documents for re-ranking
        retrieval_limit = limit * 2
        retriever = VectorIndexRetriever(
            index=self.vector_index,
            similarity_top_k=retrieval_limit,
            filters=MetadataFilters(filters=filters),
        )

        initial_nodes = retriever.retrieve(current_topic)

        # Calculate recency-weighted scores
        re_ranked_nodes: List[NodeWithScore] = []
        for node in initial_nodes:
            timestamp_str = node.metadata.get("timestamp")
            if not timestamp_str:
                continue

            interaction_time = datetime.fromisoformat(timestamp_str).astimezone(
                timezone.utc
            )
            days_since = (datetime.now(timezone.utc) - interaction_time).days

            decay_rate = 0.1
            recency_score = math.exp(-decay_rate * days_since)

            combined_score = (recency_alpha * node.get_score()) + (
                (1 - recency_alpha) * recency_score
            )
            node.score = combined_score
            re_ranked_nodes.append(node)

        # Re-sort nodes based on the new combined score
        re_ranked_nodes.sort(key=lambda n: n.get_score(), reverse=True)

        # Apply threshold and return the top results
        final_nodes = [
            node for node in re_ranked_nodes if node.score >= similarity_threshold
        ]
        return final_nodes[:limit], current_difficulty

    def find_similar_learning_patterns(
        self,
        student_id: str,
        current_challenge: str,
        exclude_student: bool = True,
        limit: int = 5,
    ) -> List[NodeWithScore]:
        filters: List[MetadataFilter] = []

        if exclude_student:
            filters.append(
                MetadataFilter(
                    key="student_id", value=student_id, operator=FilterOperator.NE
                )
            )

        filters.append(
            MetadataFilter(
                key="memory_type",
                value=[
                    MemoryType.SUCCESS_MILESTONE.value,
                    MemoryType.ERROR_PATTERN.value,
                ],
                operator=FilterOperator.IN,
            )
        )

        retriever = VectorIndexRetriever(
            index=self.vector_index,
            similarity_top_k=limit,
            filters=MetadataFilters(filters=filters),
        )

        return retriever.retrieve(current_challenge)

    def get_personalized_content_recommendations(
        self,
        student_id: str,
        topic: str,
        difficulty_level: int,
        learning_style: str,
        limit: int = 5,
    ) -> List[NodeWithScore]:
        query = (
            f"learning content for {topic} suitable for {learning_style} learner "
            f"at difficulty level {difficulty_level}"
        )

        filters: List[MetadataFilter] = [
            MetadataFilter(
                key="memory_type",
                value=MemoryType.CONTENT_MASTERY.value,
                operator=FilterOperator.EQ,
            ),
            MetadataFilter(
                key="difficulty_level",
                value=[difficulty_level - 1, difficulty_level, difficulty_level + 1],
                operator=FilterOperator.IN,
            ),
        ]

        learning_style_filter = MetadataFilter(
            key="learning_style", value=learning_style, operator=FilterOperator.EQ
        )
        filters.append(learning_style_filter)

        retriever = VectorIndexRetriever(
            index=self.vector_index,
            similarity_top_k=limit,
            filters=MetadataFilters(filters=filters),
        )

        return retriever.retrieve(query)

    def analyze_learning_trajectory(
        self, student_id: str, subject: str, days_back: int = 30
    ) -> Dict[str, Any]:
        filters: List[MetadataFilter] = [
            MetadataFilter(
                key="student_id", value=student_id, operator=FilterOperator.EQ
            ),
            MetadataFilter(key="subject", value=subject, operator=FilterOperator.EQ),
        ]

        retriever = VectorIndexRetriever(
            index=self.vector_index,
            similarity_top_k=50,
            filters=MetadataFilters(filters=filters),
        )

        nodes = retriever.retrieve(f"learning progress and achievements in {subject}")

        skill_assessments: List[NodeWithScore] = []
        error_patterns: List[NodeWithScore] = []
        success_milestones: List[NodeWithScore] = []

        for node in nodes:
            memory_type = node.metadata.get("memory_type")
            if memory_type == MemoryType.SKILL_ASSESSMENT.value:
                skill_assessments.append(node)
            elif memory_type == MemoryType.ERROR_PATTERN.value:
                error_patterns.append(node)
            elif memory_type == MemoryType.SUCCESS_MILESTONE.value:
                success_milestones.append(node)

        return {
            "total_interactions": len(nodes),
            "skill_assessments": len(skill_assessments),
            "error_patterns": len(error_patterns),
            "success_milestones": len(success_milestones),
            "recent_topics": list(
                set([node.metadata.get("topic", "unknown") for node in nodes])
            ),
            "difficulty_progression": [
                node.metadata.get("difficulty_level", 0) for node in nodes
            ],
        }

    def update_student_skill_assessment(
        self,
        student_id: str,
        subject: str,
        skill_area: str,
        competency_level: float,
        assessment_details: str,
    ) -> str:
        context = LearningContext(
            student_id=student_id,
            subject=subject,
            topic=skill_area,
            difficulty_level=int(competency_level * 10),
            learning_style="assessment",
            timestamp=datetime.now(),
            content=(
                f"Skill assessment for {skill_area}: {assessment_details}. "
                f"Competency level: {competency_level}"
            ),
            memory_type=MemoryType.SKILL_ASSESSMENT,
            metadata={"competency_level": competency_level, "skill_area": skill_area},
            document_title="Skill Assessment Report",
        )

        return self.store_learning_interaction(context)

    def generate_personalized_response(
        self,
        student_id: str,
        current_question: str,
        subject: str,
        topic: str,
        context_limit: int = 5,
    ) -> str:
        logger = logging.getLogger(__name__)

        logger.info("=" * 80)
        logger.info(f"🔍 RAG RETRIEVAL STARTING")
        logger.info(f"  Student ID: {student_id}")
        logger.info(f"  Question: {current_question}")
        logger.info(f"  Subject: {subject}, Topic: {topic}")
        logger.info("=" * 80)

        # Identity + Consent Check (using sync version since we don't have async context here)
        student = check_identity_and_consent_sync(student_id)
        logger.info(f"✅ Student consent level: {student.consent_level}")

        # Intent Parsing
        intent = parse_intent(current_question, self.llm)
        logger.info(f"📊 Intent parsed - Goal: {intent.goal}, Topic: {intent.topic}")

        # Policy/Ethics Gate (Pre-Retrieval)
        if intent.risk_flags:
            logger.warning(f"⚠️  Risk flags detected: {intent.risk_flags}")
            if RiskFlag.ACADEMIC_INTEGRITY_CONCERN in intent.risk_flags:
                return "I can help you understand the concepts, but I cannot provide direct answers to assignments or tests. Let's work through a similar example problem."
            if RiskFlag.PII_DETECTED in intent.risk_flags:
                return "It looks like you may have shared some personal information. To protect your privacy, please rephrase your question without including any personal details."
            return "I am unable to process this request. Please try rephrasing your question or ask something else."

        parsed_topic = intent.topic

        # Retrieval Orchestration
        assessed_difficulty = 5
        citations = []

        if student.consent_level == ConsentLevel.MINIMAL_PSEUDONYMOUS:
            logger.warning("⚠️  Minimal consent - no personalized retrieval")
            context_text = (
                "No personal learning history available due to consent level."
            )
            assessed_difficulty = self._get_student_current_difficulty(
                student.student_id, parsed_topic, subject
            )
        else:
            logger.info(f"🔎 Retrieving context for student...")
            student_context, assessed_difficulty = self.retrieve_student_context(
                student=student,
                current_topic=parsed_topic,
                subject=subject,
                limit=context_limit,
            )

            logger.info(f"📚 Retrieved {len(student_context)} context nodes")

            # Extract document titles for citations
            document_titles = set()
            context_parts = []

            for i, node in enumerate(student_context):
                doc_title = node.metadata.get("document_title") or node.metadata.get(
                    "filename", "Unknown Source"
                )
                document_titles.add(doc_title)

                logger.info(
                    f"  📄 Node {i + 1}: {doc_title[:50]}... (score: {node.score:.3f})"
                )
                logger.info(f"     Content preview: {node.text[:100]}...")

                context_parts.append(f"[Source: {doc_title}]\n{node.text}")

            context_text = "\n\n".join(context_parts)
            citations = list(document_titles)

            logger.info(f"📖 Available citations: {citations}")
            logger.info(f"📝 Context text length: {len(context_text)} characters")

        if not citations:
            logger.warning(
                "⚠️  NO CITATIONS AVAILABLE - Documents not found or missing metadata"
            )
        else:
            logger.info(f"✅ {len(citations)} citation sources available")

        # Enhanced prompt with citation instructions
        prompt = f"""
    You are an AI tutor helping a student with {subject}.

    **Student's Learning Context:**
    {context_text if context_text else "No uploaded documents found for this topic."}

    **Student's Question:** "{current_question}"

    **CRITICAL CITATION INSTRUCTIONS:**
    {
            f'''
    YOU MUST CITE THESE SOURCES when using their information:
    Available sources: {", ".join([f"[{title}]" for title in citations])}

    CITATION RULES (MANDATORY):
    1. When you reference ANY information from the context above, immediately add the citation: [Document Title]
    2. Place citations RIGHT AFTER the relevant sentence or fact
    3. Example: "The power rule states d/dx[x^n] = n*x^(n-1) [Calculus Chapter 3]."
    4. If you use information from uploaded documents, you MUST cite them
    5. DO NOT provide answers from general knowledge if uploaded documents contain the answer
    '''
            if citations
            else '''
    NO UPLOADED DOCUMENTS FOUND for this topic.
    You may provide a brief answer from general knowledge, but tell the student:
    "I don't have any uploaded study materials about this topic yet. Would you like to upload course materials or notes so I can provide more personalized help?"
    '''
        }

    Based on the context, provide a response that:
    1. Acknowledges their emotional state and goal
    2. {
            "USES the uploaded material WITH CITATIONS in [Document Title] format"
            if citations
            else "Suggests uploading materials for personalized help"
        }
    3. Addresses any previous misconceptions
    4. Provides guidance at an appropriate difficulty level

    Response:
    """

        logger.info("🤖 Sending prompt to LLM...")
        logger.info(f"Prompt length: {len(prompt)} characters")

        response = self.llm.complete(prompt)

        logger.info("✅ LLM response received")
        logger.info(f"Response preview: {response.text[:200]}...")

        # Check if citations are in response
        has_citations = any(f"[{title}]" in response.text for title in citations)
        if citations and not has_citations:
            logger.error(
                "❌ CITATIONS MISSING FROM RESPONSE despite available sources!"
            )
        elif has_citations:
            logger.info("✅ Response includes citations")

        # Write-back (Memory Augmentation)
        self.store_learning_interaction(
            LearningContext(
                student_id=student_id,
                subject=subject,
                topic=parsed_topic,
                difficulty_level=assessed_difficulty,
                learning_style="mixed",
                timestamp=datetime.now(),
                content=f"Q: {current_question}\nA: {response.text}",
                memory_type=MemoryType.LEARNING_INTERACTION,
                metadata={
                    "goal": intent.goal.value,
                    "affective_state": intent.affective_state.value,
                },
                document_title=f"Chat Interaction on {parsed_topic}",  # Added this line
            )
        )

        logger.info("=" * 80)
        return response.text
