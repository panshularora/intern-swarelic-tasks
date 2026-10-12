# Design notes — 4.5 Call Queue

I chose Option A (call queue dashboard) because the 4.1 writeup already had a hole there: rules say `route` and then assignment looks for an AVAILABLE agent, but if nobody is free the call has nowhere to wait. A queue is the missing piece between routing and `CALL_RECEIVED`. Options B and C are useful too but they sit after the call. I wanted something that actually changes how a live call moves.

## Decisions

1. **Two models, not one counter.** The brief lists `current_calls` on `CallQueue`. I kept that field so list endpoints are cheap, but the real source of truth is `QueuedCall` rows. `current_calls` is updated inside `select_for_update` on enqueue/dequeue. If I only stored an integer I'd have no wait times and no abandonment rate.

2. **FIFO with a priority integer.** Stretch goal was "VIP goes to the front". I didn't build a second queue. `priority` default 100, VIP can POST `priority=1`, dequeue orders by `priority, enqueued_at`. Same table, one index-friendly order_by. Trade-off: a tenant can pass any priority number. A real SCAI version would map `caller_tag` from the rules engine instead of trusting the client.

3. **AllowAny + eager Celery.** This is a homework service, not wired into JWT from 4.4. Adding SimpleJWT here would mostly copy intern-backend 3.3 and eat time. Auth is a trade-off I skipped on purpose. Celery uses `ALWAYS_EAGER` so `python manage.py test` works without Redis. The task still exists as `alert_queue_threshold.delay(...)` so swapping the broker later is a settings change.

4. **Stats computed on read.** Avg wait / longest wait / abandonment rate are not stored. Small queues, SQLite, intern scale. Edge case: waiting calls count toward longest wait (someone is still on hold) but avg wait only uses finished calls so a caller sitting for an hour doesn't drag the average until they leave.

## Edge cases I handled

- enqueue when `waiting >= max_size` → 400 "Queue is full"
- dequeue / abandon on empty → 400
- bad caller_number (too short / letters) → 400, same idea as the 3.2 CallLog serializer
- missing queue id → 404
- threshold alert only fires when current_calls **>** threshold, not on every enqueue
- `select_for_update` so two workers don't dequeue the same row (works on postgres; sqlite tests are single-threaded)

## Edge cases I skipped

- tenant isolation is a query param, not JWT claim. Easy to spoof. Would hook `request.tenant` if this landed in scaibp.
- no WebSocket. Polling `/stats/` is enough for the homework.
- no hold-time SLA, no callback number, no "position in line" TTS.
- abandoned is a separate POST, not a timeout Beat job. With more time I'd add a beat task that abandons anything waiting > N seconds.

## What I would do with more time

Wire enqueue to the 4.2 engine (`route` action target = queue name) and dequeue to the 4.3 machine (`CALL_RECEIVED` on the agent). Persist tenant from middleware. Channels for a live supervisor board. That's the actual platform shape — this repo is just the queue slice.
