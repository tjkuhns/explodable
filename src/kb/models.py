"""Pydantic models for all five KB entity types."""

import json
from datetime import datetime, date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _parse_pg_array(v, enum_cls=None):
    """Parse a PostgreSQL array string like '{a,b,c}' into a Python list."""
    if v is None:
        return v
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
        items = v[1:-1].split(",") if v != "{}" else []
        if enum_cls:
            return [enum_cls(item.strip()) for item in items]
        return [item.strip() for item in items]
    return v


def _parse_pg_vector(v):
    """Parse a pgvector string like '[0.1,0.2,...]' into a Python list of floats."""
    if v is None:
        return v
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.startswith("["):
        return json.loads(v)
    return v


# ── Enums matching PostgreSQL types ──


class RootAnxiety(str, Enum):
    MORTALITY = "mortality"
    ISOLATION = "isolation"
    INSIGNIFICANCE = "insignificance"
    MEANINGLESSNESS = "meaninglessness"
    HELPLESSNESS = "helplessness"


class PankseppCircuit(str, Enum):
    SEEKING = "SEEKING"
    RAGE = "RAGE"
    FEAR = "FEAR"
    LUST = "LUST"
    CARE = "CARE"
    PANIC_GRIEF = "PANIC_GRIEF"
    PLAY = "PLAY"


class CircuitAffinity(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    CONTEXTUAL = "contextual"


class FindingProvenance(str, Enum):
    HUMAN = "human"
    AI_PROPOSED = "ai_proposed"
    AI_CONFIRMED = "ai_confirmed"


class FindingStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    MERGED = "merged"
    REJECTED = "rejected"


class RelationshipType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    QUALIFIES = "qualifies"
    EXTENDS = "extends"
    SUBSUMES = "subsumes"
    REFRAMES = "reframes"


class ContradictionResolution(str, Enum):
    A_SUPERSEDES_B = "a_supersedes_b"
    B_SUPERSEDES_A = "b_supersedes_a"
    BOTH_VALID_DIFFERENT_SCOPE = "both_valid_different_scope"
    MERGED_INTO_NEW = "merged_into_new"
    UNRESOLVED = "unresolved"


class SourceType(str, Enum):
    ACADEMIC = "academic"
    JOURNALISM = "journalism"
    BOOK = "book"
    SOCIAL_MEDIA = "social_media"
    GOVERNMENT = "government"
    PRIMARY = "primary"
    OTHER = "other"
    INDUSTRY_RESEARCH = "industry_research"
    PRACTITIONER = "practitioner"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Entity 1: Root Anxiety Nodes ──


class RootAnxietyNode(BaseModel):
    id: UUID
    anxiety: RootAnxiety
    description: str
    cultural_domains: list[str]
    created_at: datetime

    @field_validator("cultural_domains", mode="before")
    @classmethod
    def parse_cultural_domains(cls, v):
        return _parse_pg_array(v)


class AnxietyCircuitAffinity(BaseModel):
    id: UUID
    anxiety: RootAnxiety
    circuit: PankseppCircuit
    affinity: CircuitAffinity
    rationale: str | None = None


# ── Entity 2: Findings ──


class FindingCreate(BaseModel):
    claim: str = Field(max_length=280)
    elaboration: str
    root_anxieties: list[RootAnxiety] = Field(min_length=1, max_length=2)
    primary_circuits: list[PankseppCircuit] | None = Field(default=None, max_length=3)
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_basis: str
    provenance: FindingProvenance = FindingProvenance.AI_PROPOSED
    academic_discipline: str
    cultural_domains: list[str] | None = None
    era: str | None = None
    source_document: str | None = None
    status: FindingStatus = FindingStatus.PROPOSED
    embedding: list[float] | None = None


class Finding(FindingCreate):
    id: UUID
    confidence_level: ConfidenceLevel
    claim_hash: str
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None

    @field_validator("cultural_domains", mode="before")
    @classmethod
    def parse_cultural_domains(cls, v):
        return _parse_pg_array(v)

    @field_validator("root_anxieties", mode="before")
    @classmethod
    def parse_root_anxieties(cls, v):
        return _parse_pg_array(v, RootAnxiety)

    @field_validator("primary_circuits", mode="before")
    @classmethod
    def parse_primary_circuits(cls, v):
        return _parse_pg_array(v, PankseppCircuit)

    @field_validator("embedding", mode="before")
    @classmethod
    def parse_embedding(cls, v):
        return _parse_pg_vector(v)

    @field_validator("confidence_level", mode="before")
    @classmethod
    def compute_confidence_level(cls, v: str | ConfidenceLevel | None, info) -> ConfidenceLevel:
        if v is not None:
            return ConfidenceLevel(v) if isinstance(v, str) else v
        score = info.data.get("confidence_score", 0.0)
        if score >= 0.75:
            return ConfidenceLevel.HIGH
        elif score >= 0.45:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW


class FindingUpdate(BaseModel):
    claim: str | None = Field(default=None, max_length=280)
    elaboration: str | None = None
    root_anxieties: list[RootAnxiety] | None = Field(default=None, min_length=1, max_length=2)
    primary_circuits: list[PankseppCircuit] | None = Field(default=None, max_length=3)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_basis: str | None = None
    academic_discipline: str | None = None
    cultural_domains: list[str] | None = None
    era: str | None = None
    source_document: str | None = None
    status: FindingStatus | None = None
    embedding: list[float] | None = None


# ── Entity 3: Manifestations ──


class ManifestationCreate(BaseModel):
    description: str
    academic_discipline: str
    era: str | None = None
    source: str
    source_type: SourceType
    source_url: str | None = None
    source_date: date | None = None
    embedding: list[float] | None = None


class Manifestation(ManifestationCreate):
    id: UUID
    description_hash: str
    created_at: datetime
    updated_at: datetime

    @field_validator("embedding", mode="before")
    @classmethod
    def parse_embedding(cls, v):
        return _parse_pg_vector(v)


# ── Entity 4: Inter-Finding Relationships ──


class FindingRelationshipCreate(BaseModel):
    from_finding_id: UUID
    to_finding_id: UUID
    relationship: RelationshipType
    rationale: str = Field(min_length=20)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("to_finding_id")
    @classmethod
    def no_self_reference(cls, v: UUID, info) -> UUID:
        if "from_finding_id" in info.data and v == info.data["from_finding_id"]:
            raise ValueError("Finding cannot have a relationship with itself")
        return v


class FindingRelationship(FindingRelationshipCreate):
    id: UUID
    created_at: datetime


# ── Entity 5: Contradiction Records ──


class ContradictionRecordCreate(BaseModel):
    finding_a_id: UUID
    finding_b_id: UUID
    description: str
    resolution: ContradictionResolution = ContradictionResolution.UNRESOLVED
    resolution_notes: str | None = None
    merged_finding_id: UUID | None = None

    @field_validator("finding_b_id")
    @classmethod
    def no_self_contradiction(cls, v: UUID, info) -> UUID:
        if "finding_a_id" in info.data and v == info.data["finding_a_id"]:
            raise ValueError("Finding cannot contradict itself")
        return v


class ContradictionRecord(ContradictionRecordCreate):
    id: UUID
    resolved_at: datetime | None = None
    created_at: datetime
