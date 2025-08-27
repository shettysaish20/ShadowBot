# WebSocket Event Schema (ShadowBot)

Version: draft

## Connection Flow
1. Client connects to /ws (WebSocket)
2. Immediately sends: {"session_id": "<id>", "last_seq": <optional int>}
3. Server responds with ack event (type: ws.subscribed)
4. Server replays events after last_seq (or entire buffer if none) then streams live events.

Sequence field `seq` is strictly increasing per session. Use it to detect gaps.

## Core Event Envelope
{
  "seq": <int>,
  "ts": <float epoch seconds>,
  "session_id": "...",
  "type": "<event_type>",
  "payload": { ... },
  // optional when truncated
  "truncated": true,
  "original_size": <bytes before truncation>
}

Server enforces ~32KB limit per event payload. Large string fields are proportionally truncated with ellipsis. If still too large, a final fallback holds a single truncated_blob.

## Event Types

### ws.subscribed
Sent once after client handshake.
Payload embedded directly in ack frame (NOT inside a wrapper envelope):
{
  "type": "ws.subscribed",
  "session_id": "...",
  "last_seq": <client supplied>,
  "latest_seq": <server seq at subscribe time>,
  "buffer_size": <current buffered events>,
  "buffer_cap": 500
}

### ws.heartbeat
Emitted every 15s of inactivity. Payload:
{ "last_seq": <latest known seq> }
Use to measure liveness. Missing > 2 intervals => consider reconnect.

### ws.replay.gap
Indicates replay mismatch.
Reasons:
- ahead_of_server: client requested future seq
- buffer_overflow: client requested seq older than retained buffer window
Payload example:
{ "reason": "buffer_overflow", "requested_seq": 10, "oldest_available": 25, "latest_seq": 80 }

### job.status
Lifecycle & progress of a submitted job.
States: queued, running, completed, failed, timeout, canceled
Common payload fields:
{
  "state": "running",
  "job_id": "uuid",
  "completed_steps": <int>,
  "failed_steps": <int>,
  "total_steps": <int>,
  "progress_ratio": <0.0-1.0>,
  "elapsed_ms": <int>
}
Periodic refresh every ~3s while running plus after each step and terminal state.

### job.error
When a job fails or times out.
{
  "job_id": "...",
  "state": "failed" | "timeout",
  "error": "message"
}

### step.start
{
  "step_id": "T5",
  "agent": "FormatterAgent",
  "reads": ["T1"],
  "writes": ["T5"],
  "turn": <int>
}

### step.end
{
  "step_id": "T5",
  "status": "completed" | "failed",
  "duration_ms": <float>,
  "error": <string or null>,
  "output_meta": { "type": "str" | "dict" | "none" | etc., "size": <int optional>, ... },
  "progress": { "completed": <int>, "failed": <int>, "total": <int>, "ratio": <float> }
}

### step.error
Additional error context after a failed step.
{
  "step_id": "T5",
  "error_kind": "timeout" | "error",
  "message": "truncated message"
}

### report.final
HTML report summary snippet.
{
  "step_id": "T9",
  "path": "media/generated/<session_id>/formatted_report_T9.html",
  "size": <full html length>,
  "snippet": "sanitized truncated html",
  "snippet_truncated": <bool>,
  "content_type": "text/html",
  "snippet_chars": <int>,
  "sanitized": true
}

## Future Reserved
clarification.request / clarification.response (not yet emitted)

## Client Recommendations
- Maintain last_seq; on reconnect send { last_seq } to receive only missed events.
- If you detect a numeric gap in seq values without a ws.replay.gap explanation, emit a local warning and consider a fast reconnect.
- Treat job.status states terminal set: {completed, failed, timeout, canceled}. Stop active waits when one observed.
- Use heartbeat absence to trigger reconnect (>= 30s).

## Example Flow
1. ws.subscribed
2. job.status (running, elapsed_ms=0)
3. step.start (T1)
4. step.end (T1)
5. job.status (running progress_ratio=0.1)
6. ... more steps ...
7. report.final
8. job.status (completed)

## Buffer & Replay
- Buffer retains last 500 events per session.
- Replay provided automatically after subscribe based on client last_seq.
- If requested last_seq is too old, client receives ws.replay.gap (buffer_overflow) and should rebuild state from scratch using replay then live.

## Truncation Flags
If an event includes truncated=true, consult original_size and be aware some string fields were shortened. Full data might exist elsewhere (e.g., /job/<id> REST endpoint or persisted report file).

## Error Handling Patterns
- On step.error or job.error surface message to UI and allow user to retry.
- For timeout, consider offering job cancel or re-run with adjusted parameters.

-- End of spec --
