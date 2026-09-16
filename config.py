import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
GITHUB_PATH = os.getenv("GITHUB_PATH", "images").strip("/")
USE_CDN = os.getenv("USE_CDN", "true").lower() == "true"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN не задан в переменных окружения")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN не задан в переменных окружения")
if not GITHUB_REPO or "/" not in GITHUB_REPO:
    raise RuntimeError("GITHUB_REPO должен быть в формате user/repo")
