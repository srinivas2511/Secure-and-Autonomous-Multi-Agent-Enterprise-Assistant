import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { approveSubtask, listPendingApprovals, rejectSubtask } from "../api/approvals";
import { useAuth } from "../context/AuthContext";
import NavBar from "../components/NavBar";
import { humanizeAgent } from "../utils/labels";

export default function ApprovalsPage() {
  const { user } = useAuth();
  const [pending, setPending] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

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
    setBusyId(id);
    try {
      await rejectSubtask(id);
      setPending((prev) => prev.filter((p) => p.id !== id));
    } catch {
      setError("Could not reject this item.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="requests-page">
      <NavBar />
      <div className="page-content">
      <h2>Pending Approvals</h2>
      {error && <p className="error">{error}</p>}

      <ul className="request-list">
        {pending.map((p) => (
          <li key={p.id}>
            <p className="request-text">
              <strong>{p.requester_email}</strong> asked: "{p.request_text}"
            </p>
            <span className="subtask-agent">{humanizeAgent(p.agent_type)}</span>
            {p.confidence != null && (
              <span className="confidence">{Math.round(p.confidence * 100)}% confidence</span>
            )}
            <p className="subtask-result">{p.result}</p>
            {p.explanation && <p className="subtask-explanation">Why: {p.explanation}</p>}
            <div className="approval-actions">
              <button type="button" disabled={busyId === p.id} onClick={() => handleApprove(p.id)}>
                Approve
              </button>
              <button type="button" disabled={busyId === p.id} onClick={() => handleReject(p.id)}>
                Reject
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
