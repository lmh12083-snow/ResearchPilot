"""
Metadata extraction service.

Sources (priority order):
  1. arXiv API — when imported from arXiv
  2. Semantic Scholar API — best metadata enrichment
  3. Crossref API — fallback for DOI lookup
"""
import json
import re
from typing import Optional

import httpx
from xml.etree import ElementTree


ARXIV_API_URL = "http://export.arxiv.org/api/query?id_list={arxiv_id}"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/{source}:{id}"
CROSSREF_WORKS_URL = "https://api.crossref.org/works/{doi}"

NS = {"arxiv": "http://www.w3.org/2005/Atom"}


def fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Fetch title, authors, abstract from arXiv API."""
    url = ARXIV_API_URL.format(arxiv_id=arxiv_id)
    resp = httpx.get(url, timeout=15)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)
    entry = root.find("arxiv:entry", NS)

    title = ""
    authors = []
    abstract = ""
    doi = None

    if entry is not None:
        title_el = entry.find("arxiv:title", NS)
        if title_el is not None and title_el.text:
            title = title_el.text.strip().replace("\n", " ").replace("  ", " ")

        for author_el in entry.findall("arxiv:author", NS):
            name_el = author_el.find("arxiv:name", NS)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        abstract_el = entry.find("arxiv:summary", NS)
        if abstract_el is not None and abstract_el.text:
            abstract = abstract_el.text.strip().replace("\n", " ").replace("  ", " ")

        # Extract DOI from links or comments
        for link in entry.findall("arxiv:link", NS):
            href = link.get("href", "")
            if "doi.org/" in href:
                doi = href.split("doi.org/")[-1]
                break

    year = _guess_year(arxiv_id)

    return {
        "title": title or None,
        "authors": json.dumps(authors, ensure_ascii=False) if authors else None,
        "abstract": abstract or None,
        "doi": doi,
        "year": year,
        # arXiv category tags as keywords
        "keywords": None,  # will try semantic scholar
    }


def fetch_semantic_scholar(source: str, sid: str) -> dict:
    """Enrich metadata from Semantic Scholar API.

    Args:
        source: "arXiv", "DOI", "CorpusId", "Title"
        sid: The ID value
    """
    url = SEMANTIC_SCHOLAR_URL.format(source=source, id=sid)
    params = {
        "fields": "title,authors,year,abstract,externalIds,keywords,publicationDate"
    }
    try:
        resp = httpx.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        result = {}
        if data.get("authors"):
            result["authors"] = json.dumps(
                [a.get("name", "") for a in data["authors"] if a.get("name")],
                ensure_ascii=False,
            )
        if data.get("abstract"):
            result["abstract"] = data["abstract"]
        if data.get("year"):
            result["year"] = data["year"]
        if data.get("keywords"):
            result["keywords"] = json.dumps(
                [k for k in data["keywords"] if k],
                ensure_ascii=False,
            )
        if data.get("externalIds", {}).get("DOI"):
            result["doi"] = data["externalIds"]["DOI"]
        return result
    except Exception:
        return {}


def fetch_crossref(doi: str) -> dict:
    """Enrich metadata from Crossref API."""
    url = CROSSREF_WORKS_URL.format(doi=doi)
    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})

        result = {}
        if message.get("author"):
            result["authors"] = json.dumps(
                [f"{a.get('given', '')} {a.get('family', '')}".strip()
                 for a in message["author"]],
                ensure_ascii=False,
            )
        if message.get("title"):
            result["title"] = message["title"][0]
        if message.get("abstract"):
            # Strip HTML tags from abstract
            abstract = re.sub(r"<[^>]+>", "", message["abstract"])
            result["abstract"] = abstract
        if message.get("published-print", {}).get("date-parts"):
            result["year"] = message["published-print"]["date-parts"][0][0]
        elif message.get("published-online", {}).get("date-parts"):
            result["year"] = message["published-online"]["date-parts"][0][0]
        if message.get("DOI"):
            result["doi"] = message["DOI"]
        return result
    except Exception:
        return {}


def enrich_paper_metadata(
    arxiv_id: Optional[str] = None,
    title: Optional[str] = None,
    doi: Optional[str] = None,
) -> dict:
    """Cascade through metadata sources to get the best result.

    Priority: arXiv API → Semantic Scholar → Crossref
    """
    merged: dict = {}

    # 1. arXiv API
    if arxiv_id:
        try:
            merged.update(fetch_arxiv_metadata(arxiv_id))
        except Exception:
            pass

    # 2. Semantic Scholar (by arXiv ID / DOI / title)
    ss_id = None
    ss_source = None
    if arxiv_id:
        ss_id = arxiv_id
        ss_source = "arXiv"
    elif doi:
        ss_id = doi
        ss_source = "DOI"

    if ss_id and ss_source:
        ss_data = fetch_semantic_scholar(ss_source, ss_id)
        merged.update(ss_data)

    # 3. Crossref (by DOI)
    if doi or merged.get("doi"):
        try:
            crossref_data = fetch_crossref(doi or merged["doi"])
            # Don't override arXiv/SemanticScholar title with Crossref
            if crossref_data.get("doi"):
                merged.setdefault("doi", crossref_data["doi"])
            if crossref_data.get("year"):
                merged.setdefault("year", crossref_data["year"])
            if crossref_data.get("authors"):
                merged.setdefault("authors", crossref_data["authors"])
            if crossref_data.get("abstract"):
                merged.setdefault("abstract", crossref_data["abstract"])
        except Exception:
            pass

    # 4. Try Semantic Scholar by title as fallback
    if title and not merged.get("authors"):
        try:
            # URL-encode the title for the Title-based lookup
            import urllib.parse
            title_encoded = urllib.parse.quote(title)
            ss_data = fetch_semantic_scholar("Title", title_encoded)
            merged.update(ss_data)
        except Exception:
            pass

    return merged


def _guess_year(arxiv_id: str) -> Optional[int]:
    """Extract year from arXiv ID (first 2 digits)."""
    match = re.match(r"(\d{2})\d{2}\.", arxiv_id)
    if match:
        prefix = int(match.group(1))
        # arXiv IDs started in 1991 (91), IDs after 2000 use 00xx.xxxx format
        if prefix <= 91:
            return 1900 + prefix
        else:
            return 2000 + prefix
    return None
