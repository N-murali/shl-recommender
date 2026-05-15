"""Test HF API with feature-extraction compatible models."""
import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("HF_API_TOKEN")
headers = {"Authorization": f"Bearer {token}"}

# Try models that support feature-extraction (returns embeddings)
models = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "BAAI/bge-small-en-v1.5",
    "intfloat/e5-small-v2",
]

for model in models:
    url = f"https://router.huggingface.co/hf-inference/models/{model}"
    print(f"\nModel: {model}")
    print(f"URL: {url}")
    
    # Try feature-extraction style payload
    payload = {"inputs": "java developer programming test", "options": {"wait_for_model": True}}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                if isinstance(data[0], list):
                    print(f"  ✓ Got embeddings! Shape: [{len(data)}][{len(data[0])}]")
                elif isinstance(data[0], float):
                    print(f"  Got flat list, length: {len(data)}")
                else:
                    print(f"  List of {type(data[0])}")
            else:
                print(f"  Type: {type(data)}, preview: {str(data)[:200]}")
        else:
            print(f"  Error: {r.text[:200]}")
    except Exception as e:
        print(f"  Exception: {e}")

