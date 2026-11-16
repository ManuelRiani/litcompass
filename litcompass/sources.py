"""Clients for free, keyless bibliographic sources.

- OpenCitations Index v2: the citation graph (who cites whom), by DOI, in both directions.
- OpenAlex: ONLY single-work lookups by DOI (cost 0 in OpenAlex usage-based pricing): metadata, abstract, open access.
- Crossref: fallback for metadata and references, and keyword search used to find seed papers.

OpenAlex searches and filtered lists are metered and are never used. If OpenAlex ever reports a non-zero cost
for a single lookup, the client stops using it for the rest of the run and falls back to Crossref.
"""
from __future__ import annotations

import html
import logging
import os
import re
import time
from urllib.parse import quote

import requests

from . import __version__

log = logging.getLogger(__name__)

DOI_IN_FIELD = re.compile(r"doi:(10\.\S+)")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


class SourceError(Exception):
    pass


def normalize_doi(s: str) -> str | None:
    """Accepts a bare DOI, doi:..., or a doi.org URL. Returns the lowercase DOI or None."""
    s = (s or "").strip().strip("<>\"'").lower()
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s)
    s = re.sub(r"^doi:\s*", "", s)
    s = s.rstrip(".,;")
    return s if DOI_RE.match(s) else None


class Budget:
    """Counts requests and stops the run when time is up."""

    def __init__(self, max_minutes: float):
        self.t0 = time.monotonic()
        self.deadline = self.t0 + max_minutes * 60
        self.requests = 0

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline

    def elapsed_min(self) -> float:
        return (time.monotonic() - self.t0) / 60


class Http:
    MIN_INTERVAL = {"api.opencitations.net": 0.5, "api.openalex.org": 0.15, "api.crossref.org": 0.25}

    def __init__(self, budget: Budget | None = None):
        self.budget = budget or Budget(10 ** 6)
        self.s = requests.Session()
        self.contact = os.environ.get("CONTACT_EMAIL", "").strip()
        ua = f"litcompass/{__version__} (open-source literature citation graph; non-commercial research)"
        if self.contact:
            ua += f" mailto:{self.contact}"
        self.s.headers["User-Agent"] = ua
        self.oc_token = os.environ.get("OPENCITATIONS_TOKEN", "").strip()
        self.openalex_key = os.environ.get("OPENALEX_API_KEY", "").strip()
        self.last: dict[str, float] = {}

    def get(self, url: str, headers: dict | None = None, tries: int = 4) -> requests.Response | None:
        host = url.split("/")[2]
        for attempt in range(tries):
            wait = self.MIN_INTERVAL.get(host, 0.3) - (time.monotonic() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.monotonic()
            self.budget.requests += 1
            try:
                r = self.s.get(url, headers=headers or {}, timeout=60)
            except requests.RequestException as e:
                log.warning("network error %s: %s", host, e)
                time.sleep(2 ** attempt * 2)
                continue
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            if r.status_code == 429:
                if host == "api.openalex.org" and _nonzero(r.headers.get("x-ratelimit-cost-required-usd")):
                    raise PaidCall("OpenAlex asks for budget on a single lookup: source suspended")
                ra = min(float(r.headers.get("retry-after", 10) or 10), 120)
                log.warning("429 from %s, waiting %.0fs", host, ra)
                time.sleep(ra)
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt * 3)
                continue
            raise SourceError(f"HTTP {r.status_code} from {url}")
        raise SourceError(f"too many failed attempts: {url}")

    def get_json(self, url: str, headers: dict | None = None):
        r = self.get(url, headers)
        if r is None:
            return None
        try:
            return r.json()
        except ValueError:
            raise SourceError(f"invalid JSON from {url}")


class PaidCall(SourceError):
    pass


def _nonzero(v) -> bool:
    try:
        return float(v or 0) > 0
    except ValueError:
        return False


def _doi_from_field(field: str) -> str | None:
    m = DOI_IN_FIELD.search(field or "")
    return m.group(1).lower().rstrip(".") if m else None


