"""Tests for the LinkedIn content workflow."""

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from linkedin import common, discover_engagement, draft_posts, generate_ideas


def _config(tmp_path: Path) -> Path:
    data = {
        "linkedin": {
            "positioning": "Technical Product Owner",
            "audience": ["hiring managers"],
            "content_pillars": ["platform product management"],
            "tone": ["concrete"],
            "forbidden_phrases": ["please refer me"],
            "confidentiality": {
                "forbidden_public_details": ["internal product names"],
            },
            "files": {
                "ideas": str(tmp_path / "ideas.md"),
                "drafts_dir": str(tmp_path / "drafts"),
                "engagement": str(tmp_path / "engagement.md"),
                "networking": str(tmp_path / "networking.md"),
            },
            "idea_generation": {"ideas_per_run": 2},
            "draft_generation": {
                "posts_per_run": 1,
                "source_status": "raw",
                "mark_converted": True,
                "max_words_per_post": 120,
            },
            "engagement_discovery": {
                "results_per_query": 1,
                "posts_per_run": 1,
                "region": {"country": "DE", "search_lang": "en", "location": "Berlin"},
                "linkedin_domains": {
                    "people": "linkedin.com/in",
                    "posts": "linkedin.com/posts",
                },
                "topics": ["platform product management"],
            },
            "networking": {
                "suggestions_per_run": 1,
                "max_message_words": 70,
                "target_people": ["platform product managers"],
            },
        }
    }
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_next_idea_id_increments():
    assert common.next_idea_id("") == "IDEA-0001"
    assert common.next_idea_id("## IDEA-0007: Existing") == "IDEA-0008"


def test_idea_parsing_ignores_fenced_examples():
    text = """# Ideas

```markdown
## IDEA-0001: Example only

Status: raw
```

## IDEA-0003: Real idea

Status: raw
"""
    assert common.next_idea_id(text) == "IDEA-0004"
    assert [block["id"] for block in common.unconverted_ideas(text, "raw")] == ["IDEA-0003"]


def test_linkedin_yaml_files_parse():
    files = [
        ".github/workflows/linkedin_content.yml",
        ".github/workflows/sync_template_repo.yml",
        ".github/workflows/update_from_template.yml",
        "linkedin/config.yml",
        "template/linkedin/config.yml",
        "config/api_config.yml",
        "template/config/api_config.yml",
    ]
    for filename in files:
        assert yaml.safe_load(Path(filename).read_text(encoding="utf-8")) is not None


def test_generate_ideas_appends_public_safe_items(tmp_path):
    cfg = _config(tmp_path)
    payload = json.dumps([
        {
            "title": "Internal platforms need product thinking",
            "source": "story_bank",
            "pillar": "platform product management",
            "angle": "Platform work needs adoption and versioning.",
            "evidence_to_use": "General platform product experience.",
            "do_not_mention": "Internal product names.",
        }
    ])

    with patch("linkedin.generate_ideas.complete_linkedin", return_value=payload):
        rendered = generate_ideas.generate(cfg)

    ideas = (tmp_path / "ideas.md").read_text(encoding="utf-8")
    assert len(rendered) == 1
    assert "IDEA-0001" in ideas
    assert "Public-safe: yes" in ideas


def test_draft_posts_creates_draft_and_marks_idea_converted(tmp_path):
    cfg = _config(tmp_path)
    (tmp_path / "ideas.md").write_text(
        """# Ideas

## IDEA-0001: Platform APIs need product lifecycle thinking

Status: raw
Source: manual
Pillar: platform product management
Confidentiality: public-safe
Public-safe: yes

Angle:
Versioning and adoption matter.
""",
        encoding="utf-8",
    )
    payload = json.dumps([
        {
            "idea_id": "IDEA-0001",
            "title": "Platform APIs need product lifecycle thinking",
            "pillar": "platform product management",
            "post_text": "A platform API is still a product surface.",
            "confidentiality_notes": "Generalized.",
            "review_checklist": "Check no private names are included.",
        }
    ])

    with patch("linkedin.draft_posts.complete_linkedin", return_value=payload):
        created = draft_posts.draft(cfg)

    assert len(created) == 1
    assert created[0].exists()
    ideas = (tmp_path / "ideas.md").read_text(encoding="utf-8")
    assert "Converted to draft: yes" in ideas
    assert "Draft:" in ideas


