"""Flask API wrapper for multi-turn agentic system.

Endpoints:
POST /start  -> initialize MultiMCP + background event loop
GET  /health -> status & counts
POST /run    -> submit async run job (returns job_id)
GET  /job/<job_id> -> job status + final HTML report (when completed)
GET  /sessions/<session_id> -> session graph summary

Design:
- Background asyncio loop in a dedicated thread (single loop)
- Each session keeps its own AgentLoop4 instance (isolated conversation_turn counters)
- Jobs stored in-memory (no persistence)
- Enforces 120s timeout per job
- Aborts /run if any provided file path is missing
"""
from __future__ import annotations
import uuid
import time
import threading
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import re
import queue
from flask import Flask, request, jsonify, abort
from flask_sock import Sock
from werkzeug.utils import secure_filename

# Local imports (reuse existing code)
from main import load_server_configs  # re-use config loader
from mcp_servers.multiMCP import MultiMCP
from agentLoop.flow import AgentLoop4
from agentLoop.contextManager import ExecutionContextManager
from utils.utils import log_error
from api_helpers.history import list_history, load_session_summary, load_session_report_html

API_VERSION = "v1"
JOB_TIMEOUT_SECONDS = 120
HEARTBEAT_INTERVAL = 15
PAYLOAD_MAX_BYTES = 32 * 1024  # 32KB cap for entire payload (approx)
CHANNEL_IDLE_SECONDS = 1800  # 30 minutes
CHANNEL_SWEEP_INTERVAL = 300  # 5 minutes

app = Flask(__name__)
sock = Sock(app)

# ----------------------- HTTP Request Logging -----------------------
# Lightweight access log printing method, path, status, and duration.
try:
    from flask import g
except Exception:  # pragma: no cover
    g = None  # type: ignore

@app.before_request
def _log_request_start():  # pragma: no cover - trivial
    if g is not None:
        try:
            g._req_start_ts = time.time()
        except Exception:
            pass

@app.after_request
def _log_request_end(response):  # pragma: no cover - trivial
    try:
        start = getattr(g, '_req_start_ts', None) if g is not None else None
        dur_ms = (time.time() - start) * 1000 if start else None
        # Avoid extremely chatty logging for heartbeats if desired (keep for now)
        print(f"[HTTP] {request.method} {request.path} -> {response.status_code}{' %.1fms' % dur_ms if dur_ms is not None else ''}")
    except Exception as e:
        try:
            log_error(f"access log error: {e}")
        except Exception:
            pass
    return response

@app.teardown_request
def _log_request_teardown(exc):  # pragma: no cover - trivial
    if exc is not None:
        try:
            print(f"[HTTP][ERROR] {request.method} {request.path} raised {exc.__class__.__name__}: {exc}")
        except Exception:
            pass

class SystemState:
    def __init__(self):
        # Core runtime state
        self.started: bool = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.loop_thread: Optional[threading.Thread] = None
        self.multi_mcp: Optional[MultiMCP] = None
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.start_time: Optional[float] = None

        # Upload directory for /upload endpoint
        self.upload_dir = Path("media/uploads/api")
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        # WebSocket session channels (session_id -> channel dict)
        self.ws_channels: Dict[str, Dict[str, Any]] = {}
        self.ws_lock = threading.Lock()

STATE = SystemState()

# ----------------------- Channel Cleanup Thread --------------------
_cleanup_thread_started = False
def _start_channel_cleanup():
    global _cleanup_thread_started
    if _cleanup_thread_started:
        return
    _cleanup_thread_started = True
    def _sweeper():
        while True:
            try:
                now = time.time()
                with STATE.ws_lock:
                    to_delete = []
                    for sid, ch in list(STATE.ws_channels.items()):
                        if ch.get('connections'):
                            continue
                        last_act = ch.get('last_activity', now)
                        if now - last_act > CHANNEL_IDLE_SECONDS:
                            to_delete.append(sid)
                    for sid in to_delete:
                        STATE.ws_channels.pop(sid, None)
            except Exception as e:
                log_error(f"channel cleanup error: {e}")
            time.sleep(CHANNEL_SWEEP_INTERVAL)
    t = threading.Thread(target=_sweeper, daemon=True)
    t.start()

