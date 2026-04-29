import os
import requests

BAD_WORDS = [
    "hack", "scam", "lawsuit", "ban", "crash", "fraud",
    "sec", "investigation", "stolen", "malicious",
    "corruption", "exploit", "bankruptcy"
]

def get_news():
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return []

    url = f"https://newsapi.org/v2/everything?q=bitcoin OR crypto&language=en&sortBy=publishedAt&apiKey={key}"

    try:
        data = requests.get(url, timeout=10).json()
        return data.get("articles", [])[:5]
    except:
        return []

def news_is_risky(news):
    for article in news:
        title = article.get("title", "").lower()
        description = article.get("description", "").lower()

        for word in BAD_WORDS:
            if word in title or word in description:
                return True, word

    return False, None