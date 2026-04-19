#!/bin/bash
# Explodable statusline — live KB + pipeline state for Claude Code.
#
# Called every session render. Must be fast (< 5s). Caches for 10s via
# /tmp/.explodable_statusline_cache to avoid hammering postgres on every
# keystroke.

CACHE=/tmp/.explodable_statusline_cache
CACHE_TTL=10

# Serve cache if fresh
if [ -f "$CACHE" ]; then
  AGE=$(( $(date +%s) - $(stat -c %Y "$CACHE" 2>/dev/null || echo 0) ))
  if [ "$AGE" -lt "$CACHE_TTL" ]; then
    cat "$CACHE"
    exit 0
  fi
fi

cd /home/thoma/explodable 2>/dev/null || exit 0

# Read stdin session JSON if provided (Claude Code passes this) — we don't
# use it currently but drain it to avoid any blocking.
[ -t 0 ] || cat > /dev/null

# KB state (short query, 2s timeout)
KB_STATE=$(python3 -c "
import os
try:
    for line in open('.env'):
        l = line.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, _, v = l.partition('=')
        os.environ.setdefault(k.strip(), v.strip().strip(chr(34)).strip(chr(39)))
    import psycopg
    conn = psycopg.connect(
        host='localhost', port=5432, dbname='explodable',
        user='explodable', password=os.environ.get('POSTGRES_PASSWORD', ''),
        connect_timeout=2,
    )
    with conn.cursor() as cur:
        cur.execute(\"SELECT COUNT(*) FILTER (WHERE status='active'), COUNT(*) FILTER (WHERE status='proposed') FROM findings;\")
        a, p = cur.fetchone()
        cur.execute('SELECT COUNT(*) FROM finding_relationships;')
        r = cur.fetchone()[0]
    conn.close()
    print(f'KB {a}a/{p}p · {r}rel')
except Exception:
    print('KB ?')
" 2>/dev/null)

# Draft count
DRAFTS=$(ls drafts/*.md 2>/dev/null | wc -l | tr -d ' ')

# API status
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 http://localhost:8000/api/health 2>/dev/null)
if [ "$API_STATUS" = "200" ]; then
  API_MARK="API↑"
else
  API_MARK="API↓"
fi

# Celery worker running?
if pgrep -f "celery.*celery_app.*worker" > /dev/null 2>&1; then
  CELERY_MARK="worker↑"
else
  CELERY_MARK="worker↓"
fi

# Git branch
BRANCH=$(git branch --show-current 2>/dev/null || echo '?')

# Compose output
OUTPUT="$KB_STATE · $DRAFTS drafts · $API_MARK · $CELERY_MARK · $BRANCH"
echo "$OUTPUT" | tee "$CACHE"
