import { useEffect, useState } from "react";
import { Button } from "primereact/button";
import { Dialog } from "primereact/dialog";
import { InputText } from "primereact/inputtext";

const DEFAULT_API_BASE = import.meta.env.DEV
  ? `${window.location.protocol}//${window.location.hostname}:8080`
  : `${window.location.protocol}//${window.location.host}/api`;
const API_BASE = import.meta.env.VITE_API_BASE || DEFAULT_API_BASE;

export default function Chat() {
  const [name, setName] = useState("");
  const [registeredName, setRegisteredName] = useState("");
  const [status, setStatus] = useState("Checking...");
  const [showDialog, setShowDialog] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    const loadName = async () => {
      setStatus("Checking...");
      try {
        const res = await fetch(`${API_BASE}/chat/name`);
        if (!res.ok) {
          throw new Error("Failed to fetch");
        }
        const data = await res.json();
        if (!active) return;
        if (data.registered) {
          setRegisteredName(data.name || "");
          setShowDialog(false);
          setStatus("Ready");
        } else {
          setShowDialog(true);
          setStatus("Needs name");
        }
      } catch {
        if (!active) return;
        setShowDialog(true);
        setStatus("Needs name");
        setError("Unable to check your name. Please enter it.");
      }
    };

    loadName();

    return () => {
      active = false;
    };
  }, []);

  const submitName = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter a name.");
      return;
    }
    setError("");
    try {
      const res = await fetch(`${API_BASE}/chat/name`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed })
      });
      if (!res.ok) {
        setError(`Failed to save name (${res.status}).`);
        return;
      }
      const data = await res.json();
      setRegisteredName(data.name || trimmed);
      setShowDialog(false);
      setStatus("Ready");
    } catch {
      setError("Failed to save name. Try again.");
    }
  };

  const dialogFooter = (
    <div className="dialog-actions">
      <Button label="Save" icon="pi pi-check" onClick={submitName} />
    </div>
  );

  return (
    <section className="card">
      <header>
        <h1>Chat</h1>
        <p className="meta chat-status">
          {registeredName ? `Welcome, ${registeredName}.` : "Name required."} Status:
          <strong> {status}</strong>
        </p>
      </header>

      <div className="chat-placeholder">
        <p>We will add messages and input here later.</p>
      </div>

      <Dialog
        header="Introduce yourself"
        visible={showDialog}
        modal
        closable={false}
        draggable={false}
        footer={dialogFooter}
      >
        <div className="dialog-body">
          <label className="dialog-label" htmlFor="chat-name">
            Your name
          </label>
          <InputText
            id="chat-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                submitName();
              }
            }}
            autoFocus
          />
          {error ? <p className="dialog-error">{error}</p> : null}
        </div>
      </Dialog>
    </section>
  );
}
