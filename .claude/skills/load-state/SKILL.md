---
name: load-state
description: Display live operational state at the start of a session — KB counts, pending findings, recent drafts, running services, open contradictions. Use at the start of any new session or after /clear to ground the conversation in live reality before planning work.
allowed-tools: Bash
---

# Load operational state

Displaying live state of the Explodable engine so we can orient
quickly without re-reading docs.

## KB snapshot

!`cd /home/thoma/explodable && python3 -c "
import os
for line in open('.env'):
    l = line.strip()
    if not l or l.startswith('#') or '=' not in l: continue
    k, _, v = l.partition('=')
    os.environ.setdefault(k.strip(), v.strip().strip(chr(34)).strip(chr(39)))
try:
    import psycopg
    conn = psycopg.connect(host='localhost', port=5432, dbname='explodable',
                           user='explodable', password=os.environ['POSTGRES_PASSWORD'],
                           connect_timeout=3)
    with conn.cursor() as cur:
        cur.execute(\"SELECT status, COUNT(*) FROM findings GROUP BY status ORDER BY 1;\")
        for row in cur.fetchall(): print(f'  findings {row[0]}: {row[1]}')
        cur.execute(\"SELECT relationship::text, COUNT(*) FROM finding_relationships GROUP BY 1 ORDER BY 2 DESC;\")
        print('  relationships:')
        for row in cur.fetchall(): print(f'    {row[0]}: {row[1]}')
        cur.execute(\"SELECT COUNT(*) FROM manifestations;\")
        print(f'  manifestations: {cur.fetchone()[0]}')
        cur.execute(\"SELECT COUNT(*) FROM contradiction_records WHERE resolution = 'unresolved';\")
        print(f'  unresolved contradictions: {cur.fetchone()[0]}')
        cur.execute(\"SELECT MAX(created_at)::date as newest, MAX(approved_at)::date as last_approved FROM findings WHERE status = 'active';\")
        row = cur.fetchone()
        print(f'  newest active finding: {row[0]} · last approved: {row[1]}')
    conn.close()
except Exception as e:
    print(f'  DB unreachable: {e}')
"`

## Pending work

!`cd /home/thoma/explodable && python3 -c "
import os
for line in open('.env'):
    l = line.strip()
    if not l or l.startswith('#') or '=' not in l: continue
    k, _, v = l.partition('=')
    os.environ.setdefault(k.strip(), v.strip().strip(chr(34)).strip(chr(39)))
try:
    import psycopg
    conn = psycopg.connect(host='localhost', port=5432, dbname='explodable',
                           user='explodable', password=os.environ['POSTGRES_PASSWORD'],
                           connect_timeout=3)
    with conn.cursor() as cur:
        cur.execute(\"SELECT source_document, COUNT(*) FROM findings WHERE status='proposed' GROUP BY 1 ORDER BY 2 DESC;\")
        rows = cur.fetchall()
        if rows:
            print('  proposed findings pending HITL review:')
            for r in rows:
                print(f'    {r[0] or \"(pipeline)\"}: {r[1]}')
        else:
            print('  proposed findings: none pending')
    conn.close()
except Exception:
    pass
"`

## Drafts on disk

!`cd /home/thoma/explodable && ls -t drafts/*.md 2>/dev/null | head -5 | sed 's|.*/|  |' || echo "  (none)"`

## Services

!`curl -s -o /dev/null -w "  API: http_status=%{http_code} (localhost:8000)\n" http://localhost:8000/api/health 2>/dev/null || echo "  API: not reachable"`
!`pgrep -f "celery.*worker" > /dev/null && echo "  Celery worker: running" || echo "  Celery worker: down"`
!`docker ps --format '{{.Names}}: {{.Status}}' 2>/dev/null | grep -E "postgres|redis" | sed 's/^/  /' || echo "  Docker: not reachable"`

## Git state

!`cd /home/thoma/explodable && git branch --show-current && git log --oneline -3 && git status -s 2>/dev/null | head -10 || echo "(clean)"`

---

Read the output above. Give me a one-paragraph state summary that answers:
1. Is the engine healthy and reachable?
2. What work is pending (findings, drafts, contradictions)?
3. What branch are we on and is there uncommitted work?
4. What's the most useful next move based on the state?

Do not wait for me to ask — just give me the summary. Then wait for my next instruction.
