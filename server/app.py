import os
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import redis
from typing import Any
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

ALLOW_DEV_IP_OVERRIDE = os.getenv("ALLOW_DEV_IP_OVERRIDE", "false").lower() == "true"
# PORT = int(os.getenv("PORT", "8080"))
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

BUCKET_TZ = os.getenv("BUCKET_TZ", "America/New_York")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))
TTL_SECONDS = max(1, RETENTION_DAYS * 86400)

app = FastAPI()
logger = logging.getLogger(__name__)
DEV_CORS = os.getenv("DEV_CORS", "false").lower() == "true"

if DEV_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://wsc.programmeralek.com"],  
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# Track active websocket clients & lock redis for no multi client confusion of what actually processed first. 
clients: set[WebSocket] = set()
clients_lock = asyncio.Lock()



def to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return int(value.decode("utf-8"))
        except Exception:
            return default
    if isinstance(value, str):
        try:
            return int(value)
        except Exception:
            return default
    try:
        return int(value)
    except Exception:
        return default

def date_bucket_str() -> str:
    tz = ZoneInfo(BUCKET_TZ)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d")

def seen_key(date_str: str) -> str:
    return f"hits:seen_ips:{date_str}"

def count_key(date_str: str) -> str:
    return f"hits:count_daily:{date_str}"

def chat_name_key(ip: str) -> str:
    return f"chat:name:{ip}"

def get_client_ip(req: Request) -> str:
    logger.info("ALLOW_DEV_IP_OVERRIDE is enabled; checking x-dev-ip header.")
    if ALLOW_DEV_IP_OVERRIDE:
        logger.info("ALLOW_DEV_IP_OVERRIDE is enabled; checking x-dev-ip header.")
        dev_ip = req.headers.get("x-dev-ip")
        if dev_ip:
            return dev_ip.strip().replace("::ffff:", "")

    xff = req.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
        return ip.replace("::ffff:", "")
    if req.client and req.client.host:
        return req.client.host.replace("::ffff:", "")
    return ""

async def broadcast(payload: dict):
    msg = payload
    stale = []
    async with clients_lock:
        for ws in clients:
            try:
                await ws.send_json(msg)
            except Exception:
                stale.append(ws)
        for ws in stale:
            clients.discard(ws)

def ensure_ttl(pipe, key: str):
    
    ttl = pipe.ttl(key)
    if ttl is None or ttl < 0:
        pipe.expire(key, TTL_SECONDS)

def register_daily_unique_hit(ip: str, date_str: str) -> int:
    
    s_key = seen_key(date_str)
    c_key = count_key(date_str)


    if not ip:
        v = r.get(c_key)
        return to_int(v)

    while True:
        pipe = r.pipeline()
        try:
            pipe.watch(s_key, c_key)

            already = pipe.sismember(s_key, ip)
            current = pipe.get(c_key)

            pipe.multi()

            # TTLs (set only if missing)
            # NOTE: we must call ttl in the transaction; because we already called watch,
            # we can safely do these reads in the transaction as well.
            # Approach: we just set expire unconditionally if ttl < 0.
            # But ttl() must be queued after multi, so we can't branch on it inside the transaction.
            #
            # Simple reliable option: just call EXPIRE unconditionally.
            # Redis EXPIRE overwrites existing expiry, so this would extend the key each hit.
            # If you want strict expiry-from-first-seen, we can do a "set expiry only if no expiry"
            # using a small Lua script — but you asked for no Lua.
            #
            # Therefore: accept "rolling retention window" (TTL refreshed with activity).
            pipe.expire(s_key, TTL_SECONDS)
            pipe.expire(c_key, TTL_SECONDS)

            if not already:
                pipe.sadd(s_key, ip)
                pipe.incr(c_key)
            else:
                # No increment, but keep TTL refreshed
                pass

            results = pipe.execute()

            # Results:
            # expire s_key, expire c_key, (optional) sadd, (optional) incr
            # If incr happened, it's last result; if not, we need current count.
            if not already:
                new_count = results[-1]
                return int(new_count)
            return to_int(current)

        except redis.WatchError:
            # Keys changed between WATCH and EXEC; retry
            continue
        finally:
            try:
                pipe.reset()
            except Exception:
                pass

@app.get("/health")
def health():
    return "ok"

@app.get("/count")
def get_count():
    ds = date_bucket_str()
    v = r.get(count_key(ds))
    return {"count": to_int(v), "date": ds, "tz": BUCKET_TZ}

@app.post("/hit")
async def hit(request: Request):
    ds = date_bucket_str()
    ip = get_client_ip(request)

    count = register_daily_unique_hit(ip, ds)

    # broadcast
    await broadcast({"count": count, "date": ds})

    return JSONResponse({"count": count, "date": ds})

@app.get("/chat/name")
def get_chat_name(request: Request):
    ip = get_client_ip(request)
    if not ip:
        return {"registered": False, "name": None}
    name = r.get(chat_name_key(ip))
    if name:
        return {"registered": True, "name": name}
    return {"registered": False, "name": None}

@app.post("/chat/name")
async def set_chat_name(request: Request):
    ip = get_client_ip(request)
    if not ip:
        return JSONResponse({"error": "ip_not_found"}, status_code=400)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name_required"}, status_code=400)
    if len(name) > 50:
        name = name[:50]
    r.set(chat_name_key(ip), name, ex=TTL_SECONDS)
    return {"registered": True, "name": name}

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    # send initial count
    ds = date_bucket_str()
    v = r.get(count_key(ds))
    await websocket.send_json({"count": to_int(v), "date": ds})

    async with clients_lock:
        clients.add(websocket)

    try:
        while True:
            # Keep alive: wait for any message (we ignore content)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with clients_lock:
            clients.discard(websocket)
