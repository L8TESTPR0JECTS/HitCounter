import { useEffect, useRef, useState } from "react";

const WS_PROTO = window.location.protocol === "https:" ? "wss" : "ws";
const DEFAULT_API_BASE = import.meta.env.DEV
  ? `${window.location.protocol}//${window.location.hostname}:8080`
  : `${window.location.protocol}//${window.location.host}/api`;
const DEFAULT_WS_URL = import.meta.env.DEV
  ? `${WS_PROTO}://${window.location.hostname}:8080/ws`
  : `${WS_PROTO}://${window.location.host}/api/ws`;

const API_BASE = import.meta.env.VITE_API_BASE || DEFAULT_API_BASE;
const WS_URL = import.meta.env.VITE_WS_URL || DEFAULT_WS_URL;

export default function Counter() {
  const [count, setCount] = useState(0);
  const [date, setDate] = useState("");
  const [status, setStatus] = useState("Connecting...");
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setStatus("Connected");
    ws.onclose = () => setStatus("Disconnected");
    ws.onerror = () => setStatus("Error");
    ws.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (typeof payload.count === "number") {
          setCount(payload.count);
        }
        if (payload.date) {
          setDate(payload.date);
        }
      } catch {
        // Ignore malformed payloads.
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  const registerHit = async () => {
    try {
      const devIp = `${Math.floor(Math.random() * 150) + 1}.0.${Math.floor(
        Math.random() * 10
      ) + 1}.${Math.floor(Math.random() * 200) + 1}`;

      const res = await fetch(`${API_BASE}/hit`, {
        method: "POST",
        headers: { "X-Dev-Ip": devIp }
      });

      if (!res.ok) {
        const text = await res.text();
        console.error("Hit failed:", res.status, text);
      }
    } catch (error) {
      console.error("Hit error:", error);
    }
  };

  return (
    <section className="card">
      <header>
        <h1>Hit Counter</h1>
        <p className="meta">
          Status: <strong>{status}</strong>
        </p>
      </header>

      <div className="count">
        <span className="label">Count</span>
        <span className="value">{count}</span>
      </div>

      <p className="meta">
        Daily bucket: <code>{date || "loading..."}</code>
      </p>

      <button className="btn" type="button" onClick={registerHit}>
        Register Hit
      </button>

      <p className="meta small">API: {API_BASE}</p>
    </section>
  );
}
