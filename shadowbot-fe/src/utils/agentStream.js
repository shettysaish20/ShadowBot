/* Agent WebSocket + REST orchestration for ShadowBot
 * Phase 2 implementation.
 * Plain JS (ES module) for Electron renderer.
 */

// Backend URL (local)
const DEFAULT_BASE_URL = 'http://localhost:8000';

// Backend URL (AWS)
// const DEFAULT_BASE_URL = 'http://3.6.40.89:5000'

// Internal state (single active session per desktop client)
const _state = {
    baseUrl: DEFAULT_BASE_URL,
    sessionId: null,
    jobId: null,
    ws: null,
    wsUrl: null,
    connected: false,
    connecting: false,
    lastSeq: null,
    lastHeartbeatAt: 0,
    reconnectAttempts: 0,
    maxReconnectDelayMs: 15000,
    heartbeatIntervalSec: 15,
    heartbeatTimeoutSec: 30,
    closedManually: false,
    // Aggregated runtime data
    job: null, // {state, progress, elapsed_ms, ...}
    steps: {}, // step_id -> {start, end, status, duration_ms, error, output_meta, progress}
    report: null, // {path, snippet, ...}
    errors: [],
    gap: null,
    eventLog: [], // truncated recent events (diagnostics)
    subscribers: new Set(),
    connectionStatus: 'idle', // idle|connecting|connected|reconnecting|stalled|closed|error
    lastEventAt: 0,
    lastError: null,
    nextReconnectDelayMs: 0,
    debug: true,
};

function _notify() {
    const snapshot = getSnapshot();
    _state.subscribers.forEach(fn => {
        try { fn(snapshot); } catch (e) { /* ignore */ }
    });
}

function _debug(msg, meta) {
    if (_state.debug) {
        console.debug('[agentStream]', msg, meta || '');
    }
}

export function setDebug(v = true) { _state.debug = !!v; }

export function getSnapshot() {
    return {
        baseUrl: _state.baseUrl,
        sessionId: _state.sessionId,
        jobId: _state.jobId,
        connected: _state.connected,
        lastSeq: _state.lastSeq,
        lastHeartbeatAt: _state.lastHeartbeatAt,
        job: _state.job,
        steps: { ..._state.steps },
        report: _state.report,
        errors: [..._state.errors],
        gap: _state.gap,
        eventCount: _state.eventLog.length,
        connectionStatus: _state.connectionStatus,
        lastEventAt: _state.lastEventAt,
        reconnectAttempts: _state.reconnectAttempts,
        nextReconnectDelayMs: _state.nextReconnectDelayMs,
        lastError: _state.lastError,
    };
}

export function subscribe(listener) {
    _state.subscribers.add(listener);
    // immediate push
    try { listener(getSnapshot()); } catch (_) { }
    return () => _state.subscribers.delete(listener);
}

function _logEvent(ev) {
    _state.eventLog.push(ev);
    if (_state.eventLog.length > 500) _state.eventLog.shift();
}

async function ensureBackendStarted() {
    const healthUrl = `${_state.baseUrl}/health`;
    try {
        _debug('Checking backend health', healthUrl);
        const r = await fetch(healthUrl);
        if (r.ok) {
            const data = await r.json();
            if (data.started) {
                _debug('Backend server is already running');
                return data;
            }
        }
        _debug('Backend health check failed or server not started');
    } catch (e) {
        _debug('Backend health check failed with error', e.message);
    }
    
    // Try start
    try {
        const startUrl = `${_state.baseUrl}/start`;
        _debug('Attempting to start backend server', startUrl);
        const sr = await fetch(startUrl, { method: 'POST' });
        if (!sr.ok) {
            throw new Error(`Start request failed with status: ${sr.status}`);
        }
        _debug('Backend server started successfully');
        return sr.json();
    } catch (e) {
        _debug('Failed to start backend server', e.message);
        throw new Error(`Failed to start backend server: ${e.message}`);
    }
}

export async function configure(opts = {}) {
    if (opts.baseUrl) _state.baseUrl = opts.baseUrl.replace(/\/$/, '');
    
    // Try to start backend but don't fail if it's not available during initial configure
    try {
        await ensureBackendStarted();
        _debug('Backend server started during configuration');
    } catch (e) {
        _debug('Backend server not available during configuration, will retry when needed', e);
        // Don't throw error - let it fail gracefully and retry later when actually needed
    }
    
    _notify();
}

// -------------------- Image Upload --------------------

