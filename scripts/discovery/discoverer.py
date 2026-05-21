"""
Weekly job: discovers new companies via an LLM + search provider fallbacks,
validates their career pages exist, and adds them to search_config.yml regions.
Deduplicates against existing entries automatically.
"""

import os
import re
import json
import yaml

from core.config import ROOT as REPO_ROOT
from core.llm_client import get_llm_client
from core.llm_utils import get_llm_role_settings
from sources.search_providers import search_career_urls, search_web

# scripts/discovery/ → scripts/ → repo root
ROOT = str(REPO_ROOT)
SEARCH_CONFIG_FILE = os.path.join(ROOT, "config", "search_config.yml")

# ATS URL patterns and the canonical career_url format to store in search_config.yml.
# Order matters: more specific patterns first.
ATS_PATTERNS = [
    (r"boards\.greenhouse\.io/([^/?#\s]+)",       "boards.greenhouse.io/{slug}"),
    (r"job-boards\.greenhouse\.io/([^/?#\s]+)",   "job-boards.greenhouse.io/{slug}"),
    (r"jobs\.lever\.co/([^/?#\s]+)",              "jobs.lever.co/{slug}"),
    (r"apply\.workable\.com/([^/?#\s]+)",         "apply.workable.com/{slug}"),
    (r"jobs\.ashbyhq\.com/([^/?#\s]+)",           "jobs.ashbyhq.com/{slug}"),
    (r"jobs\.smartrecruiters\.com/([^/?#\s]+)",   "jobs.smartrecruiters.com/{slug}"),
    # Subdomain-based ATS: slug is the company subdomain
    (r"([^./]+)\.careers\.hibob\.com",            "{slug}.careers.hibob.com"),
    (r"([^./]+)\.jobs\.personio\.de",             "{slug}.jobs.personio.de"),
    (r"([^./]+)\.recruitee\.com",                 "{slug}.recruitee.com"),
    # jobs.personio.com uses path-based slugs
    (r"jobs\.personio\.com/([^/?#\s]+)",          "jobs.personio.com/{slug}"),
]

CAREER_PATH_PATTERNS = ["/careers", "/jobs", "/work-with-us", "/join-us"]

# One prompt per sector — run independently so every vertical gets proper coverage.
# Now parameterized by location.
SECTOR_PROMPTS_TEMPLATE = [
    {
        "sector": "automotive & mobility",
        "prompt": (
            "List 10 companies based in {location} (or with a significant {location} office) "
            "in automotive tech, connected vehicles, EV charging, fleet management, "
            "ride-hailing software, or urban mobility platforms. Requirements:\n"
            "- English as primary working language\n"
            "- Known to hire these roles: {job_titles}\n"
            "- NOT defence, military, weapons, banking, or gambling companies\n"
            "- NOT already in this list: {existing}\n\n"
            "Return ONLY a valid JSON array of company name strings. "
            "No explanation, no markdown, no code fences.\n"
            'Example: ["Volkswagen Digital Solutions", "Volocopter", "Lilium", "Sono Motors"]'
        ),
    },
    {
        "sector": "commercial aviation & travel tech",
        "prompt": (
            "List 10 companies based in {location} (or with a significant {location} office) "
            "in commercial airline software, airport systems, aviation operations tech, "
            "travel booking platforms, or tourism tech. Requirements:\n"
            "- English as primary working language\n"
            "- Known to hire these roles: {job_titles}\n"
            "- Civil/commercial aviation ONLY — NO defence, military, or weapons companies\n"
            "- NOT already in this list: {existing}\n\n"
            "Return ONLY a valid JSON array of company name strings. "
            "No explanation, no markdown, no code fences.\n"
            'Example: ["Lufthansa Systems", "Hahn Air", "Amadeus", "TUI Group"]'
        ),
    },
    {
        "sector": "industrial & enterprise tech",
        "prompt": (
            "List 10 companies based in {location} (or with a significant {location} office) "
            "in industrial automation, manufacturing software, Industry 4.0, IIoT platforms, "
            "enterprise SaaS, B2B analytics, or supply-chain tech. "
            "Large corporates with {location} offices (e.g. Siemens, Bosch) are welcome. Requirements:\n"
            "- English as primary working language\n"
            "- Known to hire these roles: {job_titles}\n"
            "- NOT defence, military, weapons, banking, or gambling companies\n"
            "- NOT already in this list: {existing}\n\n"
            "Return ONLY a valid JSON array of company name strings. "
            "No explanation, no markdown, no code fences.\n"
            'Example: ["Siemens", "Bosch", "Celonis", "Software AG", "Enpal"]'
        ),
    },
    {
        "sector": " {location} tech startups & scale-ups",
        "prompt": (
            "List 10 {location}-based tech startups or scale-ups (ideally Series A–D, founded after 2010) "
            "in any sector EXCEPT banking/crypto-lending, gambling, defence, military, or weapons. "
            "Sectors of particular interest: fintech (non-bank), health tech, climate tech, "
            "logistics, marketplace, developer tools, SaaS. Requirements:\n"
            "- English as primary working language\n"
            "- Known to hire these roles: {job_titles}\n"
            "- NOT already in this list: {existing}\n\n"
            "Return ONLY a valid JSON array of company name strings. "
            "No explanation, no markdown, no code fences.\n"
            'Example: ["Forto", "Moss", "Taxfix", "Pitch", "Hygraph"]'
        ),
    },
]


