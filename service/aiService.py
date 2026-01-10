import os
from typing import Any, Dict
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI
from ddgs import DDGS
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import re

import requests

load_dotenv()


client = OpenAI()


AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
COMPANY_SEARCH_ENABLED = os.getenv("COMPANY_SEARCH_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
COMPANY_SEARCH_MAX_RESULTS = int(os.getenv("COMPANY_SEARCH_MAX_RESULTS", "6"))
COMPANY_SEARCH_TIMEOUT_SECONDS = float(os.getenv("COMPANY_SEARCH_TIMEOUT_SECONDS", "6"))
COMPANY_SEARCH_MAX_TOOL_CALLS = int(os.getenv("COMPANY_SEARCH_MAX_TOOL_CALLS", "2"))
AI_DEBUG = os.getenv("AI_DEBUG", "false").strip().lower() in {"1", "true", "yes", "y", "on"}

_company_search_cache: Dict[str, str] = {}


_PERSONAL_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "ukr.net",
    "i.ua",
}


def _company_candidate_from_sender_email(sender_email: str) -> str | None:
    if not sender_email or "@" not in sender_email:
        return None

    domain = sender_email.split("@", 1)[1].strip().lower()
    if not domain or domain in _PERSONAL_EMAIL_DOMAINS:
        return None

    # Get a best-effort "brand" from domain.
    # Examples:
    #   mail.softserve.com -> softserve
    #   nova-poshta.ua -> nova-poshta
    parts = [p for p in domain.split(".") if p]
    if len(parts) < 2:
        return None

    sld = parts[-2]
    if not sld or sld in {"mail", "smtp", "api", "app", "www"}:
        return None

    candidate = sld.replace("-", " ").strip()
    if not candidate:
        return None

    # Title-case words but keep it simple (LLM can normalize further).
    return " ".join([w[:1].upper() + w[1:] for w in candidate.split() if w]) or None


def search_company_tool(company_name: str) -> str:
    if not company_name:
        return "No company provided."

    cached = _company_search_cache.get(company_name)
    if cached is not None:
        return cached

    query_variants = [
        f'"{company_name}" company overview',
        f'"{company_name}" official website',
        f'"{company_name}" about us',
        f'"{company_name}" services',
    ]

    def _format_entry(index: int, title: str, snippet: str, url: str) -> str:
        domain = urlparse(url).netloc if url else ""
        header = f"{index}. {title or 'No title'}"
        if domain:
            header += f" ({domain})"
        details: list[str] = [header]
        if snippet:
            details.append(f"   Snippet: {snippet}")
        if url:
            details.append(f"   URL: {url}")
        return "\n".join(details)

    try:
        aggregated: list[dict] = []
        seen_keys: set[str] = set()

        def _search_once(query: str) -> list[dict]:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=COMPANY_SEARCH_MAX_RESULTS))

        with ThreadPoolExecutor(max_workers=1) as ex:
            for query in query_variants:
                fut = ex.submit(_search_once, query)
                results = fut.result(timeout=COMPANY_SEARCH_TIMEOUT_SECONDS)

                for result in results:
                    title = (result.get("title") or "").strip()
                    snippet = (result.get("body") or "").strip()
                    url = (result.get("href") or result.get("url") or "").strip()

                    if not title and not snippet and not url:
                        continue

                    dedupe_key = url or f"{title}|{snippet}"
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)

                    aggregated.append({
                        "title": title,
                        "snippet": snippet,
                        "url": url,
                    })

                    if len(aggregated) >= COMPANY_SEARCH_MAX_RESULTS:
                        break

                if len(aggregated) >= COMPANY_SEARCH_MAX_RESULTS:
                    break

        if not aggregated:
            out = "No info found online."
            _company_search_cache[company_name] = out
            return out

        context_lines = [
            _format_entry(idx, entry["title"], entry["snippet"], entry["url"])
            for idx, entry in enumerate(aggregated, start=1)
        ]
        context = "\n".join(context_lines)
        _company_search_cache[company_name] = context
        return context
    except TimeoutError:
        out = "Search timeout."
        _company_search_cache[company_name] = out
        return out
    except Exception as e:
        out = f"Error during search: {e}"
        _company_search_cache[company_name] = out
        return out


def fetch_website_tool(url: str) -> str:
    if not url:
        return "No website provided."

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GradientBot/1.0; +https://example.com)"
        }
        resp = requests.get(url, headers=headers, timeout=COMPANY_SEARCH_TIMEOUT_SECONDS)
        if resp.status_code >= 400:
            return f"Website request failed with status {resp.status_code}."

        html = resp.text or ""

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        desc = re.sub(r"\s+", " ", desc_match.group(1)).strip() if desc_match else ""

        og_desc_match = re.search(
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        og_desc = re.sub(r"\s+", " ", og_desc_match.group(1)).strip() if og_desc_match else ""

        summary_parts = []
        if title:
            summary_parts.append(f"Title: {title}")
        if desc:
            summary_parts.append(f"Meta description: {desc}")
        if og_desc and og_desc != desc:
            summary_parts.append(f"OG description: {og_desc}")

        return "\n".join(summary_parts) or "No usable metadata found on website."
    except Exception as e:
        return f"Error fetching website: {e}"


tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "search_company_tool",
            "description": "Use this if you found a company name in the email and need extra details (website, short overview).",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "Company name found in the email (e.g. 'SoftServe' or 'Nova Poshta').",
                    }
                },
                "required": ["company_name"],
            },
        },
    }
    ,
    {
        "type": "function",
        "function": {
            "name": "fetch_website_tool",
            "description": "Use this if the email contains a website URL. Fetch the website to extract title and meta description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "A website URL found in the email (e.g. 'https://thegradient.com').",
                    }
                },
                "required": ["url"],
            },
        },
    }
]


