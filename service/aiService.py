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

from service.settingsService import get_reply_prompts

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
PERSON_SEARCH_MAX_RESULTS = int(os.getenv("PERSON_SEARCH_MAX_RESULTS", "4"))
AI_DEBUG = os.getenv("AI_DEBUG", "false").strip().lower() in {"1", "true", "yes", "y", "on"}

_company_search_cache: Dict[str, str] = {}
_company_search_struct_cache: Dict[str, list[dict[str, str]]] = {}
_person_search_cache: Dict[str, list[dict[str, str]]] = {}

MAX_REPLY_WORDS = 140
REPLY_VARIANTS = ("follow_up", "recap")


def _to_serializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_serializable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_serializable(item) for item in value]
    if isinstance(value, (str, int, float)) or value is None:
        return value
    if isinstance(value, bool):
        return value
    return str(value)


def _pretty_json(data: dict | list | None) -> str:
    if not data:
        return "{}"
    try:
        return json.dumps(_to_serializable(data), ensure_ascii=False, indent=2)
    except Exception:
        return json.dumps({}, indent=2)


def _enforce_word_limit(text: str, max_words: int = MAX_REPLY_WORDS) -> str:
    words = re.findall(r"\S+", text)
    if len(words) <= max_words:
        return text.strip()
    trimmed = " ".join(words[:max_words]).strip()
    if not trimmed.endswith((".", "!", "?")):
        trimmed += "..."
    return trimmed


