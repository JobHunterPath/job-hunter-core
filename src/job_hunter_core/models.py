from __future__ import annotations
import dataclasses


@dataclasses.dataclass
class JobPosting:
    title: str
    company: str
    url: str
    location: str
    snippet: str
    source: str
    posted: str = ""
    region: str = ""
    query: str = ""
    extraction_method: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> "JobPosting":
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclasses.dataclass
class Company:
    name: str
    career_url: str
    region: str
    location: str
    country: str = ""
    search_lang: str = ""
    ats: str = ""


@dataclasses.dataclass
class JobScore:
    score: int
    matched_keywords: list[str]
    gaps: list[str]
    years_exp_required: int | None = None
