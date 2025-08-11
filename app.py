from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from urllib import robotparser
import requests
from urllib.parse import urlparse, urlunparse

app = FastAPI(title="AI Bot Block Checker", version="1.0.0")

# CORS is fine to leave open for now; this can be restricted later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DEFAULT_AI_BOTS = [
    "GPTBot",            # OpenAI
    "PerplexityBot",     # Perplexity
    "ClaudeBot",         # Anthropic (reported UA)
    "CCBot",             # CommonCrawl
    "Google-Extended",   # Google AI training opt-out
    "Amazonbot",         # Amazon
]

class BotResult(BaseModel):
    userAgent: str
    canFetchRoot: bool
    canFetchSitewide: bool  # Root-block treated as sitewide for simplicity
    notes: str | None = None

class CheckResponse(BaseModel):
    robotsTxtFound: bool
    robotsUrl: str
    statusCode: int | None
    blockedBots: List[str]
    results: List[BotResult]
    robotsTxt: str | None = None
    warnings: List[str] = []

def normalize_to_origin(url: str) -> str:
    """Return just the scheme + domain from any URL."""
    p = urlparse(url)
    scheme = p.scheme or "https"
    netloc = p.netloc or p.path  # allow 'example.com' input
    return urlunparse((scheme, netloc, "", "", "", ""))

@app.get("/check", response_model=CheckResponse)
def check_ai_bot_block(
    url: str = Query(..., description="Any URL on the target site; we'll normalize to its origin."),
    bots: List[str] = Query(DEFAULT_AI_BOTS, description="User agents to test."),
    includeRobotsTxt: bool = Query(True, description="Return raw robots.txt text.")
):
    origin = normalize_to_origin(url).rstrip("/")
    robots_url = f"{origin}/robots.txt"
    warnings: List[str] = []

    try:
        r = requests.get(robots_url, timeout=8, allow_redirects=True)
        status = r.status_code
    except requests.RequestException as e:
        return CheckResponse(
            robotsTxtFound=False,
            robotsUrl=robots_url,
            statusCode=None,
            blockedBots=[],
            results=[],
            robotsTxt=None,
            warnings=[f"Fetch error: {e.__class__.__name__}"]
        )

    if status != 200 or not r.text.strip():
        return CheckResponse(
            robotsTxtFound=False,
            robotsUrl=robots_url,
            statusCode=status,
            blockedBots=[],
            results=[],
            robotsTxt=None,
            warnings=warnings
        )

    txt = r.text
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.parse(txt.splitlines())
    except Exception as e:
        warnings.append(f"Parse warning: {e.__class__.__name__}")

    results: List[BotResult] = []
    blocked: List[str] = []

    for ua in bots:
        can_root = bool(rp.can_fetch(ua, origin + "/"))
        can_sitewide = can_root
        if not can_root:
            blocked.append(ua)
        results.append(BotResult(
            userAgent=ua,
            canFetchRoot=can_root,
            canFetchSitewide=can_sitewide,
            notes=None
        ))

    return CheckResponse(
        robotsTxtFound=True,
        robotsUrl=robots_url,
        statusCode=status,
        blockedBots=blocked,
        results=results,
        robotsTxt=txt if includeRobotsTxt else None,
        warnings=warnings
    )