def _normalize_placeholder_key(key: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", key.upper()).strip("_")


def _flatten_for_placeholders(prefix: str, value: Any) -> dict[str, str]:
    items: dict[str, str] = {}
    if value is None:
        return items
    if isinstance(value, dict):
        for sub_key, sub_val in value.items():
            combined = f"{prefix}_{sub_key}" if prefix else str(sub_key)
            items.update(_flatten_for_placeholders(combined, sub_val))
        return items
    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            for idx, item in enumerate(value, start=1):
                combined = f"{prefix}_{idx}" if prefix else str(idx)
                items.update(_flatten_for_placeholders(combined, item))
        else:
            items[prefix] = ", ".join(str(item) for item in value if str(item).strip())
        return items

    if prefix:
        items[prefix] = str(value)
    return items


def _collect_placeholder_mapping(
    lead: dict[str, Any] | None,
    email: dict[str, Any] | None,
    placeholders: dict[str, Any] | None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}

    def register(key: str, value: Any) -> None:
        if value is None:
            return
        norm = _normalize_placeholder_key(key)
        if not norm:
            return
        text = str(value).strip()
        if not text:
            return
        mapping.setdefault(norm, text)

    for source in (placeholders or {}).items():
        key, value = source
        register(str(key), value)

    for key, value in (email or {}).items():
        register(f"email_{key}", value)

    for key, value in (lead or {}).items():
        register(f"lead_{key}", value)

    for key, value in _flatten_for_placeholders("lead", lead or {}).items():
        register(key, value)

    for key, value in _flatten_for_placeholders("email", email or {}).items():
        register(key, value)

    full_name = (lead or {}).get("full_name") or "".join(
        filter(None, [
            (lead or {}).get("first_name"),
            (lead or {}).get("last_name"),
        ])
    )
    if full_name:
        register("name", full_name)
        register("client_name", full_name)

    subject = (email or {}).get("subject")
    if subject:
        register("subject", subject)
        register("topic_discussed", subject)

    return mapping


def _render_prompt(template: str, mapping: dict[str, str]) -> str:
    if not template:
        return ""

    pattern = re.compile(r"\[([^\[\]]+)\]")

    def replacer(match: re.Match[str]) -> str:
        raw_key = match.group(1)
        norm_key = _normalize_placeholder_key(raw_key)
        replacement = mapping.get(norm_key)
        return replacement if replacement is not None else match.group(0)

    return pattern.sub(replacer, template).strip()


def _compose_reply_context(
    lead: dict[str, Any] | None,
    email: dict[str, Any] | None,
    placeholders: dict[str, Any] | None,
) -> str:
    sections: list[str] = []
    email_section = _pretty_json(email or {})
    lead_section = _pretty_json(lead or {})
    sections.append(f"EMAIL CONTEXT:\n{email_section}")
    sections.append(f"LEAD DATA:\n{lead_section}")
    if placeholders:
        sections.append(f"ADDITIONAL PLACEHOLDERS:\n{_pretty_json(placeholders)}")
    return "\n\n".join(sections)


def _build_reply_messages(rendered_prompt: str, context: str) -> list[dict[str, str]]:
    system_prompt = (
        "You are an experienced sales development representative drafting concise email replies. "
        "Always respond in English. Limit the reply to 140 words. Use only factual information provided in the context. "
        "Do not invent names, dates, or commitments beyond what the context states."
    )

    user_prompt = (
        "Follow this reply blueprint and fill placeholders with the factual details from the context.\n\n"
        f"Reply blueprint:\n{rendered_prompt or '<no prompt provided>'}\n\n"
        f"Context with factual data:\n{context or '<empty>'}\n\n"
        "Output only the email body, without subject lines, notes, or extra commentary."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_email_replies(
    *,
    lead: dict[str, Any] | None,
    email: dict[str, Any] | None,
    placeholders: dict[str, Any] | None = None,
    prompt_overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    stored_prompts = get_reply_prompts()
    prompts: dict[str, str] = {
        variant: (stored_prompts.get(variant) or "")
        for variant in REPLY_VARIANTS
    }

    if prompt_overrides:
        for key, value in prompt_overrides.items():
            if key in prompts and isinstance(value, str) and value.strip():
                prompts[key] = value

    mapping = _collect_placeholder_mapping(lead, email, placeholders)
    context = _compose_reply_context(lead, email, placeholders)

    replies: dict[str, str] = {}
    for variant in REPLY_VARIANTS:
        template = prompts.get(variant, "")
        rendered_prompt = _render_prompt(template, mapping)

        if not rendered_prompt:
            replies[variant] = ""
            continue

        messages = _build_reply_messages(rendered_prompt, context)

        try:
            completion = client.chat.completions.create(
                model=AI_MODEL,
                messages=messages,
                temperature=0.35,
            )
            choice = completion.choices[0] if completion.choices else None
            content = choice.message.content if choice and choice.message else ""
        except Exception as exc:  # pragma: no cover
            if AI_DEBUG:
                print(f"[AI] generate_email_replies error for {variant}: {exc}")
            content = ""

        replies[variant] = _enforce_word_limit(content or "")

    return replies


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
            _company_search_struct_cache[company_name] = []
            return out

        context_lines = [
            _format_entry(idx, entry["title"], entry["snippet"], entry["url"])
            for idx, entry in enumerate(aggregated, start=1)
        ]
        context = "\n".join(context_lines)
        _company_search_cache[company_name] = context
        _company_search_struct_cache[company_name] = aggregated
        return context
    except TimeoutError:
        out = "Search timeout."
        _company_search_cache[company_name] = out
        return out
    except Exception as e:
        out = f"Error during search: {e}"
        _company_search_cache[company_name] = out
        return out


def search_person_insights(full_name: str, company_hint: str | None = None) -> list[dict[str, str]]:
    """Search for person insights using DuckDuckGo to infer role and social links."""

    if not full_name:
        return []

    cache_key = f"{full_name}|{company_hint or ''}"
    if cache_key in _person_search_cache:
        return _person_search_cache[cache_key]

    query = full_name
    if company_hint:
        query = f"{full_name} {company_hint}"

    results: list[dict[str, str]] = []

    try:
        with DDGS() as ddgs:
            matches = ddgs.text(query, max_results=PERSON_SEARCH_MAX_RESULTS)

        for match in matches:
            title = (match.get("title") or "").strip()
            snippet = (match.get("body") or "").strip()
            url = (match.get("href") or match.get("url") or "").strip()

            if not any([title, snippet, url]):
                continue

            results.append({
                "title": title,
                "snippet": snippet,
                "url": url,
            })

            if len(results) >= PERSON_SEARCH_MAX_RESULTS:
                break
    except Exception as exc:  # pragma: no cover - network errors tolerated
        if AI_DEBUG:
            print(f"[AI] person search failed: {exc}")

    _person_search_cache[cache_key] = results
    return results


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
        "phone_number, website, person_role, person_location, person_experience, person_links, person_summary. "
        "If some field is not present, set it to null. "
        "If amount is present, use a number (dot as decimal separator)."
    )

    company_candidate = _company_candidate_from_sender_email(sender)
    website_candidate = _website_candidate_from_body(body)
    company_for_search: str | None = None
    company_insights_struct: list[dict[str, str]] = []

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
    person_enrichment: list[dict[str, str]] = []
    if COMPANY_SEARCH_ENABLED:
        company_for_search = base_data.get("company") or company_candidate
        website_for_fetch = _normalize_website(base_data.get("website") or website_candidate)

        if website_for_fetch:
            enrichment_parts.append("[WEBSITE]\n" + fetch_website_tool(website_for_fetch))

        if company_for_search and len(enrichment_parts) < max(COMPANY_SEARCH_MAX_TOOL_CALLS, 0):
            enrichment_parts.append("[DDG_SEARCH]\n" + search_company_tool(company_for_search))
            company_insights_struct = _company_search_struct_cache.get(company_for_search, [])

        person_name = base_data.get("full_name") or base_data.get("first_name")
        if person_name:
            person_enrichment = search_person_insights(person_name, company_for_search)
            if person_enrichment:
                formatted = "\n".join(
                    f"{idx}. {item.get('title', 'Без заголовку')}\n   {item.get('snippet', '')}\n   {item.get('url', '')}"
                    for idx, item in enumerate(person_enrichment, start=1)
                )
                enrichment_parts.append("[PERSON_SEARCH]\n" + formatted)

    enrichment_context = "\n\n".join(enrichment_parts) if enrichment_parts else ""

    # Step 3: Final JSON generation using extracted + enriched context.
    final_system_prompt = (
        system_prompt
        + " Use the enrichment context (if provided) to populate company_summary and website accurately."
        + " If person search results are provided, populate role, experience level, social links when possible."
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

    final_content = final_response.choices[0].message.content
    try:
        data = json.loads(final_content)
    except json.JSONDecodeError:
        data = {}

    person_links = data.get("person_links") or []
    if isinstance(person_links, str):
        person_links = [person_links]

    if not isinstance(person_links, list):
        person_links = []

    person_summary = data.get("person_summary")
    if not person_summary:
        summary_parts: list[str] = []
        role = data.get("person_role")
        if role:
            summary_parts.append(f"Роль: {role}")
        location = data.get("person_location")
        if location:
            summary_parts.append(f"Локація: {location}")
        experience = data.get("person_experience")
        if experience:
            summary_parts.append(f"Досвід: {experience}")
        if person_enrichment:
            first_snippet = next((item.get("snippet") for item in person_enrichment if item.get("snippet")), None)
            if first_snippet:
                summary_parts.append(first_snippet)
        person_summary = " | ".join(summary_parts) if summary_parts else None

    result = {
        "email": data.get("email") or sender,
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
        "person_insights": person_enrichment,
        "person_role": data.get("person_role"),
        "person_location": data.get("person_location"),
        "person_experience": data.get("person_experience"),
        "person_links": person_links,
        "company_insights": company_insights_struct,
        "person_summary": person_summary,
    }

    return result
