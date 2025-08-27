import json, time
from pathlib import Path
from typing import List, Dict, Any, Optional

MEMORY_DIR = Path('memory')
INDEX_DIR = MEMORY_DIR / 'session_summaries_index'

# Heuristic patterns
SUMMARY_GLOB = '**/session_*.json'
REPORT_PREFIX = 'session_'
REPORT_SUFFIX = '_report.html'

_DEF_LIMIT = 250

_cached_index: Dict[str, Any] = {
    'ts': 0,
    'limit': None,
    'data': []
}
_CACHE_TTL = 60  # seconds

def _safe_int(v, default=None):
    try:
        return int(v)
    except Exception:
        return default


def _scan_sessions(limit: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not INDEX_DIR.exists():
        return results
    # Walk index dir for JSON session files
    for p in sorted(INDEX_DIR.glob(SUMMARY_GLOB), key=lambda x: x.stat().st_mtime, reverse=True):
        name = p.name  # session_<id>.json
        if not name.startswith('session_') or not name.endswith('.json'):
            continue
        session_id = name[len('session_'):-len('.json')]
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        started_at = raw.get('created_at') or raw.get('start_time') or _safe_int(raw.get('timestamp'))
        finished_at = raw.get('finished_at') or raw.get('end_time')
        convo = raw.get('conversationHistory') or raw.get('conversation_history') or []
        first_user = ''
        for turn in convo:
            user_txt = turn.get('transcription') or turn.get('user') or turn.get('user_text')
            if user_txt:
                first_user = user_txt.strip()[:160]
                break
        ai_preview = ''
        for turn in convo:
            ai_txt = turn.get('ai_response') or turn.get('assistant') or turn.get('ai')
            if ai_txt:
                ai_preview = ai_txt.strip()[:160]
                break
        report_file = MEMORY_DIR / f'{REPORT_PREFIX}{session_id}{REPORT_SUFFIX}'
        report_available = report_file.exists()
        results.append({
            'session_id': session_id,
            'started_at': started_at,
            'finished_at': finished_at,
            'user_preview': first_user,
            'ai_preview': ai_preview,
            'turns': len(convo),
            'report_available': report_available,
            'size_bytes': p.stat().st_size
        })
        if len(results) >= limit:
            break
    return results

def list_history(limit: Optional[int] = None, force: bool = False) -> List[Dict[str, Any]]:
    lim = limit or _DEF_LIMIT
    now = time.time()
    if not force and _cached_index['data'] and _cached_index['limit'] == lim and now - _cached_index['ts'] < _CACHE_TTL:
        return _cached_index['data']
    data = _scan_sessions(lim)
    _cached_index.update({'ts': now, 'limit': lim, 'data': data})
    return data

def load_session_summary(session_id: str) -> Optional[Dict[str, Any]]:
    # Search direct path(s)
    patterns = list(INDEX_DIR.glob(f'**/session_{session_id}.json'))
    if not patterns:
        return None
    p = patterns[0]
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None

def load_session_report_html(session_id: str) -> Optional[str]:
    p = MEMORY_DIR / f'{REPORT_PREFIX}{session_id}{REPORT_SUFFIX}'
    if not p.exists():
        return None
    try:
        return p.read_text(encoding='utf-8')
    except Exception:
        return None