# ----------------------- Async Loop Management -----------------------

def _loop_thread_target(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def ensure_loop_started():
    if STATE.loop is None:
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=_loop_thread_target, args=(loop,), daemon=True)
        t.start()
        STATE.loop = loop
        STATE.loop_thread = t

# ----------------------- Utility Functions --------------------------

def _generate_session_id() -> str:
    return str(int(time.time()))[-8:]  # mimic existing pattern

def _list_leaf_nodes(context: ExecutionContextManager) -> List[str]:
    G = context.plan_graph
    return [n for n in G.nodes if n != "ROOT" and G.out_degree(n) == 0]

def _extract_latest_html_report(context: ExecutionContextManager) -> Dict[str, Any]:
    """Attempt to find or build latest HTML report.
    Strategy:
    1. Inspect FormatterAgent completed nodes for HTML-like strings; choose node with highest numeric ID or latest end_time.
    2. If found, write to media/generated/<session_id>/formatted_report_<stepID>.html (if not already saved) and return.
    3. Else look for files on disk named formatted_report*.html; pick highest numeric suffix or latest mtime.
    """
    session_id = context.plan_graph.graph['session_id']
    session_dir = Path(f"media/generated/{session_id}")
    session_dir.mkdir(parents=True, exist_ok=True)

    formatter_nodes = []
    for n, data in context.plan_graph.nodes(data=True):
        if data.get('agent') in ('FormatterAgent', 'ClarificationAgent') and data.get('status') == 'completed':
            output = data.get('output')
            html_candidate = None
            if isinstance(output, dict):
                # search for html-like content
                for k, v in output.items():
                    if isinstance(v, str) and _looks_like_html(v):
                        html_candidate = v
                        break
                if html_candidate is None:
                    nested = output.get('output')
                    if isinstance(nested, dict):
                        for k, v in nested.items():
                            if isinstance(v, str) and _looks_like_html(v):
                                html_candidate = v
                                break
            if html_candidate:
                formatter_nodes.append((n, data, html_candidate))

    def _node_numeric(node_id: str) -> int:
        try:
            if node_id.startswith('T'):
                return int(''.join(ch for ch in node_id[1:] if ch.isdigit()))
        except Exception:
            return -1
        return -1
    if formatter_nodes:
        # pick node with highest numeric id, fallback latest end_time
        formatter_nodes.sort(key=lambda tup: (_node_numeric(tup[0]), tup[1].get('end_time','')), reverse=True)
        chosen_id, chosen_data, html = formatter_nodes[0]
        report_path = session_dir / f"formatted_report_{chosen_id}.html"
        if not report_path.exists():
            report_path.write_text(html, encoding='utf-8')
        return {
            'found': True,
            'step_id': chosen_id,
            'path': str(report_path),
            'html': html
        }

    # fallback: search files
    existing = list(session_dir.glob('formatted_report*.html'))
    if existing:
        # choose by numeric part or mtime
        def _file_key(p: Path):
            stem = p.stem
            parts = stem.split('_')
            try:
                suffix = parts[-1]
                if suffix.startswith('T'):
                    return int(''.join(ch for ch in suffix[1:] if ch.isdigit()))
            except Exception:
                return int(p.stat().st_mtime)
            return int(p.stat().st_mtime)
        existing.sort(key=_file_key, reverse=True)
        latest = existing[0]
        return {
            'found': True,
            'step_id': latest.stem.split('_')[-1],
            'path': str(latest),
            'html': latest.read_text(encoding='utf-8')
        }

    return {'found': False, 'step_id': None, 'path': None, 'html': ''}

# ----------------------- WS Event Dispatch --------------------------

def _get_channel(session_id: str):
    """Return (or create) a channel data structure for a session.

    Structure:
    queue: thread-safe queue.Queue for events to send
    buffer: deque of last 500 events (for replay)
    seq: monotonically increasing sequence id
    connections: set of active ws objects
    """
    with STATE.ws_lock:
        ch = STATE.ws_channels.get(session_id)
        if not ch:
            from collections import deque
            import queue
            ch = {
                'queue': queue.Queue(),  # standard thread-safe queue
                'buffer': deque(maxlen=500),
                'seq': 0,
                'connections': set(),
                'session_id': session_id,
                'last_activity': time.time()
            }
            STATE.ws_channels[session_id] = ch
        return ch

