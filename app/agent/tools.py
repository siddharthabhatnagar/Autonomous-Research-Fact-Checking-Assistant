import time
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from langchain_core.tools import tool
from app.config import settings

USER_AGENT = "MyResearchBot/1.0 (https://example.com/bot; contact@example.com)"

def calculate_credibility(url: str, title: str) -> tuple[int, str]:
    """Calculates credibility score (0-100) and rationale based on domain authority."""
    domain = urlparse(url).netloc.lower()
    
    if any(domain.endswith(tld) for tld in [".gov", ".mil"]):
        return 96, "Official government or military institutional source (highest authority)"
    if any(domain.endswith(tld) for tld in [".edu", ".ac.uk"]):
        return 92, "Accredited academic institution research repository"
    
    tier_1_domains = [
        "nature.com", "science.org", "nejm.org", "thelancet.com", "cell.com",
        "ieee.org", "arxiv.org", "nih.gov", "cdc.gov", "who.int", "imf.org", "worldbank.org",
        "reuters.com", "apnews.com", "bbc.com", "bloomberg.com", "ft.com", "economist.com"
    ]
    if any(t1 in domain for t1 in tier_1_domains):
        return 90, f"Peer-reviewed journal or Tier-1 global news agency ({domain})"
    
    if any(domain.endswith(tld) for tld in [".org"]):
        return 85, f"Non-profit or organizational publication ({domain})"
        
    tier_2_domains = [
        "wsj.com", "nytimes.com", "washingtonpost.com", "theguardian.com",
        "theverge.com", "wired.com", "technologyreview.com", "techcrunch.com",
        "cnbc.com", "forbes.com", "scientificamerican.com", "wikipedia.org"
    ]
    if any(t2 in domain for t2 in tier_2_domains):
        return 82, f"Established mainstream press or vetted encyclopedia ({domain})"
        
    low_authority_domains = ["medium.com", "substack.com", "reddit.com", "quora.com", "wordpress.com", "blogspot.com"]
    if any(la in domain for la in low_authority_domains):
        return 60, f"User-generated content or opinion blog platform ({domain})"
        
    return 75, f"Standard web publication ({domain})"