class Sources:
    def __init__(self, http: Http):
        self.http = http
        self.openalex_ok = True

    # ---------- graph ----------
    def references(self, doi: str) -> list[str]:
        """DOIs cited by `doi`. OpenCitations, falling back to references deposited in Crossref."""
        out = self._oc("references", doi, "cited")
        if out:
            return out
        m = self.http.get_json(f"https://api.crossref.org/works/{quote(doi)}")
        refs = ((m or {}).get("message") or {}).get("reference") or []
        return sorted({r["DOI"].lower() for r in refs if r.get("DOI")} - {doi})

    def citations(self, doi: str) -> list[str]:
        """DOIs citing `doi` (OpenCitations)."""
        return self._oc("citations", doi, "citing")

    def _oc(self, op: str, doi: str, key: str) -> list[str]:
        h = {"authorization": self.http.oc_token} if self.http.oc_token else None
        data = self.http.get_json(f"https://api.opencitations.net/index/v2/{op}/doi:{quote(doi)}", headers=h) or []
        out = {_doi_from_field(row.get(key, "")) for row in data}
        out.discard(None)
        out.discard(doi)
        return sorted(out)

    # ---------- metadata ----------
    def metadata(self, doi: str) -> dict | None:
        if self.openalex_ok:
            try:
                m = self._openalex(doi)
                if m:
                    return m
            except PaidCall as e:
                log.error("%s", e)
                self.openalex_ok = False
        return self._crossref(doi)

    def _openalex(self, doi: str) -> dict | None:
        fields = ("id,doi,title,publication_year,type,cited_by_count,is_retracted,open_access,"
                  "primary_location,authorships,abstract_inverted_index,primary_topic")
        url = f"https://api.openalex.org/works/doi:{quote(doi)}?select={fields}"
        if self.http.openalex_key:
            url += f"&api_key={quote(self.http.openalex_key)}"
        r = self.http.get(url)
        if r is None:
            return None
        if _nonzero(r.headers.get("x-ratelimit-cost-usd")):
            raise PaidCall("OpenAlex charged a single lookup: source suspended")
        w = r.json()
        abstract = ""
        ii = w.get("abstract_inverted_index") or {}
        if ii:
            pos = sorted((p, t) for t, ps in ii.items() for p in ps)
            abstract = " ".join(t for _, t in pos)
        src = ((w.get("primary_location") or {}).get("source") or {})
        topic = w.get("primary_topic") or {}
        oa = w.get("open_access") or {}
        return {
            "title": w.get("title") or "",
            "year": w.get("publication_year"),
            "type": w.get("type"),
            "venue": src.get("display_name") or "",
            "authors": [a["author"]["display_name"] for a in (w.get("authorships") or [])[:6] if a.get("author")],
            "cited_by": w.get("cited_by_count") or 0,
            "retracted": bool(w.get("is_retracted")),
            "abstract": abstract,
            "topic": topic.get("display_name") or "",
            "subfield": ((topic.get("subfield") or {}).get("display_name")) or "",
            "oa_url": oa.get("oa_url") or "",
            "openalex": (w.get("id") or "").rsplit("/", 1)[-1],
            "meta_src": "openalex",
        }

    def _crossref(self, doi: str) -> dict | None:
        m = self.http.get_json(f"https://api.crossref.org/works/{quote(doi)}")
        if not m:
            return None
        return crossref_record(m.get("message") or {})

    # ---------- seed search (Crossref, free and keyless) ----------
    def search(self, query: str, rows: int = 20, since: int | None = None, until: int | None = None) -> list[dict]:
        url = (f"https://api.crossref.org/works?query.bibliographic={quote(query)}&rows={min(rows, 100)}"
               "&select=DOI,title,author,issued,published,container-title,is-referenced-by-count,type")
        flt = []
        if since:
            flt.append(f"from-pub-date:{since}")
        if until:
            flt.append(f"until-pub-date:{until}")
        if flt:
            url += "&filter=" + ",".join(flt)
        if self.http.contact:
            url += f"&mailto={quote(self.http.contact)}"
        data = self.http.get_json(url) or {}
        out = []
        for it in (data.get("message") or {}).get("items") or []:
            rec = crossref_record(it)
            rec["doi"] = (it.get("DOI") or "").lower()
            out.append(rec)
        return out


def crossref_record(m: dict) -> dict:
    abstract = html.unescape(re.sub(r"<[^>]+>", " ", m.get("abstract") or ""))
    year = None
    for k in ("published", "published-print", "published-online", "issued"):
        dp = (m.get(k) or {}).get("date-parts") or [[None]]
        if dp and dp[0] and dp[0][0]:
            year = dp[0][0]
            break
    return {
        "title": html.unescape(" ".join(((m.get("title") or [""])[0] or "").split())),
        "year": year,
        "type": m.get("type"),
        "venue": html.unescape((m.get("container-title") or [""])[0] or ""),
        "authors": [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in (m.get("author") or [])[:6]],
        "cited_by": m.get("is-referenced-by-count") or 0,
        "retracted": False,
        "abstract": " ".join(abstract.split()),
        "topic": "",
        "subfield": "",
        "oa_url": "",
        "openalex": "",
        "meta_src": "crossref",
    }
