"""
prompts.py — System prompt and all prompt templates for the SHL Recommender agent.

What this file does:
    Contains the system prompt that defines the agent's persona, rules, and
    response format, plus behavior-specific prompt templates for each mode
    (clarify, recommend, refine, compare, refuse).

Why these decisions:
    - System prompt is ~800 tokens — fits within Groq's context window budget.
    - JSON output format is explicitly defined in the system prompt so the LLM
      always returns parseable structured responses.
    - Each behavior has its own prompt template to give the LLM clear instructions
      for that specific mode.
    - Separated from agent.py so prompts can be tuned without touching logic.

What breaks if this file is wrong:
    - Wrong JSON format instructions → LLM returns unparseable responses → schema violation.
    - Missing behavior rules → LLM recommends on turn 1 for vague queries → fails behavior probe.
    - No grounding instructions → LLM hallucinates assessment names → fails provenance check.
    - Too long system prompt → exceeds token budget → truncated context → poor responses.
"""

# ============================================================
# SYSTEM PROMPT — Defines agent persona, rules, and output format
# ============================================================

SYSTEM_PROMPT = """You are an SHL Assessment Recommender — a helpful AI assistant that helps hiring managers find the right SHL assessments for their candidates.

## YOUR RULES (FOLLOW STRICTLY):

1. You ONLY recommend assessments from the provided catalog data. NEVER invent or hallucinate assessment names, URLs, or details.
2. You MUST respond in valid JSON format on every turn. No markdown, no extra text outside the JSON.
3. When you don't have enough information, ask clarifying questions. Do NOT recommend on the first turn for vague queries.
4. Maximum 2 clarifying questions before you must provide recommendations.
5. When recommending, provide 1-10 assessments. Never 0 (when recommending), never more than 10.
6. If the user asks something unrelated to SHL assessments (off-topic, legal questions, general advice), politely refuse and redirect.
7. If the user changes constraints after you've recommended, UPDATE the shortlist — don't restart.
8. For comparison questions, use ONLY the catalog data provided. Never use your own knowledge about assessments.

## RESPONSE FORMAT (EVERY TURN):

You MUST return EXACTLY this JSON structure:
{
  "reply": "Your natural language response to the user",
  "recommendations": [],
  "end_of_conversation": false
}

Rules for fields:
- "reply": Your conversational message (string, max 2000 chars)
- "recommendations": Empty array [] when clarifying or refusing. Array of 1-10 objects when recommending.
- "end_of_conversation": false unless the conversation is complete (user is satisfied or turn limit reached)

Each recommendation object MUST have exactly:
{
  "name": "exact assessment name from catalog",
  "url": "exact URL from catalog",
  "test_type": "exact test_type from catalog"
}

## BEHAVIOR MODES:

- CLARIFY: Ask about role, competencies, seniority, assessment type preferences
- RECOMMEND: Provide 1-10 assessments with explanation of relevance
- REFINE: Update shortlist based on changed constraints, explain what changed
- COMPARE: Compare assessments using only provided catalog data
- REFUSE: Politely decline off-topic requests, redirect to assessments

IMPORTANT: Only use assessment data from the CATALOG CONTEXT provided below. Never make up assessments."""


# ============================================================
# BEHAVIOR-SPECIFIC PROMPT TEMPLATES
# ============================================================

def build_clarify_prompt(conversation_summary: str) -> str:
    """
    Build the user-facing prompt for CLARIFY mode.

    Instructs the LLM to ask a clarifying question based on what's missing
    from the conversation context.

    Args:
        conversation_summary: Summary of what the user has said so far.

    Returns:
        Prompt string to append to the conversation.
    """
    return f"""Based on the conversation so far, you need more information to recommend assessments.

What you know: {conversation_summary}

Ask ONE focused clarifying question about what's missing. Consider asking about:
- Job role/title
- Required competencies or skills
- Seniority level (entry, mid, senior)
- Type of assessment preferred (knowledge, personality, ability, simulation)
- Duration constraints

Remember: Return valid JSON with empty recommendations array and end_of_conversation=false."""


def build_recommend_prompt(conversation_summary: str, catalog_context: str) -> str:
    """
    Build the prompt for RECOMMEND mode with retrieved catalog entries.

    Provides the LLM with relevant catalog entries and instructs it to
    select and recommend the most appropriate ones.

    Args:
        conversation_summary: Summary of user's needs from conversation.
        catalog_context: Formatted string of retrieved catalog entries.

    Returns:
        Prompt string with catalog context for recommendation.
    """
    return f"""Based on the conversation, the user needs:
{conversation_summary}

## CATALOG CONTEXT (use ONLY these assessments):
{catalog_context}

Select 1-10 assessments from the catalog above that best match the user's needs.
For each recommendation, use the EXACT name, url, and test_type from the catalog.
In your reply, briefly explain why each assessment is relevant to their needs.

Return valid JSON with recommendations array containing 1-10 items."""


