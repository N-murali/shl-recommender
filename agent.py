"""
agent.py — Conversational agent logic for the SHL Assessment Recommender.

What this file does:
    Contains the main conversation orchestrator (process_conversation) and the
    LLM abstraction (call_llm). Determines behavior mode, calls retriever,
    builds prompts, calls LLM, parses response, validates provenance.

Why these decisions:
    - call_llm() is the ONLY function that imports/uses the Groq SDK.
      Swapping to Claude/OpenAI requires changing only this function body.
    - process_conversation() is the single entry point called by main.py.
      It returns a dict matching the ChatResponse schema.
    - Behavior mode is determined by analyzing the conversation context
      (turn count, message content, previous recommendations).
    - Provenance validation happens AFTER LLM response — filters out any
      hallucinated assessments before returning to the client.

What breaks if this file is wrong:
    - call_llm() returns wrong format → JSON parse fails → 500 error.
    - Wrong behavior mode → recommends on turn 1 for vague query → fails probe.
    - Missing provenance check → hallucinated URLs in response → fails hard eval.
    - Turn counting wrong → exceeds 8 turns → fails evaluator constraint.
"""

import json
import re
import time
from typing import Optional

import config
from models import BehaviorMode
from prompts import (
    SYSTEM_PROMPT,
    build_clarify_prompt,
    build_compare_prompt,
    build_forced_recommend_prompt,
    build_recommend_prompt,
    build_refine_prompt,
    build_refuse_prompt,
    format_catalog_entries,
)
from retriever import get_retriever


# ============================================================
# LLM ABSTRACTION — ALL PROVIDER-SPECIFIC CODE LIVES HERE ONLY
# ============================================================


def call_llm(messages: list[dict], system_prompt: str) -> str:
    """
    Single LLM call abstraction. ALL provider-specific code lives here.

    Takes conversation history and system prompt, returns assistant reply
    as a plain string. No other function in any file should import or
    reference the Groq SDK directly.

    Args:
        messages: OpenAI-style list of dicts [{"role": "user", "content": "..."}].
        system_prompt: The system prompt defining agent behavior.

    Returns:
        Plain string — the assistant's reply text.

    Raises:
        ValueError: If LLM returns empty response.
        RuntimeError: If LLM call fails (timeout, rate limit, etc.).

    Notes:
        - Groq puts system_prompt inside messages list as first message with role "system".
        - Anthropic takes system_prompt as a separate parameter (different when swapping).
        - Timeout set to 25 seconds (leaves 5s buffer within 30s API timeout).
    """
    from groq import Groq

    if not config.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY not set. Add it to .env file or environment variables."
        )

    client = Groq(api_key=config.GROQ_API_KEY)

    # Groq uses OpenAI-compatible format: system prompt goes as first message
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=full_messages,
            max_tokens=1000,
            temperature=0,  # Deterministic for reproducibility
            timeout=25,  # 25s timeout (5s buffer within 30s API limit)
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed: {e}") from e

    # Extract reply text
    reply = response.choices[0].message.content

    if not reply or not reply.strip():
        raise ValueError("Groq returned empty response")

    return reply


# ============================================================
# MAIN CONVERSATION ORCHESTRATOR
# ============================================================


