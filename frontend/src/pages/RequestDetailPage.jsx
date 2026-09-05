import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getRequest } from "../api/requests";
import { useAuth } from "../context/AuthContext";
import NavBar from "../components/NavBar";
import { humanizeAgent, humanizeStatus } from "../utils/labels";

function confidenceTier(confidence) {
  if (confidence == null) return null;
  if (confidence < 0.4) return "low";
  if (confidence < 0.7) return "medium";
  return "high";
}

function hitlReason(subtask) {
  if (subtask.status !== "pending_approval" && subtask.status !== "completed") return null;
  if (subtask.agent_type === "workflow") return "Escalated: workflow actions require human sign-off";
  if (subtask.confidence != null && subtask.confidence < 0.5) return "Escalated: confidence below threshold";
  if (subtask.status === "pending_approval") return "Escalated: sensitive data accessed";
  return null;
}

export default function RequestDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [request, setRequest] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getRequest(id)
      .then(setRequest)
      .catch(() => setError("Could not load request."));
  }, [id]);

  // Poll every 5 s while any subtask is pending approval so the requester
  // sees the HITL-resolved state without a manual reload.
  useEffect(() => {
    if (!request) return;
    const hasPending = request.subtasks?.some((s) => s.status === "pending_approval");
    if (!hasPending) return;
    const timer = setInterval(() => {
      getRequest(id).then(setRequest).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [id, request]);

  if (error) {
    return (
      <div className="requests-page">
        <NavBar />
        <p className="error" style={{ padding: "1rem 1.5rem" }}>{error}</p>
      </div>
    );
  }

  if (!request) {
    return (
      <div className="requests-page">
        <NavBar />
        <p style={{ padding: "1rem 1.5rem" }}>Loading…</p>
      </div>
    );
  }

  return (
    <div className="requests-page">
      <NavBar />
      <div className="page-content">
        <Link to="/requests" style={{ fontSize: "14px" }}>← Back to requests</Link>
        <h2 style={{ margin: "0.5rem 0 1rem" }}>Request #{request.id}</h2>

        <section className="admin-section">
          <table className="admin-table">
            <tbody>
              <tr>
                <td><strong>Request</strong></td>
                <td>{request.text}</td>
              </tr>
              <tr>
                <td><strong>Status</strong></td>
                <td>
                  <span className={`status status-${request.status}`}>
                    {humanizeStatus(request.status)}
                  </span>
                </td>
              </tr>
              <tr>
                <td><strong>Submitted</strong></td>
                <td>{new Date(request.created_at).toLocaleString()}</td>
              </tr>
              {request.completed_at && (
                <tr>
                  <td><strong>Completed</strong></td>
                  <td>{new Date(request.completed_at).toLocaleString()}</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        {request.subtasks?.length > 0 && (
          <section className="admin-section">
            <h2>Subtasks</h2>
            {request.subtasks.map((s) => (
              <div
                key={s.id}
                style={{ marginBottom: "1.5rem", borderLeft: "3px solid #444", paddingLeft: "1rem" }}
              >
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.4rem" }}>
                  <span className="subtask-id-badge">#{s.id}</span>
                  <strong>{humanizeAgent(s.agent_type)}</strong>
                  <span className={`status status-${s.status}`}>{humanizeStatus(s.status)}</span>
                  {s.confidence != null && (
                    <span className={`confidence confidence-${confidenceTier(s.confidence)}`}>
                      {Math.round(s.confidence * 100)}% confidence
                    </span>
                  )}
                  {s.duration_ms != null && (
                    <span className="request-time">{(s.duration_ms / 1000).toFixed(1)}s</span>
                  )}
                  {user?.role === "admin" && (
                    <button
                      type="button"
                      className="trace-btn"
                      onClick={() => navigate("/admin", { state: { traceSubtaskId: s.id } })}
                      title="Open full decision trace"
                    >
                      Trace
                    </button>
                  )}
                </div>

                {s.created_at && (
                  <p className="subtask-explanation" style={{ fontSize: "11px", color: "var(--text)" }}>
                    Started {new Date(s.created_at).toLocaleString()}
                  </p>
                )}
                {hitlReason(s) && (
                  <p className="hitl-reason">{hitlReason(s)}</p>
                )}
                {s.description && (
                  <p className="subtask-explanation">Task: {s.description}</p>
                )}
                {s.result && <p className="subtask-result">{s.result}</p>}
                {s.explanation && (
                  <p className="subtask-explanation">Why: {s.explanation}</p>
                )}
                {s.workflow_steps?.length > 0 && (
                  <details style={{ marginTop: "0.5rem" }}>
                    <summary style={{ fontSize: "13px", cursor: "pointer", color: "var(--accent)" }}>
                      {s.workflow_steps.length} workflow step{s.workflow_steps.length !== 1 ? "s" : ""}
                    </summary>
                    <ol className="workflow-steps">
                      {s.workflow_steps.map((step) => (
                        <li key={step.step}>
                          <code>{step.function}</code>
                          {step.created_at && (
                            <span style={{ fontSize: "11px", color: "var(--text)", marginLeft: "8px", opacity: 0.7 }}>
                              {new Date(step.created_at).toLocaleTimeString()}
                            </span>
                          )}
                          {step.output && Object.keys(step.output).length > 0 && (
                            <pre className="workflow-output">{JSON.stringify(step.output, null, 2)}</pre>
                          )}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
                {s.approved_by_email && (
                  <p className="subtask-explanation">
                    Reviewed by {s.approved_by_email} at{" "}
                    {new Date(s.approved_at).toLocaleString()}
                  </p>
                )}
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
