"""
Simple test script for the CMAPSS serving layer.
Assumes the server is running at localhost:8000.
Run: uvicorn serve:app --reload
"""

import requests
import numpy as np

BASE_URL = "http://localhost:8000"


def random_cycle(n_cycles: int = 50) -> list[dict]:
    """Generate n_cycles of random sensor readings."""
    return [
        {
            "os_1": np.random.uniform(0, 1),
            "os_2": np.random.uniform(0, 1),
            "os_3": np.random.uniform(0, 100),
            "sensors": np.random.uniform(0, 1, 21).tolist(),
        }
        for _ in range(n_cycles)
    ]


# Health check
resp = requests.get(f"{BASE_URL}/health")
print("Health:", resp.json())
print()

# Single engine prediction
payload = {
    "engine_id": "engine_001",
    "cycles": random_cycle(50),
}
resp = requests.post(f"{BASE_URL}/predict", json=payload)
print("Single prediction:", resp.json())
print()

# Batch prediction
batch_payload = {
    "engines": [
        {"engine_id": f"engine_{i:03d}", "cycles": random_cycle(50)}
        for i in range(3)
    ]
}
resp = requests.post(f"{BASE_URL}/predict/batch", json=batch_payload)
print("Batch predictions:")
for prediction in resp.json()["predictions"]:
    print(" ", prediction)