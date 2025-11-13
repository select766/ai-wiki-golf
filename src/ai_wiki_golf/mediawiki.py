from __future__ import annotations

from collections import defaultdict
from typing import Optional

import requests

HEADERS = {
    "User-Agent": "ai-wiki-golf/0.1 (contact: select766@outlook.jp)",
}


class MediaWikiClient:
    def __init__(self, api_url: str):
        self.api_url = api_url

    def get_random_pages(self, limit: int = 1) -> list[str]:
        resp = requests.get(
            self.api_url,
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

    def get_page_abstract(self, title: str) -> Optional[str]:
        resp = requests.get(
            self.api_url,
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

    def get_links(self, title: str) -> Optional[list[str]]:
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
            resp = requests.get(self.api_url, query, headers=HEADERS, timeout=30)
            result = resp.json()
            for _, page_info in result.get("query", {}).get("pages", {}).items():
                if "missing" in page_info:
                    return None
                links = page_info.get("links", [])
                if not links:
                    continue
                page_links[page_info["title"].strip()].extend(
                    [p["title"].strip() for p in links if "title" in p]
                )
            if cont := result.get("continue"):
                query.update(cont)
            else:
                break
        return page_links.get(title, [])

    def get_backlink_count(self, title: str) -> int:
        query = {
            "action": "query",
            "format": "json",
            "list": "backlinks",
            "bltitle": title,
            "blnamespace": 0,
            "bllimit": 500,
        }
        count = 0
        while True:
            resp = requests.get(self.api_url, query, headers=HEADERS, timeout=30)
            result = resp.json()
            backlinks = result.get("query", {}).get("backlinks", [])
            count += len(backlinks)
            if cont := result.get("continue"):
                query.update(cont)
            else:
                break

        return count
