import requests
from config import LARAVEL_API_URL, LARAVEL_API_TOKEN

def send_result_to_laravel(payload):
    try:
        headers = {
            "Authorization": f"Bearer {LARAVEL_API_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(LARAVEL_API_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Failed to send result to Laravel: {e}")
        return False