def _truncate_payload(ev_type: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, int]:
    """Ensure payload (alone) when JSON-serialized fits under PAYLOAD_MAX_BYTES.
    Strategy: if too large, truncate large string fields, then mark truncated flag.
    Returns (possibly modified payload, truncated_flag, original_size_bytes).
    """
    try:
        encoded = json.dumps(payload, ensure_ascii=False)
        size = len(encoded.encode('utf-8'))
        if size <= PAYLOAD_MAX_BYTES:
            return payload, False, size
        # Work on a shallow copy
        work = dict(payload)
        # Identify large string fields
        str_fields = []
        for k, v in work.items():
            if isinstance(v, str) and len(v) > 512:
                str_fields.append((k, len(v)))
        # Sort largest first
        str_fields.sort(key=lambda x: x[1], reverse=True)
        for k, _ in str_fields:
            v = work[k]
            # aggressive slice proportionally until under limit
            # heuristic: keep first 4000 chars max then shrink progressively
            keep = min(4000, max(512, int(len(v) * 0.3)))
            work[k] = v[:keep] + '...'
            encoded = json.dumps(work, ensure_ascii=False)
            if len(encoded.encode('utf-8')) <= PAYLOAD_MAX_BYTES:
                return work, True, size
        # Final hard cut: serialize then slice bytes (unsafe for multibyte but acceptable dev) -> fallback
        b = json.dumps(work, ensure_ascii=False).encode('utf-8')
        if len(b) > PAYLOAD_MAX_BYTES:
            b = b[:PAYLOAD_MAX_BYTES-4] + b'...'
            try:
                # Attempt to load truncated JSON (likely broken) so wrap
                work = { 'truncated_blob': b.decode('utf-8', errors='ignore') }
            except Exception:
                work = { 'truncated_blob': '<binary>' }
        return work, True, size
    except Exception:
        return payload, False, 0

def ws_send_event(session_id: str, ev_type: str, payload: Dict[str, Any]):
    """Queue an event for all WebSocket listeners of this session.

    Safe to call from any thread.
    """
    try:
        ch = _get_channel(session_id)
        ch['seq'] += 1
        payload, truncated, original_size = _truncate_payload(ev_type, payload)
        evt = {
            'seq': ch['seq'],
            'ts': time.time(),
            'session_id': session_id,
            'type': ev_type,
            'payload': payload,
            **({'truncated': True, 'original_size': original_size} if truncated else {})
        }
        ch['buffer'].append(evt)
        ch['queue'].put_nowait(evt)
        ch['last_activity'] = time.time()
        # Track job status metadata for periodic emission
        if ev_type == 'job.status':
            ch['last_job_status'] = dict(payload)
            ch['last_job_status_emit'] = time.time()
            job_id = payload.get('job_id')
            if job_id:
                ch['current_job_id'] = job_id
                # Record job start if not set
                if 'job_started_at' not in ch:
                    job_rec = STATE.jobs.get(job_id, {})
                    ch['job_started_at'] = job_rec.get('started_at', time.time())
    except Exception as e:
        log_error(f"ws_send_event error: {e}")

def _sanitize_html_snippet(html: str, limit: int = 10_000) -> str:
    try:
        import re
        # Remove script & style blocks
        html = re.sub(r'<script.*?>.*?</script>', '', html, flags=re.IGNORECASE|re.DOTALL)
        html = re.sub(r'<style.*?>.*?</style>', '', html, flags=re.IGNORECASE|re.DOTALL)
        # Remove on* attributes (simple)
        html = re.sub(r'on[a-zA-Z]+="[^"]*"', '', html)
        # Trim
        if len(html) > limit:
            return html[:limit] + '...'
        return html
    except Exception:
        return html[:limit] if html else ''

