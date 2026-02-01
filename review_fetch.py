import json
import re
from typing import Optional, Tuple

import requests


def detect_platform(url: str) -> str:
    lower = (url or "").lower()
    if "yandex" in lower or "yandex.ru/maps" in lower:
        return "yandex"
    if "2gis" in lower or "2gis.ru" in lower or "2gis.com" in lower:
        return "2gis"
    return "unknown"


def fetch_url(url: str) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; telegramreviewsbot/1.0; +https://t.me)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.7,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        return resp.status_code, resp.text, None
    except Exception as exc:
        return None, None, str(exc)[:200]


def _extract_json_ld(html: str) -> list:
    blocks = re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    parsed = []
    for block in blocks:
        cleaned = block.strip()
        try:
            obj = json.loads(cleaned)
            parsed.append(obj)
        except Exception:
            continue
    return parsed


def _find_review_in_json(obj: dict) -> Optional[dict]:
    if not isinstance(obj, dict):
        return None
    if obj.get("@type") == "Review":
        return obj
    for key in ("review", "reviews"):
        item = obj.get(key)
        if isinstance(item, dict) and item.get("@type") == "Review":
            return item
        if isinstance(item, list):
            for entry in item:
                if isinstance(entry, dict) and entry.get("@type") == "Review":
                    return entry
    return None


def _extract_review_fields(review: dict) -> dict:
    author = review.get("author")
    author_name = None
    if isinstance(author, dict):
        author_name = author.get("name")
    elif isinstance(author, str):
        author_name = author
    rating_obj = review.get("reviewRating") or {}
    rating_value = None
    if isinstance(rating_obj, dict):
        rating_value = rating_obj.get("ratingValue")
    try:
        rating_value = int(rating_value) if rating_value is not None else None
    except Exception:
        rating_value = None
    return {
        "review_text": review.get("reviewBody") or review.get("description"),
        "author_name": author_name,
        "rating": rating_value,
        "review_date": review.get("datePublished"),
    }


def parse_yandex_review(html: str, url: str) -> dict:
    data = {"parse_status": "partial"}
    public_id_match = re.search(r"reviews%5BpublicId%5D=([a-z0-9]+)", url, re.IGNORECASE)
    if public_id_match:
        data["public_id"] = public_id_match.group(1)
    org_match = re.search(r"/org/[^/]+/(\d+)", url)
    if org_match:
        data["org_id"] = org_match.group(1)

    for obj in _extract_json_ld(html):
        review = _find_review_in_json(obj)
        if review:
            data.update(_extract_review_fields(review))
            break

    if not data.get("review_text"):
        text_match = re.search(r'"reviewBody"\s*:\s*"([^"]+)"', html)
        if text_match:
            data["review_text"] = text_match.group(1)

    if data.get("review_text"):
        data["parse_status"] = "ok"
    return data


def parse_2gis_review(html: str, url: str) -> dict:
    data = {"parse_status": "partial"}
    org_match = re.search(r"/firm/(\d+)", url)
    if org_match:
        data["org_id"] = org_match.group(1)

    for obj in _extract_json_ld(html):
        review = _find_review_in_json(obj)
        if review:
            data.update(_extract_review_fields(review))
            break

    if not data.get("review_text"):
        text_match = re.search(r'"text"\s*:\s*"([^"]+)"', html)
        if text_match:
            data["review_text"] = text_match.group(1)

    if data.get("review_text"):
        data["parse_status"] = "ok"
    return data
