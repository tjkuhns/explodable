"""Input validation models for ingesting findings from external sources.

Shared between scripts/import_findings.py (CLI import) and the
/api/research/upload endpoint (UI upload). Centralizes vocabulary
validation against the canonical taxonomy.
"""

from pydantic import BaseModel, Field, field_validator

from src.kb.models import RootAnxiety, PankseppCircuit, SourceType


# ── Canonical controlled vocabularies ──

VALID_ANXIETIES: set[str] = {a.value for a in RootAnxiety}
VALID_CIRCUITS: set[str] = {c.value for c in PankseppCircuit}
VALID_SOURCE_TYPES: set[str] = {s.value for s in SourceType}

# Cultural domains — MUST stay in sync with docs/taxonomy.md and
# the root_anxiety_nodes.cultural_domains seed data in config/kb_schema.sql.
# The full 25-value vocabulary. "religion" appears under both mortality
# and meaninglessness in the docs — it's one value here.
VALID_CULTURAL_DOMAINS: set[str] = {
    # Mortality
    "religion", "legacy arts", "heroism", "immortality technology", "medicine",
    # Isolation
    "tribalism", "nationalism", "romantic love", "social media", "friendship",
    # Insignificance
    "achievement culture", "wealth", "fame", "competitive systems", "legacy",
    # Meaninglessness
    "philosophy", "science", "ideology", "conspiracy theories", "narrative art",
    # Helplessness
    "political movements", "rebellion", "technology", "authoritarianism", "addiction",
}

# Academic disciplines currently in the KB. New disciplines may be added
# during ingestion; this list is advisory, not enforced at the model level.
KNOWN_ACADEMIC_DISCIPLINES: set[str] = {
    "affective neuroscience",
    "b2b psychology",
    "behavioral economics",
    "buyer psychology",
    "clinical psychology",
    "cognitive psychology",
    "entrepreneurship psychology",
    "evolutionary psychology",
    "existential psychology",
    "health psychology",
    "moral psychology",
    "organizational psychology",
    "political psychology",
    "social neuroscience",
    "social psychology",
}


class SourceInput(BaseModel):
    url: str
    title: str
    source_type: str
    snippet: str

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        if v not in VALID_SOURCE_TYPES:
            raise ValueError(
                f"Invalid source_type '{v}'. Must be one of: {sorted(VALID_SOURCE_TYPES)}"
            )
        return v


class FindingInput(BaseModel):
    claim: str = Field(max_length=280)
    elaboration: str
    academic_discipline: str | None = None
    domain: str | None = None  # backward compat — prefer academic_discipline
    cultural_domains: list[str] | None = None
    era: str | None = None
    root_anxieties: list[str] = Field(min_length=1, max_length=2)
    primary_circuits: list[str] | None = Field(default=None, max_length=3)
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_basis: str
    sources: list[SourceInput] = Field(default_factory=list)

    @field_validator("academic_discipline", mode="before")
    @classmethod
    def fallback_domain(cls, v, info):
        if v is None and info.data.get("domain"):
            return info.data["domain"]
        return v

    @field_validator("root_anxieties")
    @classmethod
    def validate_anxieties(cls, v: list[str]) -> list[str]:
        for a in v:
            if a not in VALID_ANXIETIES:
                raise ValueError(
                    f"Invalid root_anxiety '{a}'. Must be one of: {sorted(VALID_ANXIETIES)}"
                )
        return v

    @field_validator("primary_circuits")
    @classmethod
    def validate_circuits(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for c in v:
            if c not in VALID_CIRCUITS:
                raise ValueError(
                    f"Invalid circuit '{c}'. Must be one of: {sorted(VALID_CIRCUITS)}"
                )
        return v

    @field_validator("cultural_domains")
    @classmethod
    def validate_cultural_domains(cls, v: list[str] | None) -> list[str] | None:
        """Enforce the 25-value taxonomy vocabulary. Empty list is allowed.

        Rejects any value not in docs/taxonomy.md — prevents silent drift
        from LLM extraction passes that hallucinate adjacent values like
        'social platforms' instead of 'social media'.
        """
        if v is None:
            return v
        invalid = [d for d in v if d not in VALID_CULTURAL_DOMAINS]
        if invalid:
            raise ValueError(
                f"Invalid cultural_domains value(s) {invalid}. "
                f"Must be from taxonomy vocabulary: {sorted(VALID_CULTURAL_DOMAINS)}"
            )
        return v
