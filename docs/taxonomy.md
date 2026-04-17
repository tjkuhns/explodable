# Explodable Taxonomy: Classification Fields

This document defines the two classification axes used on `findings` and how they relate to each other and to the `root_anxiety_nodes` table.

---

## 1. `academic_discipline` (formerly `domain`)

**What it means:** The academic or professional field whose research produced the finding. This answers: *"What kind of scholar or practitioner generated this knowledge?"*

**Column:** `findings.academic_discipline` (TEXT, NOT NULL)

**Allowed values:**

| Value | Description |
|---|---|
| affective neuroscience | Panksepp-lineage subcortical emotion research |
| b2b psychology | Psychology of business-to-business buying and selling |
| behavioral economics | Kahneman/Tversky-lineage decision research |
| buyer psychology | Psychology of consumer purchase behavior |
| clinical psychology | Psychotherapy, diagnosis, treatment research |
| cognitive psychology | Attention, memory, reasoning, judgment |
| entrepreneurship psychology | Psychology of founders, risk-taking, venture creation |
| evolutionary psychology | Adapted psychological mechanisms, fitness logic |
| existential psychology | Yalom-lineage concerns: death, freedom, isolation, meaning |
| health psychology | Stress, coping, illness behavior, health decision-making |
| moral psychology | Haidt-lineage moral intuition and judgment research |
| organizational psychology | Workplace behavior, leadership, team dynamics |
| political psychology | Political attitudes, ideology, collective action |
| social neuroscience | Neural correlates of social behavior |
| social psychology | Interpersonal and group behavior, attitudes, persuasion |

New disciplines may be added as research expands. The list above reflects all values present in the knowledge base as of April 2026.

---

## 2. `cultural_domains`

**What it means:** The real-world cultural spheres where the finding's anxiety dynamics visibly manifest. This answers: *"Where in human culture can you actually see this playing out?"*

**Column:** `findings.cultural_domains` (TEXT[], nullable)

**Allowed values:**

These are drawn from (and must stay consistent with) the `root_anxiety_nodes.cultural_domains` seed data.

### Mortality
| Value | Description |
|---|---|
| religion | Organized belief systems offering afterlife, transcendence, or death ritual |
| legacy arts | Art, memoir, monument-building motivated by surviving death symbolically |
| heroism | Sacrifice narratives, martyr culture, hero worship |
| immortality technology | Cryonics, life extension, digital consciousness, transhumanism |
| medicine | Healthcare systems, end-of-life care, disease anxiety |

### Isolation
| Value | Description |
|---|---|
| tribalism | In-group/out-group boundary enforcement |
| nationalism | National identity as belonging mechanism |
| romantic love | Pair-bonding as isolation remedy |
| social media | Digital platforms as connection/disconnection systems |
| friendship | Non-kin social bonding |

### Insignificance
| Value | Description |
|---|---|
| achievement culture | Meritocracy, credentialism, hustle culture |
| wealth | Money as significance proxy |
| fame | Celebrity, influence, visibility-seeking |
| competitive systems | Sports, rankings, zero-sum status hierarchies |
| legacy | Dynastic thinking, estate planning, "making a mark" |

### Meaninglessness
| Value | Description |
|---|---|
| philosophy | Formal meaning-making systems (existentialism, nihilism, absurdism) |
| science | Empirical worldview as meaning framework or meaning-disruptor |
| ideology | Political and social belief systems as meaning containers |
| conspiracy theories | Pattern-imposition on chaos as meaning-restoration |
| narrative art | Fiction, film, mythology as meaning-delivery vehicles |
| religion | Faith-based meaning frameworks (shared with mortality) |

### Helplessness
| Value | Description |
|---|---|
| political movements | Collective action as agency recovery |
| rebellion | Refusal, protest, revolution as control assertion |
| technology | Tools and systems as agency amplifiers |
| authoritarianism | Surrendering agency to a strong leader or system |
| addiction | Compulsive behavior as pseudo-agency or agency collapse |

A finding may reference cultural domains from multiple root anxiety nodes. The tagging is not constrained to only the domains listed under its assigned root anxieties.

---

## 3. How They Relate

These are orthogonal axes:

- **academic_discipline** = where the knowledge comes from (the lens)
- **cultural_domains** = where the phenomenon shows up in the world (the subject)

Example: A finding from `behavioral economics` (academic_discipline) might manifest in `wealth` and `achievement culture` (cultural_domains). A finding from `affective neuroscience` might manifest in `addiction` and `romantic love`.

The `root_anxiety_nodes.cultural_domains` field defines the *universe* of cultural domains relevant to each anxiety. The `findings.cultural_domains` field tags individual findings with whichever of those cultural domains they speak to, regardless of which root anxiety the finding is filed under.

---

## 4. Governance

- Adding a new `academic_discipline` value: permitted during research ingestion when a finding genuinely comes from a discipline not yet listed. Update this document afterward.
- Adding a new `cultural_domains` value: requires updating both this document and the `root_anxiety_nodes` seed data in `config/kb_schema.sql`. The two must stay in sync.
- Ingestion scripts should validate `cultural_domains` values against this canonical list.
