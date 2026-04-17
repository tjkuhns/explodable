"""Shared constants — single source of truth for thresholds, dedup parameters, and model config.

Imported by src/kb/dedup.py, src/content_pipeline/, src/kb/embeddings.py,
and drift_monitor. Pinning critical model versions here prevents silent
drift when a provider updates default behavior.
"""

import os

# LLM model
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# Embedding model — LOCKED.
#
# The KB embeddings are indexed against a specific model + dimension
# combination. Changing any of these values requires a full reindex of
# all 305+ findings because cosine similarity scores are not comparable
# across embedding spaces.
#
# If you change these values, also:
#   1. Run `python -c "from src.kb.embeddings import generate_embedding; ..."`
#      to verify the new model is accessible
#   2. Re-embed the entire KB via a reindex script (not yet built — see
#      docs/RETIREMENT_PLAN.md post-launch enhancements for the migration
#      path to BGE-M3 or voyage-3-large)
#   3. Update EMBEDDING_MODEL_VERSION to a new lock date
#   4. Verify retrieval quality on known-good queries before committing
EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_MODEL_DIMS = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))
EMBEDDING_MODEL_VERSION = "2024-01-25"  # locked date of adoption

# MinHash LSH parameters
NUM_PERM = 128
LSH_THRESHOLD = 0.5  # Jaccard similarity threshold for near-duplicate candidates

# Cosine similarity thresholds (two distinct purposes)
COSINE_DEDUP_THRESHOLD = 0.90    # Write-time: reject semantic duplicates
COSINE_DISCOVERY_THRESHOLD = 0.85  # Retrieval-time: surface related findings