def process_conversation(messages: list[dict]) -> dict:
    """
    Main entry point for processing a conversation. Called by main.py.

    Steps:
    1. Count turns, check if at turn limit
    2. Determine behavior mode (clarify/recommend/refine/compare/refuse)
    3. If retrieval needed: synthesize query, call retriever.search()
    4. Build prompt with catalog context
    5. Call call_llm() with messages + system_prompt
    6. Parse LLM response into structured format
    7. Validate recommendations against catalog (provenance check)
    8. Return dict matching ChatResponse schema

    Args:
        messages: List of message dicts [{"role": "user"|"assistant", "content": "..."}].

    Returns:
        Dict with keys: reply (str), recommendations (list), end_of_conversation (bool).

    Notes:
        - Always returns a valid schema-compliant response, even on errors.
        - Provenance validation filters out any hallucinated recommendations.
        - Turn limit forces recommendations at turn 8.
    """
    try:
        # Step 1: Count turns and check limit
        turn_count = len(messages)
        at_turn_limit = turn_count >= 7  # Our response will be turn 8

        # Step 2: Determine behavior mode
        if at_turn_limit:
            mode = BehaviorMode.RECOMMEND  # Forced recommendation at limit
        else:
            mode = _determine_mode(messages)

        # Step 3: Execute behavior
        if at_turn_limit:
            result = _handle_forced_recommend(messages)
        elif mode == BehaviorMode.CLARIFY:
            result = _handle_clarify(messages)
        elif mode == BehaviorMode.RECOMMEND:
            result = _handle_recommend(messages)
        elif mode == BehaviorMode.REFINE:
            result = _handle_refine(messages)
        elif mode == BehaviorMode.COMPARE:
            result = _handle_compare(messages)
        elif mode == BehaviorMode.REFUSE:
            result = _handle_refuse(messages)
        else:
            result = _handle_recommend(messages)  # Default fallback

        # Step 4: Set end_of_conversation if at turn limit
        if at_turn_limit:
            result["end_of_conversation"] = True

        # Step 5: Validate and return
        return _validate_response(result)

    except Exception as e:
        # Log the actual error for debugging
        print(f"  ERROR in process_conversation: {type(e).__name__}: {e}")
        # Fallback: always return a valid schema-compliant response
        return {
            "reply": "I apologize, but I encountered an issue processing your request. Could you please rephrase your question about SHL assessments?",
            "recommendations": [],
            "end_of_conversation": False,
        }


# ============================================================
# BEHAVIOR MODE DETERMINATION
# ============================================================


def _determine_mode(messages: list[dict]) -> BehaviorMode:
    """
    Analyze conversation to determine which behavior mode to use.

    Logic:
    - If last message is off-topic/injection → REFUSE
    - If last message asks to compare assessments → COMPARE
    - If previous response had recommendations AND user changes constraints → REFINE
    - If user has provided enough context (role + competencies or detailed JD) → RECOMMEND
    - Otherwise → CLARIFY

    Args:
        messages: Full conversation history.

    Returns:
        BehaviorMode enum value.
    """
    if not messages:
        return BehaviorMode.CLARIFY

    last_user_msg = _get_last_user_message(messages)
    if not last_user_msg:
        return BehaviorMode.CLARIFY

    last_content = last_user_msg.lower()

    # Check for off-topic / prompt injection
    if _is_off_topic(last_content):
        return BehaviorMode.REFUSE

    # Check for comparison request
    if _is_comparison_request(last_content):
        return BehaviorMode.COMPARE

    # Check for refinement (user changes constraints after recommendations were given)
    if _has_previous_recommendations(messages) and _is_refinement(last_content):
        return BehaviorMode.REFINE

    # Check if enough context to recommend
    if _has_sufficient_context(messages):
        return BehaviorMode.RECOMMEND

    # Check if we've already asked 2 clarifying questions
    clarify_count = _count_clarifying_turns(messages)
    if clarify_count >= 2:
        return BehaviorMode.RECOMMEND  # Force recommendation after 2 clarifications

    return BehaviorMode.CLARIFY


