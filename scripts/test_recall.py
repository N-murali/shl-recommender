"""
scripts/test_recall.py — Estimate Recall@10 with known-answer queries.

We don't have the evaluator's ground truth, but we can test with queries
where we know which assessments SHOULD appear in the results.

Recall@10 = (correct assessments in our top 10) / (total correct assessments)
"""
import json
import httpx
import time

BASE = "http://localhost:10000"

# Load catalog to know what exists
catalog = json.load(open("data/catalog.json", encoding="utf-8"))
catalog_names = {e["name"] for e in catalog}

def get_recommendations(query):
    """Get recommendations from live endpoint."""
    r = httpx.post(f"{BASE}/chat", json={
        "messages": [{"role": "user", "content": query}]
    }, timeout=35)
    if r.status_code == 200:
        return [rec["name"] for rec in r.json().get("recommendations", [])]
    return []

def recall_at_10(predicted, expected):
    """Calculate Recall@10."""
    if not expected:
        return 1.0  # No expected items = perfect recall
    correct = len(set(predicted[:10]) & set(expected))
    return correct / len(expected)

# Test cases with expected assessments (based on catalog knowledge)
test_cases = [
    {
        "query": "I need a Java programming knowledge test for an experienced developer",
        "expected": ["Java 8 (New)", "Core Java (Advanced Level) (New)", "Core Java (Entry Level) (New)", "Java Web Services (New)", "Java Design Patterns (New)", "Java Frameworks (New)"],
        "description": "Java developer"
    },
    {
        "query": "I need personality assessments for leadership and management roles",
        "expected": ["Occupational Personality Questionnaire OPQ32r", "OPQ Leadership Report", "OPQ Manager Plus Report"],
        "description": "Personality/Leadership"
    },
    {
        "query": "Numerical reasoning and data interpretation ability tests for analysts",
        "expected": ["SHL Verify Interactive \u2013 Numerical Reasoning", "Verify - Numerical Ability", "SHL Verify Interactive Numerical Calculation"],
        "description": "Numerical reasoning"
    },
    {
        "query": "Customer service phone skills assessment for entry level representatives",
        "expected": ["Customer Service Phone Solution", "Customer Service Phone Simulation", "Entry Level Customer Service (General) Solution"],
        "description": "Customer service"
    },
    {
        "query": "Python and SQL programming knowledge tests for software developers",
        "expected": ["Python (New)", "SQL (New)", "SQL Server (New)"],
        "description": "Python/SQL developer"
    },
    {
        "query": "Microsoft Excel and data analysis skills test",
        "expected": ["MS Excel (New)", "Data Science (New)", "Basic Statistics (New)"],
        "description": "Excel/Data"
    },
]

print("=" * 60)
print("RECALL@10 ESTIMATION")
print("=" * 60)

total_recall = 0
for tc in test_cases:
    print(f"\n--- {tc['description']} ---")
    print(f"  Query: {tc['query'][:60]}...")
    
    recs = get_recommendations(tc["query"])
    recall = recall_at_10(recs, tc["expected"])
    total_recall += recall
    
    print(f"  Expected: {tc['expected'][:3]}...")
    print(f"  Got: {recs[:5]}")
    
    # Show which expected items were found
    found = set(recs[:10]) & set(tc["expected"])
    missed = set(tc["expected"]) - set(recs[:10])
    print(f"  Found: {list(found)}")
    if missed:
        print(f"  Missed: {list(missed)}")
    print(f"  Recall@10: {recall:.2f} ({len(found)}/{len(tc['expected'])})")
    
    time.sleep(1)  # Rate limit

mean_recall = total_recall / len(test_cases)
print(f"\n{'=' * 60}")
print(f"MEAN RECALL@10: {mean_recall:.2f} ({mean_recall*100:.0f}%)")
print(f"{'=' * 60}")
print(f"\nNote: This is an estimate. The actual evaluator uses different")
print(f"test conversations with its own ground truth data.")