def build_refine_prompt(
    conversation_summary: str, previous_shortlist: str, catalog_context: str
) -> str:
    """
    Build the prompt for REFINE mode when user changes constraints.

    Provides previous recommendations and new catalog context so the LLM
    can update the shortlist based on changed constraints.

    Args:
        conversation_summary: Updated summary including new constraints.
        previous_shortlist: JSON string of previous recommendations.
        catalog_context: New catalog entries based on updated search.

    Returns:
        Prompt string for refinement.
    """
    return f"""The user has changed their constraints. Update the recommendation shortlist.

Updated needs: {conversation_summary}

Previous recommendations:
{previous_shortlist}

## UPDATED CATALOG CONTEXT (use ONLY these assessments):
{catalog_context}

Update the shortlist based on the new constraints. In your reply:
1. Explain what changed (what was added/removed/kept)
2. Provide 1-10 updated recommendations using EXACT name, url, test_type from catalog

Return valid JSON with updated recommendations array."""


def build_compare_prompt(assessments_data: str) -> str:
    """
    Build the prompt for COMPARE mode using only catalog data.

    Provides specific assessment details from the catalog for comparison.
    The LLM must NOT use its own knowledge — only the provided data.

    Args:
        assessments_data: Formatted string with full details of assessments to compare.

    Returns:
        Prompt string for comparison.
    """
    return f"""The user wants to compare assessments. Use ONLY the data below — do NOT use your own knowledge.

## ASSESSMENT DATA FROM CATALOG:
{assessments_data}

Compare these assessments based on the catalog data provided:
- Test type
- Duration
- Remote testing support
- Adaptive/IRT
- Description/what it measures

If an assessment is not found in the data above, say so. Never invent details.
Return valid JSON with your comparison in the reply field. Recommendations array can be empty or contain the compared assessments."""


def build_refuse_prompt() -> str:
    """
    Build the prompt for REFUSE mode (off-topic, injection, unrelated).

    Returns:
        Prompt string for polite refusal.
    """
    return """The user's message is not related to SHL assessments. Politely decline and redirect.

Your response should:
1. Acknowledge their message without being negative
2. Explain that you specialize in SHL assessment recommendations
3. Offer to help them find the right assessment

Return valid JSON with empty recommendations array and end_of_conversation=false."""


def build_forced_recommend_prompt(conversation_summary: str, catalog_context: str) -> str:
    """
    Build the prompt for forced recommendation at turn limit.

    When the conversation reaches the 8-turn limit, the agent must provide
    best-effort recommendations regardless of context completeness.

    Args:
        conversation_summary: Whatever context has been gathered so far.
        catalog_context: Retrieved catalog entries based on available context.

    Returns:
        Prompt string for forced recommendation.
    """
    return f"""You've reached the conversation turn limit. You MUST provide recommendations now based on what you know.

What you know: {conversation_summary}

## CATALOG CONTEXT:
{catalog_context}

Provide your best 1-10 recommendations based on available information.
Set end_of_conversation to true.
In your reply, acknowledge that you're providing best-effort recommendations based on limited context.

Return valid JSON with recommendations (1-10 items) and end_of_conversation=true."""


def format_catalog_entries(entries: list[dict]) -> str:
    """
    Format a list of catalog entries into a readable string for the LLM prompt.

    Args:
        entries: List of catalog entry dicts from retriever.search().

    Returns:
        Formatted multi-line string with assessment details.
    """
    if not entries:
        return "(No matching assessments found in catalog)"

    lines = []
    for i, entry in enumerate(entries, 1):
        name = entry.get("name", "Unknown")
        url = entry.get("url", "")
        test_type = entry.get("test_type", "")
        description = entry.get("description", "No description available")
        duration = entry.get("duration", 0)
        remote = entry.get("remote_testing", False)
        adaptive = entry.get("adaptive", False)

        # Truncate description for token budget
        if len(description) > 200:
            description = description[:200] + "..."

        lines.append(
            f"{i}. {name}\n"
            f"   URL: {url}\n"
            f"   Type: {test_type} | Duration: {duration} min | "
            f"Remote: {'Yes' if remote else 'No'} | Adaptive: {'Yes' if adaptive else 'No'}\n"
            f"   Description: {description}"
        )

    return "\n\n".join(lines)