def get_sector_prompts(location: str, job_titles: list[str]) -> list[dict]:
    """Generate sector prompts for a specific location."""
    title_text = ", ".join(job_titles)
    return [
        {
            "sector": spec["sector"].format(location=location),
            "prompt": spec["prompt"].format(
                location=location,
                job_titles=title_text,
                existing="{existing}",
            )
        }
        for spec in SECTOR_PROMPTS_TEMPLATE
    ]


def load_companies() -> tuple[list[dict], set[str]]:
    with open(SEARCH_CONFIG_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    companies = []
    excluded = {e.lower() for e in data.get("excluded_companies", [])}

    # Collect all companies from all regions for deduplication purposes
    seen = set()
    for region in data.get("regions", {}).values():
        for c in region.get("companies", []):
            key = (c["name"].lower(), c["career_url"].lower())
            if key not in seen:
                seen.add(key)
                companies.append({"name": c["name"], "career_url": c["career_url"]})

    return companies, excluded


def has_jobs_in_location(company_name: str, region_config: dict) -> bool:
    """Check if a company has job postings in a specific location."""
    location = region_config.get("location", "")
    job_titles = region_config.get("job_titles", [])
    title_query = " OR ".join(f'"{title}"' for title in job_titles)
    query = f'"{company_name}" "{location}" {title_query} site:jobs OR site:careers'
    try:
        results = search_web(query, region_config, count=3)
        for result in results:
            url = result.get("url", "").lower()
            if company_name.lower() in url and (location.lower() in url or 'jobs' in url or 'careers' in url):
                return True
    except Exception as e:
        print(f"  [check] Error checking {company_name} in {location}: {e}")
    return False


def add_company_to_region(search_config: dict, region_name: str, company: dict):
    """Add a company to a region if not already present."""
    if region_name not in search_config.get("regions", {}):
        return
    region = search_config["regions"][region_name]
    companies = region.get("companies", [])
    if not any(c["name"].lower() == company["name"].lower() for c in companies):
        companies.append({"name": company["name"], "career_url": company["career_url"]})
        region["companies"] = companies
        print(f"  [auto-add] Added {company['name']} to region {region_name}")


def save_search_config(search_config: dict):
    """Save the updated search_config.yml."""
    with open(SEARCH_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(search_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_existing_names(companies: list[dict]) -> set[str]:
    return {c["name"].lower() for c in companies}


def get_existing_urls(companies: list[dict]) -> set[str]:
    return {c["career_url"].lower() for c in companies}


def discover_company_names(existing: list[dict], location: str, job_titles: list[str]) -> list[str]:
    """Run one LLM query per sector and combine the results."""
    existing_names = ", ".join(c["name"] for c in existing[:60])
    seen: set[str] = set()
    all_names: list[str] = []

    sector_prompts = get_sector_prompts(location, job_titles)

    for spec in sector_prompts:
        prompt = spec["prompt"].format(existing=existing_names)
        print(f"[discover] Querying sector: {spec['sector']}...")
        try:
            settings = get_llm_role_settings("discovery")
            raw = get_llm_client("discovery").complete(
                user=prompt,
                model=settings.model,
                max_tokens=settings.max_tokens,
            )
            names = json.loads(raw)
            added = 0
            for name in names:
                if isinstance(name, str) and name.lower() not in seen:
                    seen.add(name.lower())
                    all_names.append(name)
                    added += 1
            print(f"  → {added} new suggestions")
        except Exception as e:
            print(f"  [discover] Sector '{spec['sector']}' failed: {e}")

    return all_names


def brave_search(query: str, count: int = 5, region_config: dict | None = None) -> list[dict]:
    """Compatibility wrapper; now uses the full search provider chain."""
    return search_web(region_config=region_config or {}, query=query, count=count)


def find_career_url(company_name: str, existing_urls: set[str], region_config: dict) -> dict | None:
    """
    Search provider fallbacks for the company's career page.

    Two passes:
      1. ATS-targeted query across all supported platforms.
      2. Broad career/jobs query for companies on custom domains.

    Returns a dict with name + career_url if found, None otherwise.
    """
    location = region_config.get("location", "")
    try:
        results = search_career_urls(company_name, region_config, count=7)
    except Exception as e:
        print(f"  [search] Error searching for {company_name}: {e}")
        results = []

    for result in results:
        url = result.get("url", "")

        for pattern, template in ATS_PATTERNS:
            match = re.search(pattern, url)
            if match:
                slug = match.group(1).rstrip("/")
                career_url = template.format(slug=slug)
                if career_url.lower() not in existing_urls:
                    print(f"  [found] {company_name} -> {career_url} (ATS)")
                    return {"name": company_name, "career_url": career_url}

        for path in CAREER_PATH_PATTERNS:
            if path in url.lower():
                domain_match = re.match(r"https?://([^/]+)", url)
                if domain_match:
                    domain = domain_match.group(1)
                    career_url = f"{domain}{path}"
                    if career_url.lower() not in existing_urls:
                        print(f"  [found] {company_name} -> {career_url} (direct)")
                        return {"name": company_name, "career_url": career_url}

    print(f"  [miss] No career page found for {company_name}")
    return None


def run():
    print("\n" + "="*50)
    print("Weekly Company Discovery")
    print("="*50 + "\n")

    existing, excluded = load_companies()
    existing_names = get_existing_names(existing)
    existing_urls = get_existing_urls(existing)
    print(f"[discover] Currently tracking {len(existing)} companies")
    print(f"[discover] Excluding {len(excluded)} companies: {sorted(excluded)}")

    # Load search_config for region info and potential updates
    search_config = {}
    if os.path.exists(SEARCH_CONFIG_FILE):
        with open(SEARCH_CONFIG_FILE, encoding="utf-8") as f:
            search_config = yaml.safe_load(f) or {}

    regions = {k: v for k, v in search_config.get("regions", {}).items() if v.get("enabled", True)}
    job_titles = search_config.get("global_search", {}).get("job_titles", [])

    if not regions:
        print("[discover] No enabled regions found in search_config.yml. Nothing to discover.")
        return
    if not job_titles:
        print("[discover] global_search.job_titles is empty. Nothing to discover.")
        return

    for region_config in regions.values():
        region_config["job_titles"] = job_titles

    region_discoveries = {}  # Track which region discovered which companies

    for region_name, region_config in regions.items():
        location = region_config.get("location", region_name.title())
        print(f"\n[discover] Discovering companies for region: {region_name} ({location})")

        sectors = ", ".join(s["sector"] for s in get_sector_prompts(location, job_titles))
        print(f"[discover] Querying LLM across sectors: {sectors}")
        suggested = discover_company_names(existing, location, job_titles)
        print(f"[discover] LLM suggested {len(suggested)} companies: {suggested}\n")

        new_names = [
            name for name in suggested
            if name.lower() not in existing_names
            and name.lower() not in excluded
        ]

        skipped_excluded = [name for name in suggested if name.lower() in excluded]
        if skipped_excluded:
            print(f"[discover] Excluded by exclusion list: {skipped_excluded}")

        print(f"[discover] {len(new_names)} not yet tracked: {new_names}\n")

        new_entries = []
        for name in new_names:
            print(f"[discover] Looking up: {name}")
            entry = find_career_url(name, existing_urls, region_config)
            if entry:
                new_entries.append(entry)
                existing_urls.add(entry["career_url"].lower())
                existing_names.add(entry["name"].lower())
                region_discoveries[entry["name"].lower()] = region_name

        if new_entries:
            print(f"[discover] Added {len(new_entries)} new companies for {region_name}:")
            for entry in new_entries:
                print(f"  + {entry['name']} -> {entry['career_url']}")
                # Add to the region's companies list
                region_companies = search_config["regions"][region_name].get("companies", [])
                if not any(c["name"].lower() == entry["name"].lower() for c in region_companies):
                    region_companies.append({"name": entry["name"], "career_url": entry["career_url"]})
                    search_config["regions"][region_name]["companies"] = region_companies

    # Automatic region distribution for overlaps
    if regions:
        print(f"\n[discover] Checking for overlaps in other regions...")
        for region_name, region_config in regions.items():
            if region_name not in search_config["regions"]:
                continue
            region_companies = search_config["regions"][region_name].get("companies", [])
            for company in region_companies:
                discovered_in = region_discoveries.get(company["name"].lower())
                if discovered_in and discovered_in != region_name:
                    continue  # Only check companies discovered elsewhere
                for other_region, other_config in regions.items():
                    if other_region == region_name:
                        continue
                    if has_jobs_in_location(company["name"], other_config):
                        add_company_to_region(search_config, other_region, company)

    if not any(search_config["regions"][r].get("companies", []) for r in regions.keys()):
        print("\n[discover] No new companies to add.")
        return

    # Save updated search_config
    save_search_config(search_config)

    print(f"\n[discover] Discovery complete. search_config.yml now has companies across {len(regions)} regions")


if __name__ == "__main__":
    run()
