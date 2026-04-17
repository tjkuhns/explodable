"""50 test topics for the expanded bake-off validation.

Distribution: balanced across density levels, brand registers, anxiety
types, and cultural domains. Each topic has ground-truth metadata for
verifying router classification accuracy.

Topics 1-5 are the original Phase 1 topics. Topics 6-50 are new.
"""

from dataclasses import dataclass


@dataclass
class TestTopic:
    id: str
    brand: str
    prompt: str
    expected_density: str  # dense, medium, sparse, cross_domain, ood
    expected_domains: list[str]  # primary cultural domains this touches
    expected_anxieties: list[str]  # primary root anxieties


TOPICS: list[TestTopic] = [
    # ── Original Phase 1 topics (T01-T05) ──

    TestTopic("T01", "explodable",
              "The silent disengagement: why enterprise customers churn six months before they tell you. Diagnose the psychological and organizational mechanics of disengagement-before-notification, grounded in behavioral science and buyer psychology.",
              "dense", ["competitive systems"], ["helplessness"]),
    TestTopic("T02", "explodable",
              "The first number wins: anchoring in B2B procurement negotiations. Analyze how anchoring and reference dependence shape multi-stakeholder pricing decisions.",
              "medium", ["competitive systems"], ["helplessness"]),
    TestTopic("T03", "the_boulder",
              "Why B2B vendor lock-in and religious conversion share a psychological architecture. A cross-domain analysis of identity investment, sunk cost, tribal belonging, and the cost of leaving.",
              "cross_domain", ["competitive systems", "religion", "tribalism"], ["isolation", "helplessness"]),
    TestTopic("T04", "the_boulder",
              "Legacy anxiety and the economics of signaling after death. Why the things humans build to outlast them function as commercial products for an anxiety that no product can actually resolve.",
              "sparse", ["legacy"], ["mortality"]),
    TestTopic("T05", "the_boulder",
              "What golf reveals about organizational status games. Using golf as a lens to analyze the psychological architecture of status games in modern organizations.",
              "ood", ["achievement culture"], ["insignificance"]),

    # ── Dense commercial (Explodable) — T06-T15 ──

    TestTopic("T06", "explodable",
              "Why the best-qualified vendor loses: how buying committees manufacture consensus against the strongest option.",
              "dense", ["competitive systems"], ["helplessness"]),
    TestTopic("T07", "explodable",
              "The confidence gap in sales forecasting: why your pipeline numbers are a collective fiction and what the behavioral science says about fixing them.",
              "dense", ["competitive systems"], ["helplessness"]),
    TestTopic("T08", "explodable",
              "Free trials don't convert — they create ownership. The psychology of endowment effects in SaaS product-led growth.",
              "dense", ["competitive systems", "technology"], ["helplessness"]),
    TestTopic("T09", "explodable",
              "Why enterprise buyers ghost after the demo: the psychology of post-evaluation silence and what it actually signals.",
              "dense", ["competitive systems"], ["helplessness", "isolation"]),
    TestTopic("T10", "explodable",
              "The security review as psychological theater: why procurement's most time-consuming gate is really about career risk, not data protection.",
              "dense", ["competitive systems", "technology"], ["helplessness"]),
    TestTopic("T11", "explodable",
              "Loss-framed ROI decks outperform gain-framed ones. Why showing the cost of inaction beats showing the benefit of action in B2B sales.",
              "dense", ["competitive systems"], ["helplessness"]),
    TestTopic("T12", "explodable",
              "The three-vendor shortlist is a fiction: why B2B buyers decide in the first 30 seconds and spend the next 90 days proving it.",
              "dense", ["competitive systems"], ["helplessness"]),
    TestTopic("T13", "explodable",
              "Why your champion just went silent: organizational identity shifts and the vulnerability window after internal promotions.",
              "dense", ["competitive systems"], ["helplessness", "insignificance"]),
    TestTopic("T14", "explodable",
              "The mid-market trap: why $10-50M ARR companies make systematically worse technology purchasing decisions than companies above or below them.",
              "dense", ["competitive systems"], ["helplessness"]),
    TestTopic("T15", "explodable",
              "ROI calculators are closing arguments, not evidence: why the most-used sales tool in B2B is designed to confirm, not inform.",
              "dense", ["competitive systems"], ["helplessness"]),

    # ── Medium density (Explodable + Boulder) — T16-T25 ──

    TestTopic("T16", "explodable",
              "Why healthcare procurement is the most fear-driven buying process in any industry: the psychology of defensive medicine applied to vendor selection.",
              "medium", ["medicine", "competitive systems"], ["helplessness", "mortality"]),
    TestTopic("T17", "explodable",
              "The AI feature tax: why buyers pay premiums for AI capabilities they'll never use, and what this reveals about technology purchasing psychology.",
              "medium", ["technology", "competitive systems"], ["helplessness", "insignificance"]),
    TestTopic("T18", "the_boulder",
              "Algorithmic loneliness: how recommendation engines systematically narrow social connection while appearing to expand it.",
              "medium", ["social media", "technology"], ["isolation"]),
    TestTopic("T19", "the_boulder",
              "The dopamine economics of doom scrolling: why attention markets produce engagement that degrades the consumer.",
              "medium", ["addiction", "social media", "technology"], ["meaninglessness"]),
    TestTopic("T20", "the_boulder",
              "Why financial scarcity makes you stupid: the bandwidth tax on decision quality and its implications for economic mobility.",
              "medium", ["wealth"], ["helplessness"]),
    TestTopic("T21", "the_boulder",
              "The obedience architecture: what Milgram's experiments actually tell us about organizational compliance in 2026.",
              "medium", ["authoritarianism", "competitive systems"], ["helplessness"]),
    TestTopic("T22", "the_boulder",
              "Near-miss design in gambling machines and its structural parallels to gamified SaaS engagement metrics.",
              "medium", ["addiction", "technology"], ["helplessness"]),
    TestTopic("T23", "the_boulder",
              "Why burnout isn't exhaustion — it's a meaning crisis. The existential psychology of professional identity collapse.",
              "medium", ["achievement culture", "medicine"], ["meaninglessness"]),
    TestTopic("T24", "explodable",
              "Social proof is a quorum function, not a persuasion technique: why testimonials work nonlinearly and what the saturation point is.",
              "medium", ["competitive systems", "tribalism"], ["insignificance"]),
    TestTopic("T25", "the_boulder",
              "The preference falsification machine: how social media industrializes the gap between public and private opinion.",
              "medium", ["social media", "ideology"], ["isolation", "insignificance"]),

    # ── Cross-domain (both brands) — T26-T35 ──

    TestTopic("T26", "the_boulder",
              "Why luxury consumption and political extremism are the same psychological product sold through different channels.",
              "cross_domain", ["wealth", "ideology", "tribalism"], ["insignificance", "meaninglessness"]),
    TestTopic("T27", "explodable",
              "The structural similarity between enterprise vendor lock-in and addiction: sunk cost, withdrawal, and the architecture of switching pain.",
              "cross_domain", ["competitive systems", "addiction"], ["helplessness"]),
    TestTopic("T28", "the_boulder",
              "How conspiracy theories and brand loyalty activate the same identity-protection circuitry.",
              "cross_domain", ["conspiracy theories", "competitive systems", "tribalism"], ["meaninglessness", "helplessness"]),
    TestTopic("T29", "the_boulder",
              "The architecture of belonging: what religious communities, CrossFit boxes, and Slack workspaces share at the neurological level.",
              "cross_domain", ["religion", "friendship", "technology"], ["isolation"]),
    TestTopic("T30", "explodable",
              "Why B2B sales methodology and clinical therapy share a psychological architecture: the parallels between SPIN Selling and motivational interviewing.",
              "cross_domain", ["competitive systems", "medicine"], ["helplessness"]),
    TestTopic("T31", "the_boulder",
              "Heroism as a consumer product: how military valor, startup mythology, and extreme sports sell the same anxiety relief.",
              "cross_domain", ["heroism", "achievement culture", "competitive systems"], ["mortality", "insignificance"]),
    TestTopic("T32", "the_boulder",
              "The authoritarian personality and the enterprise org chart: what political psychology reveals about why hierarchies feel safe.",
              "cross_domain", ["authoritarianism", "competitive systems", "ideology"], ["helplessness", "isolation"]),
    TestTopic("T33", "explodable",
              "Why procurement committees and jury deliberations produce the same systematic biases: group decision psychology across institutional contexts.",
              "cross_domain", ["competitive systems", "science"], ["helplessness"]),
    TestTopic("T34", "the_boulder",
              "Parasocial economics: why one-sided relationships with influencers, brands, and AI companions follow the same attachment architecture.",
              "cross_domain", ["social media", "romantic love", "technology"], ["isolation"]),
    TestTopic("T35", "the_boulder",
              "The meaning maintenance machine: how conspiracy theories, religion, and brand fandom all serve the same terror management function.",
              "cross_domain", ["conspiracy theories", "religion", "tribalism"], ["meaninglessness", "mortality"]),

    # ── Sparse (both brands) — T36-T42 ──

    TestTopic("T36", "the_boulder",
              "The psychology of the monument: why humans build things designed to outlast the species that built them.",
              "sparse", ["legacy", "philosophy"], ["mortality"]),
    TestTopic("T37", "the_boulder",
              "Why nationalism is an anxiety product: the behavioral economics of flag-waving in an age of global identity.",
              "sparse", ["nationalism", "ideology"], ["isolation", "meaninglessness"]),
    TestTopic("T38", "the_boulder",
              "Romantic rejection and organizational restructuring activate the same neural circuits. What this means for how we think about professional loss.",
              "sparse", ["romantic love", "competitive systems"], ["isolation"]),
    TestTopic("T39", "the_boulder",
              "The rebellion premium: why countercultural movements always get captured by the markets they claim to resist.",
              "sparse", ["rebellion", "wealth"], ["meaninglessness", "insignificance"]),
    TestTopic("T40", "the_boulder",
              "Why stories about heroes are actually stories about the fear of irrelevance: the anxiety architecture of the hero narrative.",
              "sparse", ["heroism", "narrative art"], ["mortality", "insignificance"]),
    TestTopic("T41", "the_boulder",
              "The philanthropy paradox: why giving money away is the most expensive status signal and the most effective anxiety medication.",
              "sparse", ["legacy", "wealth"], ["mortality", "insignificance"]),
    TestTopic("T42", "the_boulder",
              "Fame as a mortality project: why the desire to be known is structurally identical to the desire to not die.",
              "sparse", ["fame", "legacy"], ["mortality"]),

    # ── Out-of-distribution (both brands) — T43-T50 ──

    TestTopic("T43", "the_boulder",
              "What competitive eating reveals about the psychology of pointless achievement.",
              "ood", [], ["insignificance"]),
    TestTopic("T44", "the_boulder",
              "The architectural psychology of open-plan offices: how physical space design encodes status anxiety.",
              "ood", [], ["insignificance", "helplessness"]),
    TestTopic("T45", "explodable",
              "Why the best sales reps are the worst managers: the Peter Principle as a behavioral science problem.",
              "ood", ["competitive systems"], ["helplessness"]),
    TestTopic("T46", "the_boulder",
              "The psychology of the checkout line: what waiting in queues reveals about how humans process fairness and injustice.",
              "ood", [], ["helplessness"]),
    TestTopic("T47", "the_boulder",
              "Why people cry at graduations: the anxiety architecture of transitions and the rituals we build around them.",
              "ood", [], ["meaninglessness", "mortality"]),
    TestTopic("T48", "explodable",
              "The conference badge hierarchy: how name tags, lanyards, and speaker ribbons create instant status systems that mirror enterprise org politics.",
              "ood", [], ["insignificance"]),
    TestTopic("T49", "the_boulder",
              "What karaoke reveals about the psychology of public vulnerability and why it matters more than you think.",
              "ood", [], ["isolation", "insignificance"]),
    TestTopic("T50", "the_boulder",
              "The psychology of the Sunday scaries: why the most universal modern anxiety has no product solution.",
              "ood", [], ["helplessness", "meaninglessness"]),
]


# Distribution summary
if __name__ == "__main__":
    from collections import Counter
    density = Counter(t.expected_density for t in TOPICS)
    brand = Counter(t.brand for t in TOPICS)
    anxiety = Counter(a for t in TOPICS for a in t.expected_anxieties)
    print("Density:", dict(density))
    print("Brand:", dict(brand))
    print("Anxiety:", dict(anxiety))
    print(f"Total: {len(TOPICS)}")
