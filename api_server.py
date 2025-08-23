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
import os
import uuid
import time
import threading
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify, abort

# Local imports (reuse existing code)
from main import load_server_configs  # re-use config loader
from mcp_servers.multiMCP import MultiMCP
from agentLoop.flow import AgentLoop4
from agentLoop.contextManager import ExecutionContextManager
from utils.utils import log_step, log_error

API_VERSION = "v1"
JOB_TIMEOUT_SECONDS = 120

app = Flask(__name__)

class SystemState:
    def __init__(self):
        self.started: bool = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.loop_thread: Optional[threading.Thread] = None
        self.multi_mcp: Optional[MultiMCP] = None
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.start_time: Optional[float] = None

STATE = SystemState()

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
        if data.get('agent') == 'FormatterAgent' and data.get('status') == 'completed':
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
            pass
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
                pass
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

def _looks_like_html(content: str) -> bool:
    if not isinstance(content, str) or len(content) < 10:
        return False
    lowered = content.lstrip()[:150].lower()
    indicators = ['<html', '<div', '<section', '<article', '<header', '<body', '<!doctype', '<h1', '<p', '<main']
    return any(ind in lowered for ind in indicators)

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
        context = await agent_loop.run(query, file_manifest, files, context=context)
        session_entry['context'] = context

        # Collect summary & latest report
        summary = context.get_execution_summary()
        leaf_nodes = _list_leaf_nodes(context)
        report_info = _extract_latest_html_report(context)

        job['status'] = 'completed'
        job['finished_at'] = time.time()
        job['duration'] = job['finished_at'] - job['started_at']
        job['result'] = {
            'session_id': session_id,
            'query': query,
            'leaf_nodes': leaf_nodes,
            'summary': summary,
            'report': report_info,
        }
    except asyncio.TimeoutError:
        job['status'] = 'timeout'
        job['finished_at'] = time.time()
        job['error'] = 'Job exceeded time limit'
    except Exception as e:
        log_error(f"Job {job_id} failed: {e}")
        job['status'] = 'failed'
        job['finished_at'] = time.time()
        job['error'] = str(e)

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
        await STATE.multi_mcp.initialize()

    fut = asyncio.run_coroutine_threadsafe(_init(), STATE.loop)
    fut.result()  # wait for init

    STATE.started = True
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

    asyncio.run_coroutine_threadsafe(schedule(), STATE.loop)

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
        resp['result'] = job['result']
    return jsonify(resp)

@app.get('/sessions/<session_id>')
def session_info(session_id: str):
    entry = STATE.sessions.get(session_id)
    if not entry:
        abort(404, description='Session not found')
    context: ExecutionContextManager = entry.get('context')
    if not context:
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

# --------------- Convenience Run ---------------
if __name__ == '__main__':
    # Run Flask app
    app.run(host='0.0.0.0', port=8000, debug=True)
