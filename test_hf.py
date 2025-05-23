# test_hf.py
import requests
from config import HUGGINGFACE_TOKEN

url = "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
payload = {
    "inputs": "Un paisaje al atardecer con montañas nevadas",
    "options": {"wait_for_model": True}
}

resp = requests.post(url, headers=headers, json=payload)
print("Status:", resp.status_code)
print("Body :", resp.text[:300])