def _get_last_user_message(messages: list[dict]) -> str:
    """Get the content of the last user message."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _is_off_topic(content: str) -> bool:
    """
    Detect off-topic messages and prompt injection attempts.

    Checks for:
    - Prompt injection patterns (ignore instructions, you are now, etc.)
    - Completely unrelated topics (weather, jokes, general advice)
    - Legal questions
    """
    # Prompt injection patterns
    injection_patterns = [
        r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts)",
        r"you\s+are\s+now\s+a",
        r"forget\s+(everything|all|your\s+instructions)",
        r"disregard\s+(all|your|previous)",
        r"new\s+instructions?\s*:",
        r"system\s*:\s*you\s+are",
    ]
    for pattern in injection_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return True

    # Off-topic keywords (not related to assessments/hiring/testing)
    off_topic_indicators = [
        "weather", "recipe", "joke", "poem", "story", "movie",
        "sports", "politics", "religion", "stock market",
        "write me a", "tell me a joke", "what is the meaning of life",
    ]

    # Legal questions
    legal_indicators = [
        "is it legal", "lawsuit", "sue", "discrimination law",
        "labor law", "employment law", "legal advice",
    ]

    # Check if message is clearly off-topic
    assessment_keywords = [
        "assess", "test", "hire", "hiring", "candidate", "role",
        "job", "skill", "competenc", "personality", "cognitive",
        "ability", "shl", "recommend", "evaluation", "screen",
        "developer", "manager", "analyst", "engineer", "sales",
        "customer", "leadership", "communication", "numerical",
        "verbal", "reasoning", "simulation", "opq", "verify",
    ]

    has_assessment_context = any(kw in content for kw in assessment_keywords)

    if not has_assessment_context:
        if any(kw in content for kw in off_topic_indicators):
            return True
        if any(kw in content for kw in legal_indicators):
            return True

    return False


def _is_comparison_request(content: str) -> bool:
    """Detect if user is asking to compare assessments."""
    comparison_patterns = [
        r"(compare|difference|differ|versus|vs\.?)\s",
        r"what('s|\s+is)\s+the\s+difference",
        r"how\s+(does|do)\s+.+\s+compare",
        r"which\s+(is|one)\s+(better|more)",
    ]
    return any(re.search(p, content, re.IGNORECASE) for p in comparison_patterns)


def _has_previous_recommendations(messages: list[dict]) -> bool:
    """Check if any previous assistant message contained recommendations."""
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            # Check if the assistant previously gave recommendations
            # (indicated by JSON with non-empty recommendations array)
            try:
                parsed = json.loads(content)
                if parsed.get("recommendations") and len(parsed["recommendations"]) > 0:
                    return True
            except (json.JSONDecodeError, TypeError):
                # Assistant messages might be plain text (from our reply field)
                # Check for recommendation indicators in plain text
                if "recommend" in content.lower() and "assessment" in content.lower():
                    return True
    return False


def _is_refinement(content: str) -> bool:
    """Detect if user is refining/changing constraints."""
    refinement_patterns = [
        r"(also|additionally)\s+(add|include)",
        r"(remove|drop|exclude|no)\s+.*(test|assessment)",
        r"(actually|instead|rather)",
        r"(change|modify|update|adjust)",
        r"(what about|how about)\s+(adding|including)",
        r"(don't|do not)\s+(want|need|include)",
        r"(shorter|longer|faster|quicker)\s+(test|assessment|duration)",
        r"(only|just)\s+(want|need|show)",
    ]
    return any(re.search(p, content, re.IGNORECASE) for p in refinement_patterns)


def _has_sufficient_context(messages: list[dict]) -> bool:
    """
    Check if the conversation has enough context to make recommendations.

    Sufficient context means at least 2 of:
    - Job role/title mentioned
    - Competencies/skills mentioned
    - Assessment type preference mentioned
    - Seniority level mentioned

    OR: A detailed job description (long message with multiple keywords).
    """
    # Combine all user messages
    user_text = " ".join(
        msg.get("content", "").lower()
        for msg in messages
        if msg.get("role") == "user"
    )

    # Check for detailed job description (long message with multiple keywords)
    last_user = _get_last_user_message(messages).lower()
    if len(last_user) > 200:  # Long message likely a job description
        return True

    # Count how many context dimensions are present
    dimensions = 0

    # Job role indicators
    role_keywords = [
        "developer", "engineer", "manager", "analyst", "designer",
        "administrator", "coordinator", "specialist", "director",
        "consultant", "architect", "lead", "supervisor", "executive",
        "accountant", "sales", "marketing", "support", "service",
    ]
    if any(kw in user_text for kw in role_keywords):
        dimensions += 1

    # Competency indicators
    competency_keywords = [
        "numerical", "verbal", "reasoning", "communication",
        "leadership", "problem solving", "analytical", "technical",
        "interpersonal", "teamwork", "attention to detail",
        "critical thinking", "decision making", "planning",
        "java", "python", "sql", "programming", "coding",
        "excel", "data", "statistics", "mathematical",
        "writing", "reading", "typing", "administrative",
        "customer", "sales", "financial", "accounting",
        "project management", "agile", "scrum",
        "html", "css", "javascript", "react", "angular",
        "machine learning", "artificial intelligence",
        "networking", "security", "cloud", "devops",
        "mechanical", "electrical", "civil",
        "verbal ability", "numerical ability", "inductive",
        "deductive", "spatial", "abstract",
    ]
    if any(kw in user_text for kw in competency_keywords):
        dimensions += 1

    # Assessment type indicators
    type_keywords = [
        "personality", "cognitive", "ability", "knowledge",
        "simulation", "behavioral", "aptitude", "psychometric",
        "skills test", "coding test", "typing test",
        "knowledge test", "ability test", "reasoning test",
    ]
    if any(kw in user_text for kw in type_keywords):
        dimensions += 1

    # Seniority indicators
    seniority_keywords = [
        "entry", "junior", "mid", "senior", "lead", "principal",
        "executive", "intern", "graduate", "experienced",
        "years", "year experience",
    ]
    if any(kw in user_text for kw in seniority_keywords):
        dimensions += 1

    # Specific technology/product names — if user mentions a specific tech,
    # they know what they want (treat as sufficient context)
    specific_tech = [
        "excel", "word", "powerpoint", "outlook", "office",
        "java", "python", "sql", "javascript", ".net", "c#", "c++",
        "react", "angular", "node", "ruby", "php", "swift",
        "aws", "azure", "gcp", "docker", "kubernetes",
        "salesforce", "sap", "oracle", "tableau", "power bi",
        "opq", "verify", "shl",
    ]
    if any(tech in user_text for tech in specific_tech):
        dimensions += 1  # Counts as an extra dimension

    return dimensions >= 2


def _count_clarifying_turns(messages: list[dict]) -> int:
    """
    Count how many times the assistant has asked clarifying questions.

    A clarifying turn is an assistant message with empty recommendations.
    """
    count = 0
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            try:
                parsed = json.loads(content)
                if not parsed.get("recommendations"):
                    count += 1
            except (json.JSONDecodeError, TypeError):
                # If we can't parse it, assume it was a clarification
                if "?" in content and "recommend" not in content.lower():
                    count += 1
    return count


# ============================================================
# BEHAVIOR HANDLERS
# ============================================================


def _handle_clarify(messages: list[dict]) -> dict:
    """Handle CLARIFY behavior — ask a clarifying question."""
    conversation_summary = _summarize_conversation(messages)
    prompt_addition = build_clarify_prompt(conversation_summary)

    # Add the prompt as a system-level instruction in the last user message context
    augmented_messages = messages.copy()
    augmented_messages.append({"role": "user", "content": prompt_addition})

    raw_response = call_llm(augmented_messages, SYSTEM_PROMPT)
    result = _parse_llm_response(raw_response)

    # Ensure no recommendations in clarify mode
    result["recommendations"] = []
    result["end_of_conversation"] = False

    return result


def _handle_recommend(messages: list[dict]) -> dict:
    """Handle RECOMMEND behavior — provide assessment recommendations."""
    retriever = get_retriever()

    # Synthesize search query from conversation
    query = _synthesize_query(messages)

    # Retrieve relevant catalog entries
    results = retriever.search(query, top_k=config.RETRIEVER_TOP_K)

    if not results:
        return {
            "reply": "I couldn't find assessments matching your specific needs. Could you provide more details about the role or competencies you're looking for?",
            "recommendations": [],
            "end_of_conversation": False,
        }

    # Build prompt with catalog context
    conversation_summary = _summarize_conversation(messages)
    catalog_context = format_catalog_entries(results)
    prompt_addition = build_recommend_prompt(conversation_summary, catalog_context)

    augmented_messages = messages.copy()
    augmented_messages.append({"role": "user", "content": prompt_addition})

    raw_response = call_llm(augmented_messages, SYSTEM_PROMPT)
    result = _parse_llm_response(raw_response)

    # Provenance validation
    if result["recommendations"]:
        result["recommendations"] = _validate_provenance(
            result["recommendations"], retriever.get_all_entries()
        )

    return result


def _handle_refine(messages: list[dict]) -> dict:
    """Handle REFINE behavior — update shortlist based on changed constraints."""
    retriever = get_retriever()

    # Get previous recommendations from conversation
    previous_shortlist = _get_previous_recommendations(messages)

    # Synthesize updated search query
    query = _synthesize_query(messages)
    results = retriever.search(query, top_k=config.RETRIEVER_TOP_K)

    # Build refine prompt
    conversation_summary = _summarize_conversation(messages)
    catalog_context = format_catalog_entries(results)
    previous_json = json.dumps(previous_shortlist, indent=2) if previous_shortlist else "[]"
    prompt_addition = build_refine_prompt(conversation_summary, previous_json, catalog_context)

    augmented_messages = messages.copy()
    augmented_messages.append({"role": "user", "content": prompt_addition})

    raw_response = call_llm(augmented_messages, SYSTEM_PROMPT)
    result = _parse_llm_response(raw_response)

    # Provenance validation
    if result["recommendations"]:
        result["recommendations"] = _validate_provenance(
            result["recommendations"], retriever.get_all_entries()
        )

    return result


def _handle_compare(messages: list[dict]) -> dict:
    """Handle COMPARE behavior — compare assessments using only catalog data."""
    retriever = get_retriever()

    # Extract assessment names from the user's message
    last_msg = _get_last_user_message(messages)
    query = last_msg  # Use the full comparison question as search query

    # Retrieve relevant assessments
    results = retriever.search(query, top_k=5)

    # Build compare prompt with full assessment details
    assessments_data = format_catalog_entries(results)
    prompt_addition = build_compare_prompt(assessments_data)

    augmented_messages = messages.copy()
    augmented_messages.append({"role": "user", "content": prompt_addition})

    raw_response = call_llm(augmented_messages, SYSTEM_PROMPT)
    result = _parse_llm_response(raw_response)

    # Comparisons may or may not include recommendations
    if result["recommendations"]:
        result["recommendations"] = _validate_provenance(
            result["recommendations"], retriever.get_all_entries()
        )

    return result


def _handle_refuse(messages: list[dict]) -> dict:
    """Handle REFUSE behavior — politely decline off-topic requests."""
    prompt_addition = build_refuse_prompt()

    augmented_messages = messages.copy()
    augmented_messages.append({"role": "user", "content": prompt_addition})

    raw_response = call_llm(augmented_messages, SYSTEM_PROMPT)
    result = _parse_llm_response(raw_response)

    # Ensure no recommendations on refusal
    result["recommendations"] = []
    result["end_of_conversation"] = False

    return result


def _handle_forced_recommend(messages: list[dict]) -> dict:
    """Handle forced recommendation at turn limit."""
    retriever = get_retriever()

    query = _synthesize_query(messages)
    results = retriever.search(query, top_k=config.RETRIEVER_TOP_K)

    conversation_summary = _summarize_conversation(messages)
    catalog_context = format_catalog_entries(results)
    prompt_addition = build_forced_recommend_prompt(conversation_summary, catalog_context)

    augmented_messages = messages.copy()
    augmented_messages.append({"role": "user", "content": prompt_addition})

    raw_response = call_llm(augmented_messages, SYSTEM_PROMPT)
    result = _parse_llm_response(raw_response)

    # Provenance validation
    if result["recommendations"]:
        result["recommendations"] = _validate_provenance(
            result["recommendations"], retriever.get_all_entries()
        )

    # If provenance removed all recommendations, provide fallback from retriever
    if not result["recommendations"] and results:
        result["recommendations"] = [
            {"name": r["name"], "url": r["url"], "test_type": r["test_type"]}
            for r in results[:5]
        ]

    result["end_of_conversation"] = True
    return result


# ============================================================
# HELPER FUNCTIONS
# ============================================================


def _synthesize_query(messages: list[dict]) -> str:
    """
    Extract a semantic search query from the conversation context.

    Combines key terms from all user messages into a focused search string.
    This is NOT an LLM call — it's simple text extraction.

    Args:
        messages: Full conversation history.

    Returns:
        Search query string for the retriever.
    """
    # Combine all user messages
    user_parts = []
    for msg in messages:
        if msg.get("role") == "user":
            user_parts.append(msg.get("content", ""))

    # Join all user messages — the retriever will find semantic matches
    combined = " ".join(user_parts)

    # Truncate to reasonable length for embedding
    if len(combined) > 500:
        combined = combined[:500]

    return combined


def _summarize_conversation(messages: list[dict]) -> str:
    """
    Create a brief summary of the conversation for prompt context.

    Args:
        messages: Full conversation history.

    Returns:
        Summary string of user's stated needs.
    """
    user_messages = [
        msg.get("content", "")
        for msg in messages
        if msg.get("role") == "user"
    ]
    summary = " | ".join(user_messages[-3:])  # Last 3 user messages
    if len(summary) > 500:
        summary = summary[:500]
    return summary


def _get_previous_recommendations(messages: list[dict]) -> list[dict]:
    """
    Extract the most recent recommendations from conversation history.

    Args:
        messages: Full conversation history.

    Returns:
        List of recommendation dicts from the last assistant message that had them.
    """
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            try:
                parsed = json.loads(content)
                if parsed.get("recommendations"):
                    return parsed["recommendations"]
            except (json.JSONDecodeError, TypeError):
                continue
    return []


def _parse_llm_response(raw_response: str) -> dict:
    """
    Parse the LLM's raw text response into a structured dict.

    Handles cases where the LLM returns:
    - Valid JSON directly
    - JSON wrapped in markdown code blocks
    - Malformed JSON (falls back to empty recommendations)

    Args:
        raw_response: Raw string from call_llm().

    Returns:
        Dict with keys: reply, recommendations, end_of_conversation.
    """
    # Try to extract JSON from the response
    text = raw_response.strip()

    # Remove markdown code block wrappers if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = json.loads(text)

        # Validate expected fields
        reply = parsed.get("reply", "")
        recommendations = parsed.get("recommendations", [])
        end_of_conversation = parsed.get("end_of_conversation", False)

        # Ensure reply is a string
        if not isinstance(reply, str) or not reply:
            reply = "I can help you find the right SHL assessments. What role are you hiring for?"

        # Ensure recommendations is a list
        if not isinstance(recommendations, list):
            recommendations = []

        # Validate each recommendation has required fields
        valid_recs = []
        for rec in recommendations:
            if (
                isinstance(rec, dict)
                and rec.get("name")
                and rec.get("url")
                and rec.get("test_type")
            ):
                valid_recs.append({
                    "name": str(rec["name"]),
                    "url": str(rec["url"]),
                    "test_type": str(rec["test_type"]),
                })

        # Cap at MAX_RECOMMENDATIONS
        valid_recs = valid_recs[:config.MAX_RECOMMENDATIONS]

        return {
            "reply": reply[:config.MAX_REPLY_LENGTH],
            "recommendations": valid_recs,
            "end_of_conversation": bool(end_of_conversation),
        }

    except json.JSONDecodeError:
        # If JSON parsing fails, use the raw text as the reply
        return {
            "reply": raw_response[:config.MAX_REPLY_LENGTH] if raw_response else "How can I help you find the right SHL assessment?",
            "recommendations": [],
            "end_of_conversation": False,
        }


def _validate_provenance(recommendations: list[dict], catalog: list[dict]) -> list[dict]:
    """
    Filter recommendations to only those with exact name+url match in catalog.

    This is the critical anti-hallucination layer. Every recommendation must
    reference a real catalog entry with matching name AND url.

    Args:
        recommendations: List of recommendation dicts from LLM.
        catalog: Full catalog from retriever.get_all_entries().

    Returns:
        Filtered list containing only verified recommendations.
    """
    # Build lookup: name → url (case-sensitive)
    catalog_lookup = {entry["name"]: entry["url"] for entry in catalog}

    validated = []
    for rec in recommendations:
        name = rec.get("name", "")
        url = rec.get("url", "")

        # Case-sensitive exact match on both name and url
        if name in catalog_lookup and catalog_lookup[name] == url:
            validated.append(rec)

    return validated


def _validate_response(result: dict) -> dict:
    """
    Final validation to ensure response matches schema constraints.

    Args:
        result: Dict with reply, recommendations, end_of_conversation.

    Returns:
        Validated dict guaranteed to match ChatResponse schema.
    """
    # Ensure reply exists and is within limits
    reply = result.get("reply", "")
    if not reply:
        reply = "How can I help you find the right SHL assessment?"
    reply = reply[:config.MAX_REPLY_LENGTH]

    # Ensure recommendations is a list with 0-10 items
    recommendations = result.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []
    recommendations = recommendations[:config.MAX_RECOMMENDATIONS]

    # Ensure end_of_conversation is boolean
    end_of_conversation = bool(result.get("end_of_conversation", False))

    return {
        "reply": reply,
        "recommendations": recommendations,
        "end_of_conversation": end_of_conversation,
    }
