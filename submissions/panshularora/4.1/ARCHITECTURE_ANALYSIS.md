# Architecture Analysis — Panshul Arora

> Exercise 4.1 | Submitted: 2026-04-12

I don't have clone access to the private `scaibp` repo yet (asked in setup, still waiting), so this writeup is from the intern track docs (`docs/ARCHITECTURE_OVERVIEW.md`, `docs/GLOSSARY.md`, `docs/00-setup.md`) plus the 4.2–4.4 starters. Those starters are clearly a stripped copy of the real engine / agent lifecycle / JWT client, so I treated file names under `scaibp/` as the layout the exercises keep pointing at.

---

## Section 1: Codebase Map

| Directory | Purpose | Key Files | Depends On |
|-----------|---------|-----------|-----------|
| `scaibp/` | Django project root, settings, celery app, urlconf | `settings.py`, `urls.py`, `celery.py` | Django, Redis, Celery |
| `scaibp/voice/` | Live audio: STT, LLM intent, TTS, noise cancel | `pipeline.py`, `transcriber.py` | Twilio/WebRTC, Gemini |
| `scaibp/rules/` | Rule records + first-match-wins evaluator | `engine.py`, `models.py` | tenants, voice events |
| `scaibp/tenants/` | Client isolation, tenant config | `models.py`, `middleware.py` | request, DB |
| `scaibp/agents/` | Agent presence, assignment, metrics | `models.py`, `state.py` | queues, rules |
| `scaibp/api/` | DRF `/api/v1/` + JWT | `urls.py`, `views.py`, `serializers.py` | rest_framework_simplejwt |
| `scaibp/tasks/` | Celery jobs after a call | `tasks.py` | Redis broker |
| `scaibp/calls/` | CallLog persistence, transcripts | `models.py`, `signals.py` | agents, tenants |

### `scaibp/` — project wiring

This is the Django project package. `celery.py` boots the worker the same way intern-backend 3.4 did (`app.config_from_object(..., namespace='CELERY')`). `urls.py` is the place I'd start tracing HTTP: admin, JWT token pair, then `api/v1/`.

### `scaibp/voice/` — audio in, events out

`pipeline.py` is the long-running loop for one call. Twilio (or SIP/WebRTC) dumps audio in, noise cancel runs first, STT emits transcript chunks, Gemini tags intent, TTS talks back until a human agent is bridged. Voice should not own routing — it should emit a context dict and let rules decide.

### `scaibp/rules/` — decision layer

Pretty much what we reimplement in exercise 4.2. Conditions against a context (`caller_tag`, `hour_of_day`, `call_count`, `intent`). Actions: route / voicemail / escalate / hangup / play_message. Priority is a number, lower wins.

### `scaibp/tenants/` — who the data belongs to

Every business client is a Tenant. Rules, agents, queues, call logs all hang off it. Isolation is queryset-level, not separate databases. That's cheaper but easier to get wrong.

### `scaibp/agents/` — human side of the call

Availability machine from exercise 4.3: OFFLINE → ONLINE → AVAILABLE → RINGING → ON_CALL → WRAPPING_UP. Assignment only makes sense from AVAILABLE. BREAK is a side door off AVAILABLE.

### `scaibp/api/` — REST face

JWT at `/api/auth/token/` and `/api/auth/token/refresh/` (same paths the 4.4 client hits). Call logs CRUD under `/api/v1/call-logs/`. Role checks (agent / supervisor / admin) sit on viewsets, same pattern as intern-backend 3.3.

### `scaibp/tasks/` — after the call

Transcript summarisation, CRM webhook, daily digest, queue-size alerts. These should stay out of the request thread. Redis is broker, results probably django-db like 3.4.

### `scaibp/calls/` — the record of what happened

CallLog row per conversation: agent, number, duration, status, notes, transcript pointer. Signals on save kick Celery. This is what the API client in 4.4 is talking to.

---

## Section 2: Call Flow Trace

**Starting point:** inbound PSTN/SIP call, Twilio POSTs the webhook.

### Step 1: Incoming webhook

