import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMyPermissions } from "../api/auth";
import { createRequest, listRequests, streamRequest } from "../api/requests";
import { useAuth } from "../context/AuthContext";
import NavBar from "../components/NavBar";
import { humanizeAgent, humanizeStatus } from "../utils/labels";
import { AGENT_ICONS } from "../utils/agents";

function confidenceTier(confidence) {
  if (confidence == null) return null;
  if (confidence < 0.4) return "low";
  if (confidence < 0.7) return "medium";
  return "high";
}

const LONG_RESULT_THRESHOLD = 300;

function SubtaskCard({ s }) {
  const [expanded, setExpanded] = useState(s.agent_type === "security");
  const isLong = s.result && s.result.length > LONG_RESULT_THRESHOLD;
  const preview = isLong && !expanded ? s.result.slice(0, LONG_RESULT_THRESHOLD) + "…" : s.result;

  return (
    <li data-agent={s.agent_type}>
      <span className="subtask-agent">
        {AGENT_ICONS[s.agent_type] && <span aria-hidden="true">{AGENT_ICONS[s.agent_type]}</span>}
        {humanizeAgent(s.agent_type)}
      </span>
      <span className={`status status-${s.status}`}>{humanizeStatus(s.status)}</span>
      {s.confidence != null && (
        <span className={`confidence confidence-${confidenceTier(s.confidence)}`}>
          {Math.round(s.confidence * 100)}% confidence
        </span>
      )}
      {s.duration_ms != null && (
        <span className="request-time">{(s.duration_ms / 1000).toFixed(1)}s</span>
      )}
      {s.result && <p className="subtask-result">{preview}</p>}
      {isLong && (
        <button className="subtask-result-toggle" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "▲ Show less" : "▼ Show full result"}
        </button>
      )}
      {s.explanation && <p className="subtask-explanation">{s.explanation}</p>}
      {s.approved_by_email && (
        <p className="subtask-explanation">
          Reviewed by {s.approved_by_email} at {new Date(s.approved_at).toLocaleString()}
        </p>
      )}
    </li>
  );
}

const AGENT_ORDER = ["rag", "analytics", "security", "workflow", "validation"];

export default function RequestsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [requests, setRequests] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [text, setText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [streamingId, setStreamingId] = useState(null);
  const [error, setError] = useState("");
  const streamCleanupRef = useRef(null);

  useEffect(() => {
    listRequests().then(setRequests).catch(() => setError("Could not load requests."));
    fetchMyPermissions().then(setPermissions).catch(() => {});
  }, []);

  // Cleanup SSE stream on unmount
  useEffect(() => () => streamCleanupRef.current?.(), []);

  // Auto-poll every 5 s while any subtask is pending_approval so the requester
  // sees status updates without a manual reload.
  useEffect(() => {
    const hasPending = requests.some((r) =>
      r.subtasks?.some((s) => s.status === "pending_approval")
    );
    if (!hasPending) return;
    const timer = setInterval(async () => {
      try {
        const updated = await listRequests();
        setRequests(updated);
      } catch {
        // silent — don't overwrite a prior error banner with a poll failure
      }
    }, 5000);
    return () => clearInterval(timer);
  }, [requests]);

  function attachStream(requestId) {
    streamCleanupRef.current?.();
    setStreamingId(requestId);
    const cleanup = streamRequest(
      requestId,
      (payload) => {
        setRequests((prev) =>
          prev.map((r) => (r.id === requestId ? { ...r, ...payload } : r))
        );
        const terminal = ["completed", "failed", "approved", "rejected"];
        if (terminal.includes(payload.status)) {
          setStreamingId(null);
        }
      },
      () => setStreamingId(null)
    );
    streamCleanupRef.current = cleanup;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setError("");
    setIsSubmitting(true);
    try {
      const created = await createRequest(text);
      setRequests((prev) => [created, ...prev]);
      setText("");
      attachStream(created.id);
    } catch {
      setError("Could not submit your request.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="requests-page">
      <NavBar />
      <div className="page-content">
        {permissions.length > 0 && (
          <p className="subtask-explanation" style={{ marginBottom: "1rem", padding: "0.6rem 1rem", borderLeft: "3px solid #7c5cbf" }}>
            {user?.role === "hr" ? "HR" : user?.role === "admin" ? "Admin" : "Employee"} access — you can use:{" "}
            {AGENT_ORDER
              .filter((a) => permissions.includes(a))
              .map((a) => `${AGENT_ICONS[a] ?? ""} ${humanizeAgent(a)}`.trim())
              .join(", ")}
            .
          </p>
        )}

        <form onSubmit={handleSubmit} className="request-form">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask the assistant something, e.g. 'Generate this month's headcount report for Engineering.'"
            rows={3}
          />
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Submitting..." : "Submit request"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}

        <ul className="request-list">
          {requests.map((r) => (
            <li key={r.id}>
              <p className="request-text">{r.text}</p>
              <span className={`status status-${r.status}`}>{humanizeStatus(r.status)}</span>
              {streamingId === r.id && (
                <span style={{ fontSize: "0.78rem", color: "#7c5cbf", marginLeft: "0.5rem" }}>
                  ⏳ Processing…
                </span>
              )}
              <span className="request-time">
                {new Date(r.created_at).toLocaleString()}
              </span>
              <button
                type="button"
                onClick={() => navigate(`/requests/${r.id}`)}
                style={{ alignSelf: "flex-start", fontSize: "0.8rem", padding: "2px 8px" }}
              >
                View detail
              </button>
              {r.subtasks?.length > 0 && (
                <ul className="subtask-list">
                  {r.subtasks.map((s) => (
                    <SubtaskCard key={s.id} s={s} />
                  ))}
                </ul>
              )}
            </li>
          ))}
          {requests.length === 0 && <li className="empty">No requests yet.</li>}
        </ul>
      </div>
    </div>
  );
}
