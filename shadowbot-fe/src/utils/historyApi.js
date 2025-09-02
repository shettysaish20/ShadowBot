// Backend history API helper
// Plain JS helper for listing and loading historic sessions persisted on backend.

// Backend URL (local)
let _baseUrl = 'http://localhost:8000';

// Backend URL (AWS)
// let _baseUrl = 'http://3.6.40.89:5000'

export function setHistoryBaseUrl(url) {
  if (url) _baseUrl = url.replace(/\/$/, '');
}

export async function listHistorySessions(limit = 100) {
  const url = `${_baseUrl}/history/sessions?limit=${encodeURIComponent(limit)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`history sessions failed: ${r.status}`);
  return r.json();
}

export async function getHistorySessionDetail(sessionId) {
  const url = `${_baseUrl}/history/session/${encodeURIComponent(sessionId)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`history detail failed: ${r.status}`);
  return r.json();
}

export async function getHistoryReportHtml(sessionId) {
  const url = `${_baseUrl}/history/session/${encodeURIComponent(sessionId)}/report`;
  const r = await fetch(url);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`history report failed: ${r.status}`);
  return r.text();
}
