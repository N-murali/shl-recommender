"""Quick test of the new HF API-based retriever."""
import httpx
import json
import time

BASE = "http://localhost:10000"

# Test 1: Health
print("1. Health check...")
r = httpx.get(f"{BASE}/health")
print(f"   {r.status_code} {r.json()}")

# Test 2: Recommend (detailed query)
print("\n2. Recommend (Java developer)...")
start = time.time()
r = httpx.post(f"{BASE}/chat", json={
    "messages": [{"role": "user", "content": "I need cognitive assessments for a senior Java developer with problem-solving skills"}]
}, timeout=35)
elapsed = time.time() - start
d = r.json()
print(f"   Status: {r.status_code} | Time: {elapsed:.1f}s")
print(f"   Reply: {d['reply'][:120]}...")
print(f"   Recommendations: {len(d['recommendations'])}")
for rec in d["recommendations"][:5]:
    print(f"     - {rec['name']} | {rec['test_type']}")

# Test 3: Clarify (vague)
print("\n3. Clarify (vague query)...")
r = httpx.post(f"{BASE}/chat", json={
    "messages": [{"role": "user", "content": "I need an assessment"}]
}, timeout=35)
d = r.json()
print(f"   Status: {r.status_code}")
print(f"   Reply: {d['reply'][:100]}...")
print(f"   Recommendations: {len(d['recommendations'])} (should be 0)")

# Test 4: Refuse
print("\n4. Refuse (off-topic)...")
r = httpx.post(f"{BASE}/chat", json={
    "messages": [{"role": "user", "content": "Tell me a joke"}]
}, timeout=35)
d = r.json()
print(f"   Status: {r.status_code}")
print(f"   Reply: {d['reply'][:100]}...")
print(f"   Recommendations: {len(d['recommendations'])} (should be 0)")

print("\nAll quick tests done!")