export async function uploadImages(images) {
    if (!images || images.length === 0) {
        _debug('No images to upload');
        return [];
    }
    
    _debug('Uploading images', { count: images.length });
    const formData = new FormData();
    
    for (let i = 0; i < images.length; i++) {
        const image = images[i];
        let blob;
        
        if (image instanceof Blob) {
            blob = image;
        } else if (typeof image === 'string') {
            // Assume base64 data
            const base64Data = image.includes(',') ? image.split(',')[1] : image;
            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);
            for (let j = 0; j < binaryString.length; j++) {
                bytes[j] = binaryString.charCodeAt(j);
            }
            blob = new Blob([bytes], { type: 'image/jpeg' });
        } else {
            throw new Error(`Unsupported image format at index ${i}`);
        }
        
        const filename = `screenshot_${Date.now()}_${i}.jpg`;
        formData.append('files', blob, filename);
        _debug('Added image to upload', { filename, size: blob.size });
    }
    
    const url = `${_state.baseUrl}/upload`;
    _debug('Uploading to', url);
    
    const r = await fetch(url, {
        method: 'POST',
        body: formData
    });
    
    if (!r.ok) {
        const errorText = await r.text();
        throw new Error(`Upload failed: ${r.status} - ${errorText}`);
    }
    
    const data = await r.json();
    _debug('Upload successful', data);
    return data.saved_files || [];
}

// -------------------- Job Submission --------------------

export async function runJob(query, files = [], profile = null, images = []) {
    if (!query || !query.trim()) throw new Error('Empty query');
    // Prevent concurrent job for same session
    if (_state.job && _state.job.state === 'running') {
        throw new Error('Job already running');
    }
    
    // Only ensure backend is started if we have images/screenshots to upload
    if (images && images.length > 0) {
        try {
            await ensureBackendStarted();
            _debug('Backend server is ready for screenshot query');
        } catch (e) {
            _debug('Failed to start backend server for screenshot query', e);
            throw new Error(`Backend server not available for screenshot query: ${e.message}`);
        }
    }
    
    // Upload images to backend if provided
    let imageFiles = [];
    if (images && images.length > 0) {
        try {
            imageFiles = await uploadImages(images);
            _debug('Images uploaded', { count: imageFiles.length, paths: imageFiles });
        } catch (e) {
            _debug('Image upload failed', e);
            throw new Error(`Image upload failed: ${e.message}`);
        }
    }
    
    // Combine regular files with uploaded image files
    const allFiles = [...files, ...imageFiles];
    
    // Use existing session or null -> server generates
    const payload = { query, files: allFiles };
    if (_state.sessionId) payload.session_id = _state.sessionId;
    if (profile) payload.profile = profile; // new profile parameter
    const url = `${_state.baseUrl}/run`;
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error(`Run failed: ${r.status}`);
    const data = await r.json();
    _state.sessionId = data.session_id;
    _state.jobId = data.job_id;
    // Reset per-job state
    _state.job = { state: 'queued', job_id: _state.jobId, profile: data.profile };
    _state.steps = {};
    _state.report = null;
    _state.errors = [];
    _state.gap = null;
    _notify();
    // Establish / refresh WS
    _connectWebSocket();
    return data;
}

export async function cancelJob() {
    if (!_state.jobId) return false;
    if (!_state.job || ['completed', 'failed', 'timeout', 'canceled'].includes(_state.job.state)) return false;
    try {
        const url = `${_state.baseUrl}/job/${_state.jobId}/cancel`;
        const r = await fetch(url, { method: 'POST' });
        if (r.ok) {
            const data = await r.json();
            // Update local job state
            if (_state.job) _state.job.state = data.status;
            _notify();
            return true;
        }
    } catch (e) {
        _state.errors.push({ type: 'cancel.error', message: String(e) });
    }
    return false;
}

export async function retryLastJob() {
    if (!_state.job || _state.job.state !== 'failed') {
        _debug('No failed job to retry');
        return false;
    }
    
    try {
        _debug('Retrying last failed job');
        
        // Reset job state for retry
        _state.job.state = 'retrying';
        _state.errors = [];
        _state.lastError = null;
        _notify();
        
        // Restart the WebSocket connection to trigger retry
        _closeWebSocket();
        _connectWebSocket();
        
        return true;
    } catch (e) {
        _debug('retryLastJob error', e);
        return false;
    }
}

// -------------------- WebSocket Handling --------------------