def _drain_events_loop(ws, session_id: str, ch, last_seq: Optional[int]):
    """Blocking loop that sends queued events as JSON strings.

    Runs inside the Flask request thread for this WebSocket.
    """
    import queue
    # Optional replay with gap detection
    if last_seq is not None:
        if ch['buffer']:
            oldest_seq = ch['buffer'][0]['seq']
        else:
            oldest_seq = ch['seq']
        if last_seq > ch['seq']:
            ws_send_event(session_id, 'ws.replay.gap', {'reason': 'ahead_of_server', 'requested_seq': last_seq, 'latest_seq': ch['seq']})
        elif last_seq < oldest_seq - 1:
            ws_send_event(session_id, 'ws.replay.gap', {'reason': 'buffer_overflow', 'requested_seq': last_seq, 'oldest_available': oldest_seq, 'latest_seq': ch['seq']})
    # Replay
    last_replayed_seq = None
    if last_seq is not None:
        for ev in list(ch['buffer']):
            if ev['seq'] > last_seq:
                try:
                    ws.send(json.dumps(ev))
                    last_replayed_seq = ev['seq'] if (last_replayed_seq is None or ev['seq'] > last_replayed_seq) else last_replayed_seq
                except Exception:
                    return
    else:
        # On initial subscribe without last_seq, replay entire buffer
        for ev in list(ch['buffer']):
            try:
                ws.send(json.dumps(ev))
                last_replayed_seq = ev['seq'] if (last_replayed_seq is None or ev['seq'] > last_replayed_seq) else last_replayed_seq
            except Exception:
                return
    # Drain queue
    last_hb = time.time()
    while True:
        try:
            ev = ch['queue'].get(timeout=30)
        except queue.Empty:
            now = time.time()
            if now - last_hb >= HEARTBEAT_INTERVAL:
                # Heartbeat includes last seq
                ws_send_event(session_id, 'ws.heartbeat', {'last_seq': ch['seq']})
                last_hb = now
            # Periodic job.status refresh (every 3s) if job still running
            if 'last_job_status' in ch and ch.get('last_job_status', {}).get('state') == 'running':
                last_emit = ch.get('last_job_status_emit', 0)
                if now - last_emit >= 3:
                    js = dict(ch['last_job_status'])
                    # update elapsed
                    if 'job_started_at' in ch:
                        js['elapsed_ms'] = int((now - ch['job_started_at']) * 1000)
                    ws_send_event(session_id, 'job.status', js)
            continue
        try:
            # Suppress duplicate if already replayed
            if last_replayed_seq is not None and ev.get('seq') <= last_replayed_seq:
                continue
            ws.send(json.dumps(ev))
        except Exception:
            break

def instrument_step_event(session_id: str, kind: str, data: Dict[str, Any]):
    ws_send_event(session_id, f'step.{kind}', data)

def instrument_job_event(session_id: str, kind: str, data: Dict[str, Any]):
    ws_send_event(session_id, f'job.{kind}', data)

# ----------------------- WebSocket Endpoint -------------------------

@sock.route('/ws')
def websocket_route(ws):  # type: ignore[override]
    """WebSocket endpoint.

    Client must immediately send a JSON object: {"session_id": "...", "last_seq": <optional_int>}.
    We reply with an ack event then stream events.
    """
    try:
        first = ws.receive()
        session_id = None
        last_seq = None
        if first:
            try:
                obj = json.loads(first)
                session_id = obj.get('session_id')
                last_seq = obj.get('last_seq')
            except Exception:
                session_id = None
        if not session_id:
            try:
                ws.send(json.dumps({'type': 'ws.error', 'error': 'missing session_id'}))
            finally:
                ws.close()
            return
        ch = _get_channel(session_id)
        ch['connections'].add(ws)
        # Ack
        ws.send(json.dumps({'type': 'ws.subscribed', 'session_id': session_id, 'last_seq': last_seq, 'latest_seq': ch['seq'], 'buffer_size': len(ch['buffer']), 'buffer_cap': ch['buffer'].maxlen}))
        # Reserved future event family: clarification.request / clarification.response
        # Drain existing + live events
        _drain_events_loop(ws, session_id, ch, last_seq)
    except Exception as e:
        log_error(f"WebSocket error: {e}")
    finally:
        try:
            ch = _get_channel(session_id) if 'session_id' in locals() and session_id else None
            if ch:
                ch['connections'].discard(ws)
        except Exception:
            pass
        try:
            ws.close()
        except Exception:
            pass