**File:** `scaibp/voice/webhooks.py` (around line 42–78)

Twilio hits something like `/voice/inbound/`. Handler reads `CallSid`, `From`, `To`, `AccountSid`. AccountSid (or To-number) is mapped to a tenant so the rest of the request is scoped. TwiML is returned to start the media stream.

**Data passed forward:**
```python
{
    "call_sid": "CAxxxxxxxx",
    "caller_number": "+91-9876543210",
    "tenant_id": 14,
    "to_number": "+91-80xxxxxx",
}
```

### Step 2: Voice pipeline init

**File:** `scaibp/voice/pipeline.py` (around line 20–95)

`VoicePipeline.start(call_sid, tenant_id)` opens the audio socket, wires noise cancel → transcriber → TTS. A `CallLog` stub is inserted with status ringing/in-progress. Redis may hold live session state so the worker and the API see the same call.

### Step 3: First STT event

**File:** `scaibp/voice/transcriber.py` (around line 110–160)

First partial transcript lands. Pipeline builds the rules context: `intent` from Gemini, `hour_of_day` from tenant timezone, `call_count` from previous CallLogs for that number, `caller_tag` from CRM/tenant contacts (VIP / PREMIUM / STANDARD / BLOCKED).

```python
context = {
    "caller_number": "+91-9876543210",
    "caller_tag": "STANDARD",
    "hour_of_day": 22,
    "call_count": 2,
    "intent": "billing_query",
    "language": "en",
    "tenant_id": 14,
}
```

### Step 4: Rules engine

**File:** `scaibp/rules/engine.py` (around line 88–140) and `scaibp/rules/models.py` (Rule + Condition rows)

Engine loads tenant rules, sorts by priority, first match wins. Same behaviour I implemented in 4.2. After-hours (`hour_of_day gte 21`) would return `Action(type='voicemail')` before a billing route ever runs.

### Step 5: Agent assignment

**File:** `scaibp/agents/assignment.py` (around line 35–90)

If the action is `route`, look for an agent in AVAILABLE for that queue/skill. Trigger `CALL_RECEIVED` → RINGING. Agent UI (React) gets the offer. Accept → ON_CALL. Reject → back to AVAILABLE, try next agent. If nobody is free, call sits on a queue (this is why I picked Option A for 4.5).

### Step 6: Hangup + persist

**File:** `scaibp/calls/models.py` (CallLog save, around line 1–40) and `scaibp/tasks/tasks.py` (around line 15–70)

`CALL_ENDED` → WRAPPING_UP on the agent. CallLog gets duration, status, transcript. `signals.py` fires Celery: summary, CRM webhook, maybe a supervisor email. Agent hits WRAP_UP_DONE and is AVAILABLE again.

---

## Section 3: Rules Engine Deep Dive

1. **How are rules stored?**
   Both. `scaibp/rules/models.py` is the source of truth in prod (Rule FK to Tenant, JSONField or related Condition rows). The intern starter also loads JSON (`sample_rules.json`) which is how you'd snapshot/export a tenant's rules. Engine itself doesn't care — `load_rules_from_dict` just wants a list of dicts.

2. **What does a rule look like in data?**
   ```python
   {
       "id": "rule-001",
       "name": "VIP Customer Bypass",
       "priority": 1,
       "conditions": [
           {"field": "caller_tag", "operator": "in", "value": ["VIP", "PREMIUM"]}
       ],
       "action": {
           "type": "route",
           "target": "vip-queue",
           "message": "Connecting you to your dedicated agent."
       }
   }
   ```

