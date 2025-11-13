from __future__ import annotations

from collections import defaultdict
from typing import Optional

import requests

API_URL = "https://ja.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "ai-wiki-golf/0.1 (contact: select766@outlook.jp)",
}


def get_random_pages(limit: int = 1) -> list[str]:
    resp = requests.get(
        API_URL,
        {
            "action": "query",
            "format": "json",
            "list": "random",
            "rnlimit": limit,
            "rnnamespace": 0,
        },
        headers=HEADERS,
        timeout=30,
    )
    result = resp.json()
    pages = [p["title"] for p in result["query"]["random"]]
    return pages


def get_page_abstract(title: str) -> Optional[str]:
    resp = requests.get(
        API_URL,
        {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "titles": [title],
            "exchars": 1000,
            "exintro": True,
            "explaintext": True,
        },
        headers=HEADERS,
        timeout=30,
    )
    result = resp.json()
    for _, page_info in result["query"]["pages"].items():
            if page_info["title"] == title:
                return page_info.get("extract")
    return None


def get_links(title: str) -> Optional[list[str]]:
    query = {
        "action": "query",
        "format": "json",
        "prop": "links",
        "titles": [title],
        "pllimit": 500,
        "plnamespace": 0,
    }
    page_links = defaultdict(list)
    while True:
        resp = requests.get(API_URL, query, headers=HEADERS, timeout=30)
        result = resp.json()
        for _, page_info in result["query"]["pages"].items():
            if "missing" in page_info:
                return None
            page_links[page_info["title"].strip()].extend(
                [p["title"].strip() for p in page_info["links"]]
            )
        if cont := result.get("continue"):
            query.update(cont)
        else:
            break
    return page_links.get(title, [])
