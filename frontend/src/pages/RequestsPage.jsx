import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createRequest, listRequests } from "../api/requests";
import { useAuth } from "../context/AuthContext";
import NavBar from "../components/NavBar";
import { humanizeAgent, humanizeStatus } from "../utils/labels";

function confidenceTier(confidence) {
  if (confidence == null) return null;
  if (confidence < 0.4) return "low";
  if (confidence < 0.7) return "medium";
  return "high";
}

export default function RequestsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [requests, setRequests] = useState([]);
  const [text, setText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    listRequests().then(setRequests).catch(() => setError("Could not load requests."));
  }, []);

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

  async function handleSubmit(event) {
    event.preventDefault();
    if (!text.trim()) return;
    setError("");
    setIsSubmitting(true);
    try {
      const created = await createRequest(text);
      setRequests((prev) => [created, ...prev]);
      setText("");
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
        {user?.role === "hr" && (
          <p className="subtask-explanation" style={{ marginBottom: "1rem", padding: "0.6rem 1rem", borderLeft: "3px solid #7c5cbf" }}>
            HR access — you can use: Knowledge Base, Task Automation, Validation Review, Security Check, Analytics.
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
                    <li key={s.id}>
                      <span className="subtask-agent">{humanizeAgent(s.agent_type)}</span>
                      <span className={`status status-${s.status}`}>{humanizeStatus(s.status)}</span>
                      {s.description && (
                        <p className="subtask-explanation" style={{ margin: "2px 0" }}>Task: {s.description}</p>
                      )}
                      {s.confidence != null && (
                        <span className={`confidence confidence-${confidenceTier(s.confidence)}`}>
                          {Math.round(s.confidence * 100)}% confidence
                        </span>
                      )}
                      {s.duration_ms != null && (
                        <span className="request-time">{(s.duration_ms / 1000).toFixed(1)}s</span>
                      )}
                      <p className="subtask-result">{s.result}</p>
                      {s.explanation && <p className="subtask-explanation">Why: {s.explanation}</p>}
                      {s.approved_by_email && (
                        <p className="subtask-explanation">
                          Reviewed by {s.approved_by_email} at{" "}
                          {new Date(s.approved_at).toLocaleString()}
                        </p>
                      )}
                    </li>
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
