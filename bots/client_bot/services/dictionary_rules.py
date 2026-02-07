import json
import os
from typing import Any


RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "dictionary_rules.json")


def load_dictionary_rules() -> dict[str, Any]:
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"categories": {}, "questions": {}}


def analyze_text_with_rules(text: str, rules: dict[str, Any]) -> dict[str, Any]:
    normalized = text.lower()
    categories = rules.get("categories", {}) if isinstance(rules.get("categories"), dict) else {}
    questions = rules.get("questions", {}) if isinstance(rules.get("questions"), dict) else {}
    matched_category = "other"
    matched_keywords: list[str] = []
    for category, keywords in categories.items():
        if not isinstance(keywords, list):
            continue
        hits = [keyword for keyword in keywords if keyword and keyword in normalized]
        if hits:
            matched_category = category
            matched_keywords = hits
            break
    candidate_questions = questions.get(matched_category, []) if isinstance(questions.get(matched_category), list) else []
    selected_questions = [q for q in candidate_questions if isinstance(q, str) and q.strip()][:3]
    return {
        "category": matched_category,
        "keywords": matched_keywords,
        "questions": selected_questions,
    }
