#!/usr/bin/env python3
"""
Test script for AI-powered subject detection
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def test_subject_detection(text: str, context: str = "chat") -> str:
    """Test the AI subject detection"""
    try:
        prompt = f"""Analyze the following {context} content and identify the primary academic subject.

Content: {text[:1500]}

Return ONLY the subject name from this list:
- Mathematics
- Physics
- Chemistry
- Biology
- Computer Science
- English
- History
- Geography
- Economics
- Psychology
- Philosophy
- Art
- Music
- Engineering
- Business
- General

If the content clearly fits multiple subjects, choose the most dominant one.
If unclear, return "General".

Subject:"""

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at identifying academic subjects from content. Always respond with a single subject name."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=20
        )

        detected_subject = response.choices[0].message.content.strip()
        return detected_subject

    except Exception as e:
        print(f"Error: {e}")
        return "General"


if __name__ == "__main__":
    # Test cases
    test_cases = [
        {
            "text": "What is the derivative of x^2? Can you explain how to use the power rule?",
            "expected": "Mathematics"
        },
        {
            "text": "Explain Newton's laws of motion and how force relates to acceleration.",
            "expected": "Physics"
        },
        {
            "text": "How do I implement a binary search tree in Python? What's the time complexity?",
            "expected": "Computer Science"
        },
        {
            "text": "What caused World War II? Explain the Treaty of Versailles.",
            "expected": "History"
        },
        {
            "text": "What is photosynthesis? How do plants convert sunlight into energy?",
            "expected": "Biology"
        },
        {
            "text": "Hello, how are you today?",
            "expected": "General"
        }
    ]

    print("=" * 60)
    print("Testing AI Subject Detection")
    print("=" * 60)

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        print(f"Text: {test['text'][:80]}...")
        detected = test_subject_detection(test['text'])
        expected = test['expected']
        status = "✅ PASS" if detected == expected else "❌ FAIL"
        print(f"Expected: {expected}")
        print(f"Detected: {detected}")
        print(f"Status: {status}")

    print("\n" + "=" * 60)
