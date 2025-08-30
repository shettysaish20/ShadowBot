"""High-level WebSocket client helper for ShadowBot streaming events.

Features:
- Auto reconnect with exponential backoff
- Sequence tracking & duplicate suppression
- Replay (last_seq resume) + gap detection handling
- Heartbeat / liveness monitoring
- Aggregated job + step state snapshot
- Event subscription hooks + awaitable completion

Usage:
    from client.shadow_ws_client import ShadowWSClient
    c = ShadowWSClient(session_id, base_url="ws://127.0.0.1:8000/ws")
    c.on('job.status', lambda ev: print('Progress', ev['payload'].get('progress_ratio')))
    c.connect()
    c.wait_for_completion()

Threading Model:
- A background thread runs recv loop
- Callbacks executed in that thread; keep them fast
- Public snapshot methods are thread-safe
"""
from __future__ import annotations
import threading, time, json, random, sys
from typing import Callable, Dict, Any, Optional, List, DefaultDict
from collections import defaultdict

try:
    from websocket import create_connection, WebSocketException
except Exception:  # pragma: no cover - dependency missing
    create_connection = None  # type: ignore
    WebSocketException = Exception  # type: ignore

EventHandler = Callable[[Dict[str, Any]], None]

class ShadowWSClient:
    def __init__(
        self,
        session_id: str,
        base_url: str = "ws://127.0.0.1:8000/ws",
        auto_reconnect: bool = True,
        max_backoff: float = 30.0,
        heartbeat_stale_seconds: float = 45.0,
        coalesce_job_status_ms: int = 0,
    ) -> None:
        self.session_id = session_id
        self.base_url = base_url
        self.auto_reconnect = auto_reconnect
        self.max_backoff = max_backoff
        self.heartbeat_stale_seconds = heartbeat_stale_seconds
        self.coalesce_job_status_ms = coalesce_job_status_ms

        self._ws = None
        self._recv_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()

        self._listeners: DefaultDict[str, List[EventHandler]] = defaultdict(list)
        self._wildcard: List[EventHandler] = []

        self.last_seq: int = 0
        self._job: Optional[Dict[str, Any]] = None
        self._steps: Dict[str, Dict[str, Any]] = {}
        self._report: Optional[Dict[str, Any]] = None
        self._last_heartbeat_ts: float = 0.0
        self._reconnect_attempt: int = 0
        self._lock = threading.RLock()
        self._completion_event = threading.Event()
        self._desync = False
        self._requires_refresh = False
        self._pending_job_status: Optional[Dict[str, Any]] = None
        self._pending_job_status_deadline: float = 0

    # ---------------- Public API ----------------
    def on(self, event_type: str, handler: EventHandler):
        if event_type == '*':
            self._wildcard.append(handler)
        else:
            self._listeners[event_type].append(handler)

    # Shorthand helpers
    def on_step_start(self, handler: EventHandler): self.on('step.start', handler)
    def on_step_end(self, handler: EventHandler): self.on('step.end', handler)
    def on_job_status(self, handler: EventHandler): self.on('job.status', handler)
    def on_report_final(self, handler: EventHandler): self.on('report.final', handler)
    def on_step_error(self, handler: EventHandler): self.on('step.error', handler)
    def on_job_error(self, handler: EventHandler): self.on('job.error', handler)

    def connect(self, blocking: bool = False, timeout: Optional[float] = 10):
        if self._recv_thread and self._recv_thread.is_alive():  # already running
            return
        self._stop_event.clear()
        self._recv_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._recv_thread.start()
        if blocking:
            started = self._connected_event.wait(timeout)
            if not started:
                raise TimeoutError("WebSocket connection not established in time")

    def close(self):
        self.auto_reconnect = False
        self._stop_event.set()
        if self._ws:
            try: self._ws.close()
            except Exception: pass

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        return self._completion_event.wait(timeout)

    def get_job_status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._job) if self._job else None

    def get_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            s = self._steps.get(step_id)
            return dict(s) if s else None

    def list_steps(self) -> List[str]:
        with self._lock:
            return list(self._steps.keys())

    def is_stale(self) -> bool:
        return (time.time() - self._last_heartbeat_ts) > self.heartbeat_stale_seconds if self._last_heartbeat_ts else False

    def is_desynced(self) -> bool:
        return self._desync

    def requires_refresh(self) -> bool:
        return self._requires_refresh

    # ---------------- Internal Loop ----------------
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._connect_once()
                self._recv_forever()
            except Exception as e:  # noqa
                self._dispatch_internal_error(str(e))
            finally:
                if self._stop_event.is_set() or not self.auto_reconnect:
                    break
                self._schedule_reconnect_delay()

    def _connect_once(self):
        if create_connection is None:
            raise RuntimeError("websocket-client not installed")
        params: Dict[str, Any] = {"session_id": self.session_id}
        if self.last_seq:
            params["last_seq"] = int(self.last_seq)
        self._ws = create_connection(self.base_url, timeout=10)
        self._ws.send(json.dumps(params))
        self._connected_event.set()
        self._reconnect_attempt = 0

    def _recv_forever(self):
        while not self._stop_event.is_set():
            if self._ws is None:
                break
            try:
                raw = self._ws.recv()
            except Exception:
                break
            if not raw:
                break
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            self._handle_event(ev)
            # flush coalesced job.status if needed
            self._maybe_flush_coalesced()

    def _schedule_reconnect_delay(self):
        self._reconnect_attempt += 1
        backoff = min(self.max_backoff, (2 ** (self._reconnect_attempt - 1)))
        backoff = backoff + random.uniform(0, 0.25 * backoff)
        time.sleep(backoff)

    # ---------------- Event Processing ----------------
    def _handle_event(self, ev: Dict[str, Any]):
        etype = ev.get('type')
        if etype == 'ws.subscribed':
            # ack, update last_seq baseline if provided
            latest_seq = ev.get('latest_seq')
            if latest_seq is not None and self.last_seq > latest_seq:
                # server behind client (unlikely) treat as desync
                self._desync = True
            return
        if 'seq' in ev:
            seq = ev['seq']
            if seq <= self.last_seq:
                return  # duplicate/replayed
            if seq > self.last_seq + 1:
                # gap detected; rely on ws.replay.gap events
                self._desync = True
            self.last_seq = seq
        if etype == 'ws.replay.gap':
            reason = ev.get('payload', {}).get('reason') if isinstance(ev.get('payload'), dict) else ev.get('payload', {}).get('reason')
            if reason == 'buffer_overflow':
                self._requires_refresh = True
            return self._dispatch(ev)
        if etype == 'ws.heartbeat':
            self._last_heartbeat_ts = time.time()
            return self._dispatch(ev)
        if etype == 'job.status':
            self._ingest_job_status(ev)
            return
        if etype == 'step.start':
            self._ingest_step_start(ev)
            return
        if etype == 'step.end':
            self._ingest_step_end(ev)
            return
        if etype == 'report.final':
            with self._lock:
                self._report = ev['payload']
            return self._dispatch(ev)
        if etype in ('step.error','job.error'):
            return self._dispatch(ev)
        # default dispatch
        self._dispatch(ev)

    def _ingest_job_status(self, ev: Dict[str, Any]):
        payload = ev.get('payload', {})
        with self._lock:
            # Coalescing logic
            if self.coalesce_job_status_ms > 0:
                self._pending_job_status = ev
                self._pending_job_status_deadline = time.time() + (self.coalesce_job_status_ms / 1000.0)
            else:
                self._job = payload
        # Dispatch immediate if not coalescing
        if self.coalesce_job_status_ms == 0:
            self._dispatch(ev)
        # Completion detection
        state = payload.get('state')
        if state in ('completed','failed','timeout','canceled'):
            self._completion_event.set()

    def _maybe_flush_coalesced(self):
        if self.coalesce_job_status_ms == 0:
            return
        if not self._pending_job_status:
            return
        if time.time() >= self._pending_job_status_deadline:
            with self._lock:
                ev = self._pending_job_status
                self._job = ev.get('payload', {})
                self._pending_job_status = None
            self._dispatch(ev)
            st = self._job.get('state') if self._job else None
            if st in ('completed','failed','timeout','canceled'):
                self._completion_event.set()

    def _ingest_step_start(self, ev: Dict[str, Any]):
        p = ev.get('payload', {})
        sid = p.get('step_id')
        if sid:
            with self._lock:
                self._steps.setdefault(sid, {}).update({
                    'status': 'running',
                    'agent': p.get('agent'),
                    'reads': p.get('reads'),
                    'writes': p.get('writes'),
                    'turn': p.get('turn'),
                    'start_seq': ev.get('seq')
                })
        self._dispatch(ev)

    def _ingest_step_end(self, ev: Dict[str, Any]):
        p = ev.get('payload', {})
        sid = p.get('step_id')
        if sid:
            with self._lock:
                step = self._steps.setdefault(sid, {})
                step.update({
                    'status': p.get('status'),
                    'duration_ms': p.get('duration_ms'),
                    'error': p.get('error'),
                    'output_meta': p.get('output_meta'),
                    'progress_at_end': p.get('progress'),
                    'end_seq': ev.get('seq')
                })
        self._dispatch(ev)

    def _dispatch_internal_error(self, message: str):  # internal helper
        ev = {'type': 'client.internal_error', 'payload': {'message': message}}
        self._dispatch(ev)

    def _dispatch(self, ev: Dict[str, Any]):
        etype = ev.get('type')
        # Wildcard first
        for h in list(self._wildcard):
            try: h(ev)
            except Exception: pass
        # Specific
        key = etype if isinstance(etype, str) else ''
        for h in list(self._listeners.get(key, [])):
            try: h(ev)
            except Exception: pass

    # Convenience
    def percent_complete(self) -> Optional[int]:
        j = self.get_job_status()
        if not j: return None
        pr = j.get('progress_ratio')
        if pr is None: return None
        try: return int(pr * 100)
        except Exception: return None

    def job_completed(self) -> bool:
        j = self.get_job_status()
        return bool(j and j.get('state') == 'completed')

    def job_failed(self) -> bool:
        j = self.get_job_status()
        return bool(j and j.get('state') in ('failed','timeout'))

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'session_id': self.session_id,
                'last_seq': self.last_seq,
                'job': dict(self._job) if self._job else None,
                'steps': {k: dict(v) for k, v in self._steps.items()},
                'report': dict(self._report) if self._report else None,
                'desync': self._desync,
                'requires_refresh': self._requires_refresh,
                'stale': self.is_stale()
            }

if __name__ == '__main__':  # basic manual test
    if len(sys.argv) < 2:
        print('Usage: python -m client.shadow_ws_client <session_id> [ws_url]')
        sys.exit(1)
    sess = sys.argv[1]
    url = sys.argv[2] if len(sys.argv) > 2 else 'ws://127.0.0.1:8000/ws'
    c = ShadowWSClient(sess, base_url=url)
    c.on('*', lambda e: print('EV', e.get('type'), e.get('payload', {}) if isinstance(e.get('payload'), dict) else ''))
    c.connect(blocking=True)
    c.wait_for_completion(120)
    print('FINAL SUMMARY', json.dumps(c.summary(), indent=2))