function _computeWsUrl() {
    const http = _state.baseUrl;
    const wsProto = http.startsWith('https') ? 'wss' : 'ws';
    return http.replace(/^https?/, wsProto) + '/ws';
}

function _connectWebSocket() {
    if (!_state.sessionId) return;
    if (_state.connecting || (_state.connected && _state.ws && _state.ws.readyState === WebSocket.OPEN)) return;
    _state.connecting = true;
    _state.wsUrl = _computeWsUrl();
    const ws = new WebSocket(_state.wsUrl);
    _state.ws = ws;
    _state.closedManually = false;
    _state.connectionStatus = _state.reconnectAttempts ? 'reconnecting' : 'connecting';
    _debug('WS connecting', { url: _state.wsUrl, attempt: _state.reconnectAttempts });

    ws.onopen = () => {
        _state.connected = true;
        _state.connecting = false;
        _state.reconnectAttempts = 0;
        _state.connectionStatus = 'connected';
        _debug('WS open');
        // Handshake
        const hello = { session_id: _state.sessionId };
        if (_state.lastSeq != null) hello.last_seq = _state.lastSeq;
        ws.send(JSON.stringify(hello));
        _notify();
    };

    ws.onmessage = (evt) => {
        let data;
        try { data = JSON.parse(evt.data); } catch { return; }
        _handleEvent(data);
    };

    ws.onclose = () => {
        _state.connected = false;
        _state.connectionStatus = _state.closedManually ? 'closed' : 'error';
        _debug('WS close', { closedManually: _state.closedManually });
        _notify();
        if (!_state.closedManually && _state.sessionId) {
            _scheduleReconnect();
        }
    };

    ws.onerror = (e) => { _state.lastError = String(e.message || e); _debug('WS error', e); };
}

function _scheduleReconnect() {
    _state.reconnectAttempts += 1;
    const delay = Math.min(_state.maxReconnectDelayMs, 1000 * Math.pow(2, _state.reconnectAttempts - 1));
    _state.connectionStatus = 'reconnecting';
    _state.nextReconnectDelayMs = delay;
    _debug('Scheduling reconnect', { delay, attempts: _state.reconnectAttempts });
    setTimeout(() => {
        if (_state.connected) return;
        _connectWebSocket();
    }, delay);
}

function _handleEvent(ev) {
    _state.lastEventAt = Date.now();
    _logEvent(ev);
    if (typeof ev.seq === 'number') {
        _state.lastSeq = ev.seq;
    }
    const t = ev.type;
    switch (t) {
        case 'ws.subscribed':
            // nothing extra
            _debug('event:ws.subscribed', ev);
            break;
        case 'ws.heartbeat':
            _state.lastHeartbeatAt = Date.now();
            _state.connectionStatus = 'connected'; // clear stalled if recovered
            _debug('event:ws.heartbeat');
            break;
        case 'ws.replay.gap':
            _state.gap = ev.payload || ev;
            _debug('event:ws.replay.gap', ev.payload||ev);
            break;
        case 'job.status':
            _debug('event:job.status', ev.payload);
            _ingestJobStatus(ev.payload);
            break;
        case 'job.error':
            _state.errors.push({ type: 'job.error', ...ev.payload });
            if (_state.job) _state.job.state = ev.payload.state || 'failed';
            _debug('event:job.error', ev.payload);
            
            // Display user-friendly error message with specific handling for awaiting_execution
            const errorMsg = ev.payload.error || ev.payload.message || ev.payload.state || 'Unknown error';
            const jobId = ev.payload.job_id || _state.jobId || 'unknown';
            
            if (errorMsg === 'awaiting_execution') {
                console.error(`❌ Job ${jobId} failed: Job timed out while waiting for execution. The backend executor may be overloaded or unavailable.`);
                _state.lastError = 'Backend executor unavailable - job timed out in queue';
            } else {
                console.error(`❌ Job ${jobId} failed: ${errorMsg}`);
                _state.lastError = errorMsg;
            }
            break;
        case 'step.start':
            _debug('event:step.start', ev.payload);
            _ingestStepStart(ev.payload);
            break;
        case 'step.end':
            _debug('event:step.end', ev.payload);
            _ingestStepEnd(ev.payload);
            break;
        case 'step.error':
            _state.errors.push({ type: 'step.error', ...ev.payload });
            _debug('event:step.error', ev.payload);
            break;
        case 'report.final':
            _state.report = ev.payload;
            _debug('event:report.final', ev.payload);
            break;
        default:
            // ignore unknown
            _debug('event:unknown', ev);
            break;
    }
    _notify();
}