def _looks_like_html(content: str) -> bool:
    if not isinstance(content, str) or len(content) < 10:
        return False
    lowered = content.lstrip()[:150].lower()
    indicators = ['<html', '<div', '<section', '<article', '<header', '<body', '<!doctype', '<h1', '<p', '<main']
    return any(ind in lowered for ind in indicators)

# ----------------------- History Endpoints (Phase 1) -------------------------

@app.get('/history/sessions')
def history_sessions():
    limit_param = request.args.get('limit')
    limit = None
    if limit_param:
        try:
            limit = int(limit_param)
        except Exception:
            limit = None
    data = list_history(limit=limit)
    return jsonify({'api_version': API_VERSION, 'count': len(data), 'sessions': data})

@app.get('/history/session/<session_id>')
def history_session_detail(session_id: str):
    detail = load_session_summary(session_id)
    if not detail:
        abort(404, description='Session not found')
    return jsonify({'api_version': API_VERSION, 'session_id': session_id, 'detail': detail})

@app.get('/history/session/<session_id>/report')
def history_session_report(session_id: str):
    html = load_session_report_html(session_id)
    if html is None:
        abort(404, description='Report not found')
    # Return raw html text (client will render in sandbox)
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

# ----------------------- Job Execution ------------------------------

async def _run_agent_job(job_id: str, session_id: str, query: str, files: List[str]):
    job = STATE.jobs[job_id]
    job['status'] = 'running'
    job['started_at'] = time.time()

    try:
        # Build file manifest
        file_manifest = []
        for fp in files:
            p = Path(fp)
            file_manifest.append({'path': str(p), 'name': p.name, 'size': p.stat().st_size})

        with STATE.lock:
            session_entry = STATE.sessions.get(session_id)
            if session_entry is None:
                # create new session
                agent_loop = AgentLoop4(STATE.multi_mcp)
                # Attach instrumentation callbacks
                def _step_start(step_id, agent, reads, writes, turn):
                    ws_send_event(session_id, 'step.start', {
                        'step_id': step_id,
                        'agent': agent,
                        'reads': reads,
                        'writes': writes,
                        'turn': turn
                    })
                def _step_end(step_id, status, duration_ms, error, output_meta, progress):
                    payload = {
                        'step_id': step_id,
                        'status': status,
                        'duration_ms': round(duration_ms, 2),
                        'error': error,
                        'output_meta': output_meta,
                    }
                    if isinstance(progress, dict):
                        # Add minimal progress snapshot
                        payload['progress'] = {
                            'completed': progress.get('completed_steps'),
                            'failed': progress.get('failed_steps'),
                            'total': progress.get('total_steps'),
                            'ratio': round((progress.get('completed_steps',0)/ max(progress.get('total_steps',1),1)), 2)
                        }
                    ws_send_event(session_id, 'step.end', payload)
                    if status == 'failed':
                        # Emit step.error event
                        kind = 'timeout' if (error and 'timeout' in str(error).lower()) else 'error'
                        ws_send_event(session_id, 'step.error', {
                            'step_id': step_id,
                            'error_kind': kind,
                            'message': (str(error) or '')[:400]
                        })
                    # Emit enriched job.status after each step
                    if isinstance(progress, dict):
                        start_at = STATE.jobs.get(job_id, {}).get('started_at')
                        elapsed_ms = int((time.time() - start_at) * 1000) if start_at else None
                        ws_send_event(session_id, 'job.status', {
                            'state': 'running',
                            'job_id': job_id,
                            'completed_steps': progress.get('completed_steps'),
                            'failed_steps': progress.get('failed_steps'),
                            'total_steps': progress.get('total_steps'),
                            'progress_ratio': round((progress.get('completed_steps',0)/ max(progress.get('total_steps',1),1)), 2),
                            **({'elapsed_ms': elapsed_ms} if elapsed_ms is not None else {})
                        })
                agent_loop.on_step_start = _step_start  # type: ignore[attr-defined]
                agent_loop.on_step_end = _step_end      # type: ignore[attr-defined]
                context = None
                session_entry = {
                    'agent_loop': agent_loop,
                    'context': context,
                    'created_at': time.time(),
                    'session_id': session_id
                }
                STATE.sessions[session_id] = session_entry
            else:
                agent_loop = session_entry['agent_loop']
                context = session_entry['context']

        # Execute (may extend existing context)
        instrument_job_event(session_id, 'status', {'state': 'running', 'job_id': job_id, 'elapsed_ms': 0})
        context = await agent_loop.run(query, file_manifest, files, context=context)
        session_entry['context'] = context

        # Collect summary & latest report
        summary = context.get_execution_summary()
        leaf_nodes = _list_leaf_nodes(context)
        report_info = _extract_latest_html_report(context)

        job['status'] = 'completed'
        job['finished_at'] = time.time()
        job['duration'] = job['finished_at'] - job['started_at']
        output_chain = context.plan_graph.graph.get('output_chain', {})
        # Leaf outputs mapping (truncated)
        leaf_outputs = {}
        for lid in leaf_nodes:
            val = output_chain.get(lid)
            if isinstance(val, (str, int, float)):
                leaf_outputs[lid] = val
            elif isinstance(val, dict):
                # shallow copy of keys only
                leaf_outputs[lid] = list(val.keys())
            else:
                leaf_outputs[lid] = str(type(val))
        job['result'] = {
            'session_id': session_id,
            'query': query,
            'leaf_nodes': leaf_nodes,
            'leaf_outputs': leaf_outputs,
            'summary': summary,
            'report': report_info,
            'output_chain_keys': list(output_chain.keys())
        }
        elapsed_ms = int((time.time() - job['started_at']) * 1000) if job.get('started_at') else None
        instrument_job_event(session_id, 'status', {
            'state': 'completed',
            'job_id': job_id,
            'completed_steps': summary.get('completed_steps'),
            'failed_steps': summary.get('failed_steps'),
            'total_steps': summary.get('total_steps'),
            'progress_ratio': round((summary.get('completed_steps',0)/ max(summary.get('total_steps',1),1)), 2),
            **({'elapsed_ms': elapsed_ms} if elapsed_ms is not None else {})
        })
        if report_info.get('found'):
            snippet = _sanitize_html_snippet(report_info.get('html','') or '')
            ws_send_event(session_id, 'report.final', {
                'step_id': report_info['step_id'],
                'path': report_info.get('path'),
                'size': len(report_info.get('html','') or ''),
                'snippet': snippet,
                'snippet_truncated': len(snippet) < len(report_info.get('html','') or ''),
                'content_type': 'text/html',
                'snippet_chars': len(snippet),
                'sanitized': True
            })
    except asyncio.TimeoutError:
        job['status'] = 'timeout'
        job['finished_at'] = time.time()
        job['error'] = 'Job exceeded time limit'
        instrument_job_event(session_id, 'status', {'state': 'timeout', 'job_id': job_id, 'elapsed_ms': int((time.time() - job['started_at']) * 1000) if job.get('started_at') else None})
        ws_send_event(session_id, 'job.error', {'job_id': job_id, 'state': 'timeout', 'error': 'Job exceeded time limit'})
    except Exception as e:
        log_error(f"Job {job_id} failed: {e}")
        job['status'] = 'failed'
        job['finished_at'] = time.time()
        job['error'] = str(e)
        instrument_job_event(session_id, 'status', {'state': 'failed', 'job_id': job_id, 'error': str(e), 'elapsed_ms': int((time.time() - job['started_at']) * 1000) if job.get('started_at') else None})
        ws_send_event(session_id, 'job.error', {'job_id': job_id, 'state': 'failed', 'error': str(e)[:400]})
    finally:
        # Drop reference to future when done
        job.pop('future', None)