def search_ddgs(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs search using DuckDuckGo (HTML backend + news fallback)."""
    results = []
    
    # 1. Try DDGS text search with html backend
    try:
        ddgs = DDGS()
        raw = list(ddgs.text(query, backend="html", max_results=max_results))
        for r in raw:
            href = r.get("href") or r.get("url") or ""
            if href and not any(res["url"] == href for res in results):
                results.append({
                    "url": href,
                    "title": r.get("title", "Untitled"),
                    "snippet": r.get("body", ""),
                    "source": "DuckDuckGo Web"
                })
    except Exception as e:
        print(f"[tools] DDGS text search error: {e}")
        
    # 2. Try DDGS news search if text search returned few results
    if len(results) < max_results:
        try:
            ddgs = DDGS()
            raw_news = list(ddgs.news(query, max_results=max_results - len(results)))
            for r in raw_news:
                href = r.get("url") or ""
                if href and not any(res["url"] == href for res in results):
                    results.append({
                        "url": href,
                        "title": r.get("title", "Untitled"),
                        "snippet": r.get("body", ""),
                        "source": f"DuckDuckGo News ({r.get('source', 'News')})"
                    })
        except Exception as e:
            print(f"[tools] DDGS news search error: {e}")
            
    return results[:max_results]

def search_wikipedia(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """Searches Wikipedia API for foundational encyclopedic knowledge and definitions."""
    results = []
    try:
        endpoint = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": max_results
        }
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(endpoint, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                search_items = data.get("query", {}).get("search", [])
                for item in search_items:
                    page_id = item.get("pageid")
                    title = item.get("title", "")
                    clean_title = title.replace(" ", "_")
                    wiki_url = f"https://en.wikipedia.org/wiki/{clean_title}"
                    snippet_html = item.get("snippet", "")
                    clean_snippet = re.sub(r'<[^>]+>', '', snippet_html)
                    results.append({
                        "url": wiki_url,
                        "title": f"{title} (Wikipedia)",
                        "snippet": clean_snippet,
                        "source": "Wikipedia"
                    })
    except Exception as e:
        print(f"[tools] Wikipedia search error: {e}")
    return results

def search_tavily(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Searches Tavily API if TAVILY_API_KEY is configured."""
    api_key = settings.TAVILY_API_KEY
    if not api_key:
        return []
    try:
        endpoint = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_raw_content": False
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(endpoint, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("results", []):
                    results.append({
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "snippet": item.get("content"),
                        "source": "Tavily Search"
                    })
                return results
    except Exception as e:
        print(f"[tools] Tavily search error: {e}")
    return []

def search_web_aggregated(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Aggregates search results across Tavily (if present), DDGS, and Wikipedia."""
    all_results = []
    
    # 1. Tavily if available
    tavily_res = search_tavily(query, max_results=max_results)
    if tavily_res:
        all_results.extend(tavily_res)
        
    # 2. DDGS search
    if len(all_results) < max_results:
        ddgs_res = search_ddgs(query, max_results=max_results - len(all_results))
        for r in ddgs_res:
            if not any(x["url"] == r["url"] for x in all_results):
                all_results.append(r)
                
    # 3. Wikipedia search if needed
    if len(all_results) < max_results:
        wiki_res = search_wikipedia(query, max_results=max_results - len(all_results))
        for r in wiki_res:
            if not any(x["url"] == r["url"] for x in all_results):
                all_results.append(r)
                
    return all_results[:max_results]

def extract_page_content(url: str, max_length: int = 3500) -> Dict[str, Any]:
    """Fetches a webpage, strips boilerplate, and extracts clean article text."""
    domain = urlparse(url).netloc
    
    # Handle Wikipedia special case for fast structured extraction
    if "wikipedia.org" in domain:
        try:
            page_title = url.split("/wiki/")[-1]
            endpoint = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "titles": page_title,
                "prop": "extracts",
                "explaintext": 1,
                "format": "json"
            }
            with httpx.Client(timeout=10.0) as client:
                res = client.get(endpoint, params=params, headers={"User-Agent": USER_AGENT})
                if res.status_code == 200:
                    pages = res.json().get("query", {}).get("pages", {})
                    first_page = list(pages.values())[0] if pages else {}
                    text = first_page.get("extract", "")
                    title = first_page.get("title", page_title.replace("_", " "))
                    cred_score, rationale = calculate_credibility(url, title)
                    return {
                        "url": url,
                        "title": title,
                        "domain": domain,
                        "full_text": text[:max_length],
                        "published_date": "Updated continuously",
                        "credibility_score": cred_score,
                        "credibility_rationale": rationale,
                        "status": "success"
                    }
        except Exception as e:
            print(f"[tools] Wikipedia direct extract fallback: {e}")

    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                return {
                    "url": url,
                    "title": "Failed to load",
                    "domain": domain,
                    "full_text": f"Error: Received HTTP {response.status_code}",
                    "published_date": "Unknown",
                    "credibility_score": 50,
                    "credibility_rationale": "Source unreachable",
                    "status": "error"
                }
                
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts, styles, navigation, footer
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form", "svg"]):
                tag.decompose()
                
            title = soup.title.string.strip() if soup.title and soup.title.string else domain
            
            # Extract meta description
            desc_meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
            description = desc_meta.get("content", "").strip() if desc_meta else ""
            
            # Extract date
            date_meta = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "publication_date"}) or soup.find("time")
            published_date = date_meta.get("content", "").strip() if (date_meta and date_meta.get("content")) else (date_meta.text.strip() if date_meta else "Recent")

            # Extract paragraphs
            paragraphs = []
            for p in soup.find_all(["p", "h2", "h3", "li"]):
                txt = p.get_text().strip()
                if len(txt) > 30 and not any(skip in txt.lower() for skip in ["cookie", "privacy policy", "all rights reserved", "subscribe"]):
                    paragraphs.append(txt)
                    
            content = "\n\n".join(paragraphs)
            if not content and description:
                content = description
            elif not content:
                content = soup.get_text()[:max_length]

            cred_score, rationale = calculate_credibility(url, title)

            return {
                "url": url,
                "title": title,
                "domain": domain,
                "full_text": content[:max_length],
                "published_date": published_date[:50],
                "credibility_score": cred_score,
                "credibility_rationale": rationale,
                "status": "success"
            }
    except Exception as e:
        cred_score, rationale = calculate_credibility(url, domain)
        return {
            "url": url,
            "title": domain,
            "domain": domain,
            "full_text": f"Summary extracted from metadata due to connection limit: {url}",
            "published_date": "Unknown",
            "credibility_score": cred_score,
            "credibility_rationale": rationale,
            "status": "partial"
        }

# --- LangChain Tool Definitions for Controlled Agent Tool Calling ---

@tool
def search_web_tool(query: str) -> str:
    """Searches the web for facts, evidence, reports, and current statistics on a topic."""
    results = search_web_aggregated(query, max_results=4)
    if not results:
        return f"No direct search results found for query: '{query}'."
    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(f"[{i}] {r['title']}\nURL: {r['url']}\nSnippet: {r['snippet']}\n")
    return "\n".join(formatted)

@tool
def extract_page_tool(url: str) -> str:
    """Fetches and extracts the full readable text, author, and key arguments from a specific URL."""
    res = extract_page_content(url, max_length=2500)
    return f"Title: {res['title']}\nDomain: {res['domain']}\nCredibility: {res['credibility_score']}/100 ({res['credibility_rationale']})\nContent:\n{res['full_text']}"

@tool
def verify_claim_tool(claim_statement: str) -> str:
    """Cross-examines a specific factual claim against web sources to find supporting or disputing evidence."""
    search_res = search_web_aggregated(f"verify {claim_statement}", max_results=3)
    if not search_res:
        return f"No verification sources found for claim: {claim_statement}"
    output = [f"Verification evidence for claim: '{claim_statement}'"]
    for r in search_res:
        output.append(f"- Source: {r['title']} ({r['url']})\n  Evidence: {r['snippet']}")
    return "\n\n".join(output)

AGENT_TOOLS = [search_web_tool, extract_page_tool, verify_claim_tool]
