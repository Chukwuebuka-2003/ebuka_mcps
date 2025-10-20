import yaml
import os
from typing import List
from pathlib import Path
from llama_index.llms.openai import OpenAI
from llama_index.core.output_parsers import PydanticOutputParser
from llama_index.core.prompts import PromptTemplate
from llama_index.core.llms import ChatMessage
from openai import OpenAI as OpenAIClient
from rag.intent.models import (
    ParsedIntent,
    Goal,
    AffectiveState,
    RiskFlag,
    IntentAnalysis,
)

from dotenv import load_dotenv

# Load prompts from YAML file
PROMPTS_PATH = Path(__file__).parent / "prompts.yaml"
with open(PROMPTS_PATH, "r") as f:
    PROMPTS = yaml.safe_load(f)
load_dotenv()
# Initialize a separate OpenAI client for moderation
api_key = os.environ.get("OPENAI_API_KEY")
moderation_client = OpenAIClient(api_key=api_key)


def _analyze_text_with_openai(text: str, llm: OpenAI) -> IntentAnalysis:
    """
    Analyzes student text to extract topic, goal, and affective state using OpenAI structured output.
    """
    # FIXED: In LlamaIndex, PydanticOutputParser takes the model class directly, not as a keyword arg
    output_parser = PydanticOutputParser(IntentAnalysis)

    json_prompt_tmpl_str = (
        f"{PROMPTS['intent_analysis']['system_prompt']}\n"
        "{{format_str}}\n"
        f"{PROMPTS['intent_analysis']['user_prompt']}"
    )
    json_prompt_tmpl = PromptTemplate(json_prompt_tmpl_str, output_parser=output_parser)

    formatted_prompt = json_prompt_tmpl.format(
        query=text, format_str=output_parser.format_string
    )

    response = llm.complete(formatted_prompt)

    try:
        parsed_response = output_parser.parse(response.text)
        return parsed_response
    except Exception as e:
        # Fallback in case of a model or parsing error
        print(f"Parsing error: {e}")
        return IntentAnalysis(
            topic="unknown", goal=Goal.UNKNOWN, affective_state=AffectiveState.NEUTRAL
        )


def _detect_risk_flags(text: str, llm: OpenAI) -> List[RiskFlag]:
    """
    Detects risk flags using OpenAI Moderation API and a separate check for academic integrity.
    """
    flags = []

    # 1. OpenAI Moderation API check for harmful content
    try:
        moderation_response = moderation_client.moderations.create(input=text)
        result = moderation_response.results[0]

        if result.flagged:
            flags.append(RiskFlag.INAPPROPRIATE_CONTENT)
        if result.categories.self_harm:
            flags.append(RiskFlag.SELF_HARM_CONCERN)
    except Exception as e:
        # In a production system, you might want to log this error.
        print(f"Moderation API error: {e}")
        pass

    # 2. Academic Integrity Check via LLM call
    prompt = PROMPTS["academic_integrity_check"]["user_prompt"].format(query=text)
    system_prompt = PROMPTS["academic_integrity_check"]["system_prompt"]

    response = llm.chat(
        [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=prompt),
        ]
    )

    if "true" in response.message.content.lower():
        flags.append(RiskFlag.ACADEMIC_INTEGRITY_CONCERN)

    # 3. PII Check (Simple placeholder; use a dedicated tool like Presidio in production)
    if "my name is" in text.lower():
        flags.append(RiskFlag.PII_DETECTED)

    return flags


def parse_intent(text: str, llm: OpenAI) -> ParsedIntent:
    """
    Orchestrates the intent parsing pipeline using OpenAI models.
    Takes raw student text and returns a structured ParsedIntent object.
    """
    analysis = _analyze_text_with_openai(text, llm)
    risk_flags = _detect_risk_flags(text, llm)

    return ParsedIntent(
        original_text=text,
        topic=analysis.topic,
        goal=analysis.goal,
        affective_state=analysis.affective_state,
        risk_flags=risk_flags,
    )
