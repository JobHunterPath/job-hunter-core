# LinkedIn System

This folder supports a human-reviewed LinkedIn workflow for visibility,
recruiter discovery, and networking.

It never posts, likes, follows, connects, or messages automatically.
It only creates private review queues and draft text.
Most users only edit positioning, audience, pillars, cadence, and enablement;
generic discovery rules live in internal packaged defaults.

The workflow is disabled by default. Set `linkedin.enabled: true` in
`linkedin/config.yml` when you want to opt in.

## Workflow

1. Run idea generation to mine your private story bank and role-specific patterns
   for public-safe themes.
2. Run draft generation once a week to create posts from unused raw ideas.
3. Run discovery two or three times per week to find recruiters, peers,
   and creators worth connecting with.
4. Manually publish, connect, follow, or message on LinkedIn.

## Files

- `config.yml`: positioning, pillars, cadence, confidentiality,
  and automation policy.
- `ideas.md`: LLM-generated raw idea backlog.
- `drafts/`: generated post drafts for review.
- `networking.md`: people to follow/connect with and message drafts.
- `state.yml`: seen people and output fingerprints used to avoid repeats.

## Local Commands

```bash
docker run --rm -it -v "$PWD:/workspace" -w /workspace \
  ghcr.io/abdulrbasit/abdul.basit_resume/job-hunter-core:latest \
  job-hunter linkedin all
```

All generated content requires human review before use.