def test_discover_engagement_writes_review_queues(tmp_path):
    cfg = _config(tmp_path)
    search_result = [{
        "url": "https://www.linkedin.com/in/example",
        "title": "Example Product Leader",
        "description": "Posts about platform product management.",
        "source": "SearXNG",
    }]
    payload = json.dumps({
        "people": [{
            "name": "Example Product Leader",
            "role_or_context": "Platform PM",
            "url": "https://www.linkedin.com/in/example",
            "why_relevant": "Writes about platform product management.",
            "relationship_type": "peer_conversation",
            "suggested_action": "review manually",
            "message_variants": ["I noticed your posts on platform product work."],
        }],
        "posts": [{
            "author_or_source": "Example Product Leader",
            "topic": "Platform PM",
            "url": "https://www.linkedin.com/posts/example",
            "why_relevant": "Matches configured topic.",
            "suggested_comment": "This framing is useful for platform teams.",
        }],
    })

    with patch("linkedin.discover_engagement.search_web", return_value=search_result), \
         patch("linkedin.discover_engagement.complete_linkedin", return_value=payload):
        result = discover_engagement.discover(cfg)

    assert len(result["people"]) == 1
    assert "Example Product Leader" in (tmp_path / "networking.md").read_text(encoding="utf-8")
    assert "Draft comment" in (tmp_path / "engagement.md").read_text(encoding="utf-8")


def test_discover_engagement_falls_back_on_malformed_json(tmp_path):
    cfg = _config(tmp_path)
    search_result = [
        {
            "url": "https://www.linkedin.com/in/example",
            "title": "Example Product Leader - Senior Product Manager - LinkedIn",
            "description": "Posts about platform product management.",
            "source": "SearXNG",
            "query": 'site:linkedin.com/in "platform product management"',
        },
        {
            "url": "https://www.linkedin.com/posts/example",
            "title": "Example post - LinkedIn",
            "description": "A post about platform product management.",
            "source": "SearXNG",
            "query": 'site:linkedin.com/posts "platform product management"',
        },
    ]

    with patch("linkedin.discover_engagement.search_web", return_value=search_result), \
         patch("linkedin.discover_engagement.complete_linkedin", return_value='{"people": [{"name": "broken"}]'):
        result = discover_engagement.discover(cfg)

    assert len(result["people"]) == 1
    assert len(result["posts"]) == 0
    person = result["people"][0]
    assert person["suggested_action"] == "review manually"
    assert person["relationship_type"] == "peer_conversation"
    assert person["message_variants"]
    assert "Example Product Leader" in (tmp_path / "networking.md").read_text(encoding="utf-8")
    engagement = (tmp_path / "engagement.md").read_text(encoding="utf-8")
    assert "https://www.linkedin.com/posts/example" not in engagement
    assert "_No post suggestions returned._" in engagement


def test_blank_model_comments_are_skipped(tmp_path):
    cfg = _config(tmp_path)
    search_result = [{
        "url": "https://www.linkedin.com/posts/example",
        "title": "AI coding tools as interns - LinkedIn",
        "description": "AI coding tools work better when teams add review loops and clear delegation.",
        "source": "SearXNG",
    }]
    payload = json.dumps({
        "people": [],
        "posts": [{
            "author_or_source": "AI coding tools as interns",
            "topic": "internal developer platforms",
            "url": "https://www.linkedin.com/posts/example",
            "why_relevant": "AI coding tools work better when teams add review loops and clear delegation.",
            "suggested_comment": "",
        }],
    })

    with patch("linkedin.discover_engagement.search_web", return_value=search_result), \
         patch("linkedin.discover_engagement.complete_linkedin", return_value=payload):
        result = discover_engagement.discover(cfg)

    assert result["posts"] == []
    engagement = (tmp_path / "engagement.md").read_text(encoding="utf-8")
    assert "https://www.linkedin.com/posts/example" not in engagement
    assert "_No post suggestions returned._" in engagement


def test_login_wall_results_are_filtered(tmp_path):
    cfg = _config(tmp_path)
    search_result = [
        {
            "url": "https://www.linkedin.com/posts/login-wall-post",
            "title": "Some Post - LinkedIn",
            "description": "Agree & Join LinkedIn\nBy clicking Continue to join...",
            "source": "SearXNG",
            "query": 'site:linkedin.com/posts "platform product management"',
        },
    ]
    with patch("linkedin.discover_engagement.search_web", return_value=search_result), \
         patch("linkedin.discover_engagement.complete_linkedin", return_value='{}'):
        result = discover_engagement.discover(cfg)
    assert len(result["posts"]) == 0


def test_stale_posts_are_filtered():
    from datetime import date, timedelta
    from linkedin.discover_engagement import _is_recent_post

    old = date.today() - timedelta(days=35)
    recent = date.today() - timedelta(days=10)

    old_desc = f"{old.strftime('%b')} {old.day}, {old.year} · Some post content"
    recent_desc = f"{recent.strftime('%b')} {recent.day}, {recent.year} · Some post content"

    assert not _is_recent_post(old_desc)
    assert _is_recent_post(recent_desc)
    assert _is_recent_post("No date prefix — keep by default")