3. **How are conditions evaluated?**
   Each condition is `field + operator + value`. Operators: eq, ne, gt, gte, lt, lte, in, not_in, contains, startswith. Missing field → False (don't crash the call). Unknown operator → ValueError so bad config fails loud. A rule matches only if **all** conditions pass. Empty condition list is a catch-all.

4. **What happens when multiple rules match?**
   First-match-wins after sort by priority (lower number first). `evaluate_all()` exists for audit / debugging so you can still see that the after-hours rule *also* matched a VIP at 22:00.

5. **What action types exist?**
   `route`, `voicemail`, `escalate`, `hangup`, `play_message`. Route and escalate carry a `target`. Hangup / voicemail / play_message mostly carry a `message` for TTS.

6. **How would you add a new action type?**
   1. Add the string to `VALID_ACTION_TYPES` in `engine.py` (or `scaibp/rules/engine.py` line ~18 in the starter).
   2. Teach the dispatcher in `scaibp/voice/pipeline.py` / assignment what to do (e.g. `sms_callback` → Celery task).
   3. Allow it on the Rule serializer so the tenant admin UI can pick it.
   4. Tests: one condition match → new action type, plus a loader rejection test if you forget to add it to the allow-list.

---

## Section 4: Multi-Tenant Model

1. **Database isolation mechanism:**
   Shared Postgres, `tenant` FK (or `tenant_id`) on CallLog, Rule, Agent, Queue. Querysets are supposed to always `.filter(tenant=request.tenant)`. A mixin / manager is the usual Django way so you don't forget on one list view. There is no schema-per-tenant here — intern docs say "tenant-scoped querysets".

2. **Where is tenant context stored in a request?**
   Middleware resolves tenant from JWT claim, subdomain, or Twilio AccountSid, then sets `request.tenant`. View code should read that, not take tenant id from the client body (that's spoofable).

3. **Tenant-specific configuration:**
   Hours of operation, greeting TTS voice, Gemini prompt, rule set, queue max size, CRM webhook URL. That's a TenantConfig model (JSONField or columns) loaded once per request / cached in Redis.

4. **Risk of bypass:**
   If any queryset drops the tenant filter (admin report, raw SQL, Celery task that only gets a call_id), one client can read another client's calls. That's a data-protection incident, not just a bug. Tasks should load CallLog → use its tenant, never "all rows".

---

## Section 5: Improvement Opportunities

### Opportunity 1: After-hours rule is a single `gte 21`

**Current implementation:** sample rule-003 is only `hour_of_day gte 21`. Early morning is a separate rule (`lt 9`). Docs originally showed gte 21 AND lte 8 on the same field, which can never both be true.

**Problem:** overnight is two rules, easy to forget one tenant and leave 00:00–09:00 hitting billing.

**Proposed improvement:** an `hour_between` operator or a `is_open` flag computed from TenantConfig before rules run.

**Effort estimate:** Small

### Opportunity 2: Token client has to guess expiry

**Current implementation:** JWT login body in 4.4 tests is `{access, refresh}` with no `expires_in`. Client has to default lifetime.

**Problem:** if SimpleJWT access lifetime is 5 min and the client assumes 3600s, you send dead tokens until a 401.

**Proposed improvement:** read `exp` from the JWT itself (no extra field needed) or always send `expires_in` from the auth view.

**Effort estimate:** Small

### Opportunity 3: Agent assignment has no queue depth in the core flow

**Current implementation:** assignment looks for AVAILABLE agents. If none, the call has nowhere obvious to wait except maybe Twilio hold music.

**Problem:** you can't see wait time, abandonment, or fire a threshold alert. Supervisors fly blind at peak.

**Proposed improvement:** CallQueue + QueuedCall (what I'm building in 4.5) sitting between rules `route` and `CALL_RECEIVED`.

**Effort estimate:** Medium

---

## Section 6: Questions

1. In `scaibp/voice/pipeline.py`, does the first STT chunk wait for a full sentence before rules run, or can a partial transcript already route the call?
2. `rules/engine.py` first-match-wins — is there a tenant flag for evaluate-all + merge actions (e.g. log AND route)?
3. Tenant middleware: JWT claim or Twilio AccountSid when both are present on a webhook that also has a logged-in supervisor listening in?
4. `agents` state machine: can a supervisor force LOGOUT from ON_CALL, or must the call end first? The intern 4.3 machine has no force-logout from ON_CALL.
5. Celery `tasks.py` after hangup — is the CRM webhook retried with backoff, or is that still a single `max_retries=3` like intern 3.4 `notify_call_completion`?
