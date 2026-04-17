"""DEPRECATED 2026-04-14 — see src/research_pipeline/DEPRECATED.md

Research Planner agent. Dormant dependency of drift_monitor. Decomposes
a research directive into parallel tasks. No longer an active ingestion path.

Input: research directive (string)
Output: ResearchPlan (Pydantic model — structured, no free-form text in state)
Model: Claude Sonnet via LangChain Anthropic integration
"""

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic


# ── Output models ──


class ResearchTask(BaseModel):
    """A single research task to be executed by a Researcher agent."""

    task_id: str = Field(default="task_0", description="Short unique identifier, e.g. 'task_1'")
    query: str = Field(
        description="Specific research question to investigate. Must be concrete and searchable."
    )
    search_keywords: list[str] = Field(
        default_factory=list,
        description="2-5 keywords optimized for web search APIs (Tavily/Exa)",
    )
    expected_domain: str = Field(
        default="general",
        description="The domain this task targets, e.g. 'political psychology', 'consumer behavior'",
    )
    source_priority: list[str] = Field(
        default_factory=lambda: ["academic", "journalism", "book"],
        description="Preferred source types in order, e.g. ['academic', 'journalism', 'book']",
    )


class ResearchPlan(BaseModel):
    """Structured output from the Research Planner."""

    topic: str = Field(default="", description="The core topic being researched")
    root_anxiety_hints: list[str] = Field(
        default_factory=list,
        description=(
            "1-2 root anxieties this topic likely connects to. "
            "Must be from: mortality, isolation, insignificance, meaninglessness, helplessness"
        ),
    )
    tasks: list[ResearchTask] = Field(
        default_factory=list,
        description="2-5 parallel research tasks that together cover the directive",
    )
    rationale: str = Field(
        default="",
        description="Brief explanation of how the tasks decompose the directive and why these anxiety connections are hypothesized",
    )


# ── Planner agent ──

PLANNER_SYSTEM_PROMPT = """You are a research planner for an intelligence engine that organizes knowledge by root human anxieties.

Your job: decompose a research directive into 2-5 concrete, parallel research tasks that together cover the directive comprehensively.

Root anxiety framework (always consider which apply):
- mortality: Fear of death and non-existence
- isolation: Fear of being alone or excluded from community
- insignificance: Fear that one's life or actions do not matter
- meaninglessness: Fear that existence has no inherent purpose
- helplessness: Fear of lacking agency or control

Guidelines:
- Each task must be independently executable by a web search agent
- Tasks should target DIFFERENT angles or domains — not overlapping searches
- Include at least one task that crosses domains (e.g. if the directive is about politics, one task should search for parallels in consumer psychology, philosophy, or another domain)
- search_keywords should be optimized for Tavily/Exa search APIs — concrete terms, not abstract concepts
- source_priority should reflect what sources are most likely to yield quality findings for that specific task
- The cross-domain task is critical — it enables the engine's core value: connecting structurally unrelated domains via shared root anxieties"""


def create_planner() -> ChatAnthropic:
    """Create the planner LLM with structured output."""
    from src.shared.constants import ANTHROPIC_MODEL
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0.3,
        max_tokens=2000,
        max_retries=5,
    )
    return llm.with_structured_output(ResearchPlan)


def plan_research(directive: str) -> ResearchPlan:
    """Decompose a research directive into a structured research plan.

    Args:
        directive: The research question or topic to investigate.

    Returns:
        ResearchPlan with 2-5 parallel tasks, topic, and root anxiety hints.
    """
    planner = create_planner()
    result = planner.invoke(
        [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": directive},
        ]
    )
    return result