# Wrapper adding timeout
async def _job_with_timeout(job_id: str, session_id: str, query: str, files: List[str]):
    await asyncio.wait_for(_run_agent_job(job_id, session_id, query, files), timeout=JOB_TIMEOUT_SECONDS)

# ----------------------- Endpoint Helpers ---------------------------

def _validate_run_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    if 'query' not in data or not data['query'].strip():
        abort(400, description='Missing query')
    files = data.get('files', []) or []
    if not isinstance(files, list):
        abort(400, description='files must be a list')
    # Abort if any file missing (requirement #4)
    missing = [f for f in files if not Path(f).exists()]
    if missing:
        abort(400, description=f"Missing files: {missing}")
    session_id = data.get('session_id')
    if session_id is not None and session_id != '' and session_id not in STATE.sessions:
        # Treat as invalid given requirement 3
        abort(404, description='Invalid session_id')
    if not session_id:
        session_id = _generate_session_id()
    return {'session_id': session_id, 'query': data['query'], 'files': files}

# ----------------------- Flask Endpoints ----------------------------

@app.post('/start')
def start_system():
    if STATE.started:
        return jsonify({'api_version': API_VERSION, 'status': 'already_started'})

    ensure_loop_started()

    server_configs = load_server_configs()
    STATE.multi_mcp = MultiMCP(server_configs)

    async def _init():
        assert STATE.multi_mcp is not None, "MultiMCP not set"
        await STATE.multi_mcp.initialize()

    assert STATE.loop is not None, "Async loop not started"
    fut = asyncio.run_coroutine_threadsafe(_init(), STATE.loop)
    fut.result()  # wait for init

    STATE.started = True
    # Launch background channel cleanup sweeper to purge idle websocket channels
    _start_channel_cleanup()
    STATE.start_time = time.time()
    return jsonify({'api_version': API_VERSION, 'status': 'started', 'tool_count': len(STATE.multi_mcp.tool_map)})

