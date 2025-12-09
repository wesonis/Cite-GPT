from __future__ import annotations

import re
import webbrowser
from difflib import SequenceMatcher
from typing import List, Optional

from pyzotero import zotero

from .config import AppSettings


class ZoteroClient:
    """Handles read-only queries against the user's Zotero library."""

    def __init__(self, settings: AppSettings) -> None:
        if not settings.zotero_library_id:
            raise ValueError("ZOTERO_LIBRARY_ID is required")
        self._library_id = settings.zotero_library_id
        self._library_type = settings.zotero_library_type
        self._is_local = settings.zotero_use_local

        if self._is_local:
            self._library = zotero.Zotero(
                self._library_id,
                self._library_type,
                local=True,
            )
        else:
            if not settings.zotero_api_key:
                raise ValueError("ZOTERO_API_KEY is required unless using the local connector")
            self._library = zotero.Zotero(
                self._library_id,
                self._library_type,
                settings.zotero_api_key,
            )

    def search_items(self, query: str, limit: int = 10, qmode: Optional[str] = None) -> List[dict]:
        kwargs = {"q": query, "limit": limit}
        if qmode:
            kwargs["qmode"] = qmode
        return self._library.items(**kwargs)

    def search_by_fields(
        self,
        *,
        author: Optional[str] = None,
        title: Optional[str] = None,
        year: Optional[str] = None,
        limit: int = 5,
    ) -> List[dict]:
        if not any((author, title, year)):
            raise ValueError("At least one search parameter is required")
        search_terms = " ".join(term for term in (author, title, year) if term)
        seed_results = max(limit * 3, 20)
        candidates = self._library.items(q=search_terms, limit=seed_results)
        filtered: List[dict] = []

        for item in candidates:
            data = item.get("data", {})
            if author and not _fuzzy_match(author, _authors_as_text(data)):
                continue
            if title and not _fuzzy_match(title, data.get("title", "")):
                continue
            if year and not _year_matches(year, data.get("date", "")):
                continue
            filtered.append(item)
            if len(filtered) >= limit:
                break
        return filtered

    def get_attachment_or_url(self, item: dict) -> Optional[str]:
        attachments = self._library.children(item["key"])
        for att in attachments:
            data = att.get("data", {})
            if data.get("contentType") != "application/pdf":
                continue
            local_path = data.get("path")
            if local_path:
                return local_path
            file_url = att.get("links", {}).get("enclosure", {}).get("href")
            if file_url:
                return file_url
        url = item.get("data", {}).get("url")
        if url:
            return url
        alternate = item.get("links", {}).get("alternate", {}).get("href")
        if alternate:
            return alternate
        return None

    def open_attachment_or_url(self, item: dict) -> None:
        """Retained for CLI callers; prefers PDF attachment."""
        location = self.get_attachment_or_url(item)
        if location:
            webbrowser.open(location)

    @property
    def uses_local(self) -> bool:
        return self._is_local

    def describe_target(self) -> str:
        mode = "Local Zotero connector" if self._is_local else "Zotero web API"
        return f"{mode} (library {self._library_id} / {self._library_type})"

    def is_local_print(self):
        endpoint = self._library.endpoint
        local_yn = self._library.local
        print(f"endpoint: {endpoint}", f" local: {local_yn}")


def _fuzzy_match(expected: str, actual: str) -> bool:
    expected_l = expected.lower().strip()
    actual_l = actual.lower().strip()
    if not expected_l:
        return True
    if expected_l in actual_l:
        return True
    return SequenceMatcher(None, expected_l, actual_l).ratio() >= 0.55


def _authors_as_text(data: dict) -> str:
    creators = data.get("creators", [])
    names = []
    for creator in creators:
        first = creator.get("firstName", "").strip()
        last = creator.get("lastName", "").strip()
        names.append(" ".join(part for part in (first, last) if part))
    return ", ".join(name for name in names if name) or ""


def _year_matches(expected_year: str, raw_date: str) -> bool:
    if not expected_year:
        return True
    match = re.search(r"\d{4}", raw_date or "")
    if not match:
        return False
    return match.group(0) == expected_year.strip()