def _website_candidate_from_body(body: str) -> str | None:
    if not body:
        return None
    m = re.search(r"https?://[^\s)\]>\"']+", body, flags=re.IGNORECASE)
    return m.group(0) if m else None


def _normalize_website(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    # Best-effort normalize like "thegradient.com" -> "https://thegradient.com"
    return "https://" + u


def analyze_email(subject: str, body: str, sender: str) -> Dict[str, Any]:
    """Call OpenAI to extract structured fields from an email.

    Expected JSON schema in the response:
    {
        "email": string | null,
        "first_name": string | null,
        "last_name": string | null,
        "full_name": string | null,
        "company": string | null,
        "order_number": string | null,
        "order_description": string | null,
        
    }
    """

    system_prompt = (
        "You are an intelligent email parsing assistant. "
        "Your goal involves two steps: "
        "1) Extract structured data from the email. "
        "2) If you identify a company name, call the tool 'search_company_tool' to get extra company details. "
        "If no company name is explicitly present in the email text, you may infer a company from the sender email domain "
        "(but do not infer companies for personal email providers like gmail.com). "
        "Finally, return ONLY a valid JSON object with the exact keys: "
        "email, first_name, last_name, full_name, company, company_summary, "
        "order_number, order_description, amount, currency, "
        "phone_number, website. "
        "If some field is not present, set it to null. "
        "If amount is present, use a number (dot as decimal separator)."
    )

    company_candidate = _company_candidate_from_sender_email(sender)
    website_candidate = _website_candidate_from_body(body)

    if AI_DEBUG:
        # Avoid logging full PII content (body, full sender). Keep only high-level signal.
        sender_domain = sender.split("@", 1)[1] if sender and "@" in sender else None
        print(
            f"[AI] analyze_email model={AI_MODEL} search_enabled={COMPANY_SEARCH_ENABLED} "
            f"sender_domain={sender_domain} company_candidate={company_candidate} website_candidate={website_candidate}"
        )

    user_prompt = (
        "Extract data from the following email.\n\n"
        f"Sender email: {sender}\n"
        f"Sender domain company candidate (may be null): {company_candidate}\n"
        f"Website URL found in body (may be null): {website_candidate}\n"
        f"Subject: {subject}\n\n"
        "Body:\n" + body
    )

    # Step 1: Always do deterministic extraction to JSON first.
    base_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    base_response = client.chat.completions.create(
        model=AI_MODEL,
        messages=base_messages,
        response_format={"type": "json_object"},
    )

    base_content = base_response.choices[0].message.content
    try:
        base_data = json.loads(base_content)
    except json.JSONDecodeError:
        base_data = {}

    # Step 2: Always enrich ("search always") if enabled.
    enrichment_parts: list[str] = []
    if COMPANY_SEARCH_ENABLED:
        company_for_search = base_data.get("company") or company_candidate
        website_for_fetch = _normalize_website(base_data.get("website") or website_candidate)

        if website_for_fetch:
            enrichment_parts.append("[WEBSITE]\n" + fetch_website_tool(website_for_fetch))

        if company_for_search and len(enrichment_parts) < max(COMPANY_SEARCH_MAX_TOOL_CALLS, 0):
            enrichment_parts.append("[DDG_SEARCH]\n" + search_company_tool(company_for_search))

    enrichment_context = "\n\n".join(enrichment_parts) if enrichment_parts else ""

    # Step 3: Final JSON generation using extracted + enriched context.
    final_system_prompt = (
        system_prompt
        + " Use the enrichment context (if provided) to populate company_summary and website accurately."
    )

    final_user_prompt = (
        "Here is the extracted JSON (may contain nulls):\n"
        + json.dumps(base_data, ensure_ascii=False)
        + "\n\nEnrichment context (may be empty):\n"
        + (enrichment_context or "<empty>")
        + "\n\nNow output only the final JSON object with the required keys."
    )

    final_response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": final_user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    content = final_response.choices[0].message.content

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {}

    # Ensure all expected keys exist
    result: Dict[str, Any] = {
        "email": data.get("email"),
        "first_name": data.get("first_name"),
        "last_name": data.get("last_name"),
        "full_name": data.get("full_name"),
        "company": data.get("company"),
        "company_summary": data.get("company_summary"),
        "order_number": data.get("order_number"),
        "order_description": data.get("order_description"),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
        "phone_number": data.get("phone_number"),
        "website": data.get("website"),
    }

    return result