@app.get('/health')
def health():
    return jsonify({
        'api_version': API_VERSION,
        'started': STATE.started,
        'sessions': len(STATE.sessions),
        'jobs': len(STATE.jobs),
        'start_time': STATE.start_time,
        'tool_count': len(STATE.multi_mcp.tool_map) if STATE.multi_mcp else 0
    })

@app.post('/run')
def run_job():
    if not STATE.started:
        abort(400, description='System not started. Call /start first.')

    data = request.get_json(force=True, silent=False)
    payload = _validate_run_payload(data)
    session_id = payload['session_id']
    query = payload['query']
    files = payload['files']

    job_id = str(uuid.uuid4())
    STATE.jobs[job_id] = {
        'job_id': job_id,
        'session_id': session_id,
        'created_at': time.time(),
        'status': 'queued'
    }

    async def schedule():
        await _job_with_timeout(job_id, session_id, query, files)

    assert STATE.loop is not None, "Async loop not started"
    fut = asyncio.run_coroutine_threadsafe(schedule(), STATE.loop)
    STATE.jobs[job_id]['future'] = fut

    return jsonify({
        'api_version': API_VERSION,
        'job_id': job_id,
        'session_id': session_id,
        'status': 'queued'
    })

@app.get('/job/<job_id>')
def get_job(job_id: str):
    job = STATE.jobs.get(job_id)
    if not job:
        abort(404, description='Job not found')
    include_chain = request.args.get('include_output_chain', 'false').lower() == 'true'
    max_chain_items = int(request.args.get('max_chain_keys', '50'))
    resp = {
        'api_version': API_VERSION,
        'job_id': job_id,
        'status': job['status'],
        'session_id': job.get('session_id'),
        'created_at': job.get('created_at'),
        'started_at': job.get('started_at'),
        'finished_at': job.get('finished_at'),
        'duration': job.get('duration'),
        'error': job.get('error')
    }
    if job['status'] == 'completed':
        result_copy = dict(job['result'])
        if include_chain:
            # fetch context to extract output_chain
            session_id_val = job.get('session_id')
            if isinstance(session_id_val, str):
                entry = STATE.sessions.get(session_id_val, {})
                context = entry.get('context')
            else:
                context = None
            if isinstance(context, ExecutionContextManager):
                chain = context.plan_graph.graph.get('output_chain', {})  # type: ignore[arg-type]
                trimmed = {}
                for i, (k, v) in enumerate(chain.items()):
                    if i >= max_chain_items:
                        break
                    if isinstance(v, (str, int, float)):
                        trimmed[k] = v
                    elif isinstance(v, dict):
                        trimmed[k] = {subk: ('<str>' if isinstance(subv, str) and len(subv) > 120 else subv) for subk, subv in list(v.items())[:25]}
                    else:
                        trimmed[k] = str(type(v))
                result_copy['output_chain'] = trimmed
        resp['result'] = result_copy
    return jsonify(resp)

