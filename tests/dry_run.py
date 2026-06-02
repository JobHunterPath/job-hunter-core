#!/usr/bin/env python3
"""
Dry run mode: Test full pipeline with mock data.
No API calls. Validates configuration and file handling.
Perfect for testing changes without spending money.
"""

from datetime import datetime


def mock_scrape(region: str):
    """Return test jobs without scraping."""
    return [
        {
            "title": "Senior PM - AI/ML",
            "company": "Example Strategic Company",
            "url": "https://example.com/job1",
            "snippet": "Hiring Senior PM for AI. 5+ years experience. Roadmapping, stakeholder management required.",
            "source": "career_page",
        },
        {
            "title": "Product Manager",
            "company": "Example SaaS Company",
            "url": "https://example.org/job1",
            "snippet": "PM needed. 3-4 years PM experience. B2B products. Agile teams.",
            "source": "career_page",
        },
        {
            "title": "Product Owner - Platform",
            "company": "Example Platform Company",
            "url": "https://example.net/job1",
            "snippet": "PO role. Experience with agile, roadmapping. Digital transformation focus.",
            "source": "career_page",
        },
    ]


def mock_score(job: dict) -> dict:
    """Return mock scoring."""
    # Score varies by company for realism
    scores = {
        "Example Strategic Company": 88,
        "Example SaaS Company": 82,
        "Example Platform Company": 75,
    }

    return {
        "score": scores.get(job.get("company"), 80),
        "matched_keywords": ["product management", "agile", "strategy", "roadmapping"],
        "gaps": ["automotive experience"],
        "years_exp_required": 5,
    }


def mock_tailor(job: dict) -> str:
    """Return mock tailored resume."""
    return f"""
    % Tailored Resume for {job["company"]}
    
    \\section{{Professional Experience}}
    
    \\cvevent{{Product Manager}}{{ExampleCo}}{{2021 -- Present}}{{Target City}}
    
    Tailored keywords for {job["company"]}:
    \\begin{{itemize}}
    \\item Roadmap development and product strategy
    \\item Cross-functional team leadership
    \\item Agile/Scrum methodologies
    \\item Stakeholder management
    \\end{{itemize}}
    """


def mock_cover_letter(job: dict) -> str:
    """Return mock cover letter."""
    return f"""
    {datetime.now().strftime("%B %d, %Y")}
    
    Hiring Manager
    Dear Sir/Madam,
    
    I am interested in the {job["title"]} position at {job["company"]}.
    
    With 7 years of product management experience, I have successfully led cross-functional teams 
    in complex environments. My background spans strategy definition, roadmap development, and 
    stakeholder alignment across engineering, sales, and customer success.
    
    At ExampleCo, I led platform initiatives with engineering, design, and customer-facing teams.
    Replace this sentence with a verified metric from your own story bank.
    
    I would be pleased to discuss how my experience contributes to {job["company"]}'s mission.
    
    Sincerely,
    Candidate Name
    """


def dry_run():
    """Run pipeline with mock data."""
    print("🏃 DRY RUN MODE - No API calls, Configuration validation only")
    print("=" * 70)

    jobs = mock_scrape("berlin")
    print(f"✅ [Scrape] Found {len(jobs)} test jobs")
    print(f"   Jobs: {', '.join([j['company'] for j in jobs])}")

    # Simulate scoring
    print(f"\n⏳ [Scoring] Scoring {len(jobs)} jobs...")
    scored_jobs = []
    for job in jobs:
        score_result = mock_score(job)
        scored_jobs.append((job, score_result))

    min_score = 80
    passed = [j for j, s in scored_jobs if s["score"] >= min_score]
    failed = [j for j, s in scored_jobs if s["score"] < min_score]

    print(
        f"   ✅ Passed ({len(passed)}, >= {min_score}): {', '.join([j['company'] for j in passed])}"
    )
    if failed:
        print(
            f"   ❌ Failed ({len(failed)}, < {min_score}): {', '.join([j['company'] for j in failed])}"
        )

    # Simulate tailoring and cover letter for passed jobs
    print(f"\n⏳ [Tailoring] Tailoring resumes for {len(passed)} jobs...")
    for job in passed:
        tailor_result = mock_tailor(job)
        print(f"   ✅ {job['company']}: {len(tailor_result)} chars")

    print(f"\n⏳ [Cover Letter] Generating covers for {len(passed)} jobs...")
    for job in passed:
        cover = mock_cover_letter(job)
        print(f"   ✅ {job['company']}: {len(cover)} chars")

    print("\n" + "=" * 70)
    print("✅ DRY RUN COMPLETE")
    print("\n📊 Summary:")
    print(f"   • Jobs scraped: {len(jobs)}")
    print(f"   • Jobs scored: {len(scored_jobs)}")
    print(f"   • Jobs passed threshold: {len(passed)}")
    print(f"   • Resumes to tailor: {len(passed)}")
    print(f"   • Cover letters to generate: {len(passed)}")
    print("\n💰 Estimated cost: $0.00 (no API calls)")
    print("✅ Configuration: Valid")
    print("\n💡 Next steps:")
    print("   1. Run: python scripts/scrape_jobs.py  (real jobs, no API cost)")
    print("   2. Run: python scripts/test_scoring.py  (test scoring logic, ~$0.002)")
    print("   3. Run: python scripts/run_pipeline.py  (full pipeline, ~$2-5)")


if __name__ == "__main__":
    dry_run()
