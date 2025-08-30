import json, time
from websocket import create_connection
import requests

base = "http://127.0.0.1:8000"
requests.post(f"{base}/start")
resp = requests.post(f"{base}/run", json={"query":"Ping","files":[]}).json()
session_id = resp["session_id"]
job_id = resp["job_id"]
print("Started job", job_id, "session", session_id)
ws = create_connection("ws://127.0.0.1:8000/ws")
ws.send(json.dumps({"session_id": session_id}))
print("Subscribed")
events = []
running_seen = False
completed_seen = False
end_states = {"completed","failed","timeout"}
t0 = time.time()
while time.time() - t0 < 30:
    try:
        raw = ws.recv()
        if not raw:
            break
        ev = json.loads(raw)
        print("EVENT", ev)
        events.append(ev)
        if ev.get("type") == "job.status":
            state = ev["payload"].get("state")
            if state == "running":
                running_seen = True
            if state in end_states:
                completed_seen = True
                break
    except Exception as e:
        print("WS error", e)
        break
ws.close()
# Allow for possibility that running event was very fast; require at least a terminal state
assert completed_seen, "Did not observe terminal job.status event"
print("WebSocket basic test OK; running_seen=", running_seen, "total events=", len(events))