function _ingestJobStatus(p) {
    if (!_state.job || _state.job.job_id !== p.job_id) {
        _state.job = { job_id: p.job_id };
    }
    Object.assign(_state.job, p);
    if (p.state && ['completed', 'failed', 'canceled', 'timeout'].includes(p.state)) {
        // terminal
    }
}

function _ingestStepStart(p) {
    const id = p.step_id;
    if (!_state.steps[id]) _state.steps[id] = { step_id: id };
    Object.assign(_state.steps[id], { status: 'running', start: Date.now(), agent: p.agent, reads: p.reads, writes: p.writes, turn: p.turn });
}

function _ingestStepEnd(p) {
    const id = p.step_id;
    if (!_state.steps[id]) _state.steps[id] = { step_id: id };
    Object.assign(_state.steps[id], {
        status: p.status,
        end: Date.now(),
        duration_ms: p.duration_ms,
        error: p.error,
        output_meta: p.output_meta,
        progress: p.progress,
    });
}

// Heartbeat watchdog
setInterval(() => {
    if (!_state.connected) return;
    if (!_state.lastHeartbeatAt) return;
    const since = (Date.now() - _state.lastHeartbeatAt) / 1000;
    if (since > _state.heartbeatTimeoutSec) {
        _state.connectionStatus = 'stalled';
        _debug('Heartbeat stalled, closing to trigger reconnect', { since });
        try { _state.ws && _state.ws.close(); } catch (_) { }
    }
}, 5000);

// Public API to force disconnect (dev/testing)
export function forceDisconnect() {
    if (_state.ws) {
        _state.closedManually = true;
        try { _state.ws.close(); } catch (_) { }
    }
}

export function forceReconnect() {
    if (_state.ws) { try { _state.closedManually = true; _state.ws.close(); } catch (_) { } }
    _state.closedManually = false;
    _state.reconnectAttempts = 0;
    _state.connectionStatus = 'connecting';
    _connectWebSocket();
}

export function getLastEvents(count = 50) {
    return _state.eventLog.slice(-count);
}

export function currentSessionId() { return _state.sessionId; }
export function currentJobId() { return _state.jobId; }

// Attach to window for debugging (optional)
if (typeof window !== 'undefined') {
    window.shadowAgent = {
        configure,
        runJob,
        cancelJob,
        subscribe,
        getSnapshot,
        getLastEvents,
        forceDisconnect,
        setDebug,
        forceReconnect,
    };
}

// -------------------- Session Rehydration / Attach --------------------
// Adopt an existing historic session (rehydrated via backend) without starting a new job.
// Expected payload shape from /sessions/<id>/rehydrate:
// { session_id, status:'rehydrated'|'already_loaded', original_query, queries, summary, report? }
export async function rehydrateSession(sessionId) {
    if (!sessionId) throw new Error('sessionId required');
    // Ensure backend started
    await ensureBackendStarted();
    const url = `${_state.baseUrl}/sessions/${encodeURIComponent(sessionId)}/rehydrate`;
    const r = await fetch(url, { method: 'POST' });
    if (!r.ok) throw new Error(`rehydrate failed: ${r.status}`);
    const data = await r.json();
    attachSession(data);
    return data;
}

export function attachSession(data) {
    if (!data || !data.session_id) throw new Error('Invalid rehydrate payload');
    // Close any existing WS (fresh subscription will replay buffer if any)
    if (_state.ws) { try { _state.closedManually = true; _state.ws.close(); } catch (_) { } }
    _state.sessionId = data.session_id;
    _state.jobId = null; // no active job yet
    _state.job = null;   // job state resets until user sends a new query
    _state.steps = {};   // steps will repopulate on future runs; existing historic steps visible via history endpoint
    // If report snippet provided, store it
    if (data.report && data.report.snippet) {
        _state.report = {
            snippet: data.report.snippet,
            snippet_truncated: data.report.snippet_truncated,
            size: data.report.size,
            sanitized: data.report.sanitized,
            restored: true
        };
    } else {
        _state.report = null;
    }
    // Reset sequencing so WS events start fresh
    _state.lastSeq = null;
    _state.errors = [];
    _state.gap = null;
    _state.eventLog = [];
    _notify();
    _connectWebSocket();
}

// Attach for debugging
if (typeof window !== 'undefined' && window.shadowAgent) {
    Object.assign(window.shadowAgent, { rehydrateSession, attachSession });
}