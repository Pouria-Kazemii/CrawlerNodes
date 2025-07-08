import os
from dotenv import load_dotenv

load_dotenv(".env")  # Load your crawler-specific env

LARAVEL_API_URL = os.getenv("LARAVEL_API_URL")
LARAVEL_API_TOKEN = os.getenv("LARAVEL_API_TOKEN")