@app.post('/job/<job_id>/cancel')
def cancel_job(job_id: str):
    job = STATE.jobs.get(job_id)
    if not job:
        abort(404, description='Job not found')
    if job.get('status') in {'completed','failed','timeout','canceled'}:
        return jsonify({'api_version': API_VERSION, 'job_id': job_id, 'status': job['status']})
    fut = job.get('future')
    if fut and not fut.done():
        fut.cancel()
        job['status'] = 'canceled'
        job['finished_at'] = time.time()
        job['error'] = 'Canceled by user'
    return jsonify({'api_version': API_VERSION, 'job_id': job_id, 'status': job['status']})

@app.get('/sessions/<session_id>')
def session_info(session_id: str):
    entry = STATE.sessions.get(session_id)
    if not entry:
        abort(404, description='Session not found')
    context = entry.get('context')
    if not isinstance(context, ExecutionContextManager):
        return jsonify({'api_version': API_VERSION, 'session_id': session_id, 'status': 'empty'})
    G = context.plan_graph
    nodes = []
    for n, d in G.nodes(data=True):
        if n == 'ROOT':
            continue
        nodes.append({
            'id': n,
            'agent': d.get('agent'),
            'status': d.get('status'),
            'reads': d.get('reads', []),
            'writes': d.get('writes', []),
            'end_time': d.get('end_time')
        })
    summary = context.get_execution_summary()
    return jsonify({
        'api_version': API_VERSION,
        'session_id': session_id,
        'node_count': len(nodes),
        'nodes': nodes,
        'summary': summary
    })

@app.post('/upload')
def upload_files():
    if not STATE.started:
        abort(400, description='System not started')
    if 'files' not in request.files:
        abort(400, description='No files part in request (use multipart/form-data)')
    saved = []
    for file in request.files.getlist('files'):
        if not file or not file.filename:
            continue
        fname = secure_filename(file.filename or '')
        if not fname:
            continue
        # NOTE: upload_dir defined on SystemState.__init__
        dest = STATE.upload_dir / fname  # type: ignore[attr-defined]
        # Avoid overwrite: add suffix if exists
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            idx = 2
            while True:
                alt = STATE.upload_dir / f"{stem}_{idx}{suffix}"  # type: ignore[attr-defined]
                if not alt.exists():
                    dest = alt
                    break
                idx += 1
        file.save(dest)
        saved.append(str(dest))
    return jsonify({'api_version': API_VERSION, 'saved_files': saved, 'count': len(saved)})

@app.post('/shutdown')
def shutdown_system():
    if not STATE.started:
        return jsonify({'api_version': API_VERSION, 'status': 'not_started'})
    # Cancel running jobs
    for job_id, job in list(STATE.jobs.items()):
        fut = job.get('future')
        if fut and not fut.done():
            fut.cancel()
            job['status'] = 'canceled'
            job['finished_at'] = time.time()
            job['error'] = 'Canceled during shutdown'
    # Shutdown MultiMCP
    async def _shutdown():
        try:
            if STATE.multi_mcp:
                await STATE.multi_mcp.shutdown()
        except Exception as e:
            log_error(f'Shutdown error: {e}')
    if STATE.loop is not None:
        fut = asyncio.run_coroutine_threadsafe(_shutdown(), STATE.loop)
        try:
            fut.result(timeout=15)
        except Exception:
            pass
        # Stop loop
        STATE.loop.call_soon_threadsafe(STATE.loop.stop)
    STATE.started = False
    return jsonify({'api_version': API_VERSION, 'status': 'stopped'})

@app.get('/debug/tasks')
def debug_tasks():
    if not STATE.started or STATE.loop is None:
        abort(400, description="System not started")
    tasks = []
    for t in asyncio.all_tasks(loop=STATE.loop):
        tasks.append({
            "repr": repr(t),
            "done": t.done(),
            "coro": getattr(t.get_coro(), "__name__", str(t.get_coro())),
            "cr_frame": bool(getattr(t.get_coro(), "cr_frame", None))
        })
    return jsonify({"tasks": tasks, "count": len(tasks)})

# --------------- Convenience Run ---------------
if __name__ == '__main__':
    # Run Flask app
    app.run(host='0.0.0.0', port=8000, debug=False)
