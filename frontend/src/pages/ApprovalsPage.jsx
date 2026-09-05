import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { approveSubtask, listPendingApprovals, rejectSubtask } from "../api/approvals";
import { useAuth } from "../context/AuthContext";
import NavBar from "../components/NavBar";
import { humanizeAgent } from "../utils/labels";

function hitlReason(p) {
  if (p.agent_type === "workflow") return "Escalated: workflow actions require human sign-off";
  if (p.confidence != null && p.confidence < 0.5) return "Escalated: confidence below threshold";
  return "Escalated: sensitive data accessed";
}

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ApprovalsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [rejectReasons, setRejectReasons] = useState({});
  const [showReasonFor, setShowReasonFor] = useState(null);

  useEffect(() => {
    if (user?.role !== "admin") return;
    listPendingApprovals()
      .then(setPending)
      .catch(() => setError("Could not load pending approvals."));
  }, [user]);

  if (user && user.role !== "admin") {
    return <Navigate to="/requests" replace />;
  }

  async function handleApprove(id) {
    setBusyId(id);
    try {
      await approveSubtask(id);
      setPending((prev) => prev.filter((p) => p.id !== id));
    } catch {
      setError("Could not approve this item.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(id) {
    const reason = rejectReasons[id]?.trim() || null;
    setBusyId(id);
    try {
      await rejectSubtask(id, reason);
      setPending((prev) => prev.filter((p) => p.id !== id));
    } catch {
      setError("Could not reject this item.");
    } finally {
      setBusyId(null);
      setShowReasonFor(null);
    }
  }

  function handleTrace(subtaskId) {
    navigate("/admin", { state: { traceSubtaskId: subtaskId } });
  }

  return (
    <div className="requests-page">
      <NavBar />
      <div className="page-content">
        <h2>Pending Approvals</h2>
        {error && <p className="error">{error}</p>}

        <ul className="request-list">
          {pending.map((p) => (
            <li key={p.id} style={{ gap: "8px" }}>
              <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                <span className="subtask-id-badge">#{p.id}</span>
                <span className="subtask-agent">{humanizeAgent(p.agent_type)}</span>
                {p.confidence != null && (
                  <span className="confidence">{Math.round(p.confidence * 100)}% confidence</span>
                )}
                {p.created_at && (
                  <span className="approval-waiting" title={new Date(p.created_at).toLocaleString()}>
                    Waiting {timeAgo(p.created_at)}
                  </span>
                )}
              </div>

              <p className="request-text" style={{ marginTop: "4px" }}>
                <strong>{p.requester_email}</strong> asked: &quot;{p.request_text}&quot;
              </p>

              <p className="hitl-reason">{hitlReason(p)}</p>

              {p.result && <p className="subtask-result">{p.result}</p>}
              {p.explanation && <p className="subtask-explanation">Why: {p.explanation}</p>}

              {showReasonFor === p.id && (
                <div className="reject-reason-box">
                  <label style={{ fontSize: "13px", display: "block", marginBottom: "4px" }}>
                    Rejection reason (optional)
                  </label>
                  <textarea
                    rows={2}
                    value={rejectReasons[p.id] ?? ""}
                    onChange={(e) =>
                      setRejectReasons((prev) => ({ ...prev, [p.id]: e.target.value }))
                    }
                    placeholder="Explain why this is being rejected…"
                    style={{ marginBottom: "6px" }}
                  />
                  <div style={{ display: "flex", gap: "6px" }}>
                    <button
                      type="button"
                      className="reject-confirm-btn"
                      disabled={busyId === p.id}
                      onClick={() => handleReject(p.id)}
                    >
                      {busyId === p.id ? "Rejecting…" : "Confirm Reject"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowReasonFor(null)}
                      style={{ fontSize: "13px" }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              <div className="approval-actions">
                <button
                  type="button"
                  className="approve-btn"
                  disabled={busyId === p.id}
                  onClick={() => handleApprove(p.id)}
                >
                  {busyId === p.id ? "…" : "Approve"}
                </button>
                {showReasonFor !== p.id && (
                  <button
                    type="button"
                    className="reject-btn"
                    disabled={busyId === p.id}
                    onClick={() => setShowReasonFor(p.id)}
                  >
                    Reject…
                  </button>
                )}
                <button
                  type="button"
                  className="trace-btn"
                  onClick={() => handleTrace(p.id)}
                  title="Open full decision trace in Admin"
                >
                  Trace
                </button>
              </div>
            </li>
          ))}
          {pending.length === 0 && <li className="empty">No pending approvals.</li>}
        </ul>
      </div>
    </div>
  );
}
