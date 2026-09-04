import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import {
  getDecisionTrace,
  getLatestRagEvaluation,
  getMetrics,
  getPermissionsMatrix,
  listAuditLogs,
  listUsers,
  runRagEvaluation,
  togglePermission,
  updateUser,
} from "../api/admin";
import { useAuth } from "../context/AuthContext";
import { humanizeAgent, humanizeStatus } from "../utils/labels";

const EVENT_TYPES = ["", "agent_action", "data_access", "approval", "auth", "admin"];

function formatMetricValue(key, value) {
  if (value == null) return "—";
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "—";
    return entries.map(([k, v]) => `${humanizeAgent(k)}: ${formatMetricValue(key, v)}`).join(", ");
  }
  if (key.endsWith("_rate") || key.endsWith("_coverage") || key.includes("confidence")) {
    return `${Math.round(value * 100)}%`;
  }
  if (key.includes("_seconds")) {
    return `${value.toFixed(2)}s`;
  }
  if (typeof value === "number" && !Number.isInteger(value)) {
    return value.toFixed(2);
  }
  return String(value);
}

function humanizeMetricKey(key) {
  return key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function MetricsTable({ title, data }) {
  return (
    <div>
      <h3>{title}</h3>
      <table className="admin-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data).map(([key, value]) => (
            <tr key={key}>
              <td>{humanizeMetricKey(key)}</td>
              <td>{formatMetricValue(key, value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricsSection() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getMetrics().then(setReport).catch(() => setError("Could not load evaluation metrics."));
  }, []);

  if (error) {
    return (
      <section className="admin-section">
        <h2>Evaluation Metrics</h2>
        <p className="error">{error}</p>
      </section>
    );
  }
  if (!report) return null;

  return (
    <section className="admin-section">
      <h2>Evaluation Metrics</h2>
      <p className="subtask-explanation">
        Accuracy figures are confidence-based proxies (no labeled ground-truth dataset exists),
        not verified-correctness scores.
      </p>
      <div className="metrics-grid">
        <MetricsTable title="Accuracy" data={report.accuracy} />
        <MetricsTable title="Timing" data={report.timing} />
        <MetricsTable title="Security" data={report.security} />
        <MetricsTable title="Human-in-the-Loop" data={report.hitl} />
        <MetricsTable title="Explainability" data={report.explainability} />
      </div>
    </section>
  );
}

function RagEvaluationSection() {
  const [run, setRun] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getLatestRagEvaluation()
      .then(setRun)
      .catch(() => setError("Could not load the latest evaluation."));
  }, []);

  async function handleRun() {
    setRunning(true);
    setError("");
    try {
      const result = await runRagEvaluation();
      setRun(result);
    } catch {
      setError("Could not complete the evaluation run.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="admin-section">
      <h2>RAG vs. Baseline (Hallucination Check)</h2>
      <p className="subtask-explanation">
        Each question has a company-specific fact invented for this project's seed documents --
        no LLM could know it without retrieval. "Baseline" calls the LLM directly with no
        context; "Grounded" uses the real RAG pipeline. A wide accuracy gap is a measurable
        hallucination-rate reduction attributable to RAG (NFR-2).
      </p>
      <button type="button" onClick={handleRun} disabled={running}>
        {running ? "Running (this takes a couple of minutes)..." : "Run Evaluation"}
      </button>
      {error && <p className="error">{error}</p>}
      {run && (
        <>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Run at</th>
                <th>Baseline accuracy</th>
                <th>Grounded accuracy</th>
                <th>Improvement</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{new Date(run.created_at).toLocaleString()}</td>
                <td>{Math.round(run.baseline_accuracy * 100)}%</td>
                <td>{Math.round(run.grounded_accuracy * 100)}%</td>
                <td>
                  +{Math.round((run.grounded_accuracy - run.baseline_accuracy) * 100)}
                  pts
                </td>
              </tr>
            </tbody>
          </table>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Question</th>
                <th>Baseline answer</th>
                <th>Grounded answer</th>
                <th>Sources</th>
              </tr>
            </thead>
            <tbody>
              {run.cases.map((c) => (
                <tr key={c.question}>
                  <td>{c.question}</td>
                  <td className={c.baseline_correct ? "confidence-high" : "confidence-low"}>
                    {c.baseline_answer}
                  </td>
                  <td className={c.grounded_correct ? "confidence-high" : "confidence-low"}>
                    {c.grounded_answer}
                  </td>
                  <td>{c.grounded_sources.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {!run && !error && <p>No evaluation has been run yet.</p>}
    </section>
  );
}

function UsersSection({ currentUserId, roles }) {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    listUsers().then(setUsers).catch(() => setError("Could not load users."));
  }, []);

  async function handleRoleChange(user, role) {
    try {
      const updated = await updateUser(user.id, { role });
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
    } catch {
      setError(`Could not update role for ${user.email}.`);
    }
  }

  async function handleActiveToggle(user) {
    try {
      const updated = await updateUser(user.id, { is_active: !user.is_active });
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)));
    } catch {
      setError(`Could not update status for ${user.email}.`);
    }
  }

  return (
    <section className="admin-section">
      <h2>Users</h2>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Role</th>
            <th>Active</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>{u.full_name}</td>
              <td>
                <select
                  value={u.role}
                  disabled={u.id === currentUserId}
                  onChange={(e) => handleRoleChange(u, e.target.value)}
                >
                  {roles.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={u.is_active}
                  disabled={u.id === currentUserId}
                  onChange={() => handleActiveToggle(u)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function PermissionsSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getPermissionsMatrix().then(setData).catch(() => setError("Could not load permissions."));
  }, []);

  async function handleToggle(role, agentType, allowed) {
    try {
      const updated = await togglePermission(role, agentType, allowed);
      setData(updated);
    } catch {
      setError("Could not update this permission.");
    }
  }

  if (!data) return <section className="admin-section"><h2>Permissions</h2>{error && <p className="error">{error}</p>}</section>;

  return (
    <section className="admin-section">
      <h2>Permissions</h2>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Agent</th>
            {data.roles.map((role) => (
              <th key={role}>{role}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.agent_types.map((agentType) => (
            <tr key={agentType}>
              <td>{humanizeAgent(agentType)}</td>
              {data.roles.map((role) => {
                const allowed = data.matrix[role]?.includes(agentType);
                return (
                  <td key={role}>
                    <input
                      type="checkbox"
                      checked={allowed}
                      onChange={() => handleToggle(role, agentType, !allowed)}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function AuditLogSection({ onTrace }) {
  const [logs, setLogs] = useState([]);
  const [eventType, setEventType] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listAuditLogs(eventType || undefined, userId || undefined)
      .then(setLogs)
      .catch(() => setError("Could not load audit logs."));
  }, [eventType, userId]);

  return (
    <section className="admin-section">
      <h2>Audit Log</h2>
      <label className="audit-filter">
        Event type
        <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          {EVENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t || "All"}
            </option>
          ))}
        </select>
      </label>
      <label className="audit-filter">
        User ID
        <input
          type="number"
          min="1"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="All users"
        />
      </label>
      {error && <p className="error">{error}</p>}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Type</th>
            <th>Action</th>
            <th>User</th>
            <th>Role</th>
            <th>Request</th>
            <th>Subtask</th>
            <th>Context</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id}>
              <td>{new Date(log.created_at).toLocaleString()}</td>
              <td>{log.event_type}</td>
              <td>{log.action}</td>
              <td>{log.user_email ?? "—"}</td>
              <td>{log.role ?? "—"}</td>
              <td>{log.request_id ?? "—"}</td>
              <td>{log.subtask_id ?? "—"}</td>
              <td className="audit-context">{log.context ? JSON.stringify(log.context) : "—"}</td>
              <td>
                {log.subtask_id != null && (
                  <button type="button" onClick={() => onTrace(log.subtask_id)}>
                    Trace
                  </button>
                )}
              </td>
            </tr>
          ))}
          {logs.length === 0 && (
            <tr>
              <td colSpan={9}>No audit log entries.</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function TraceSection({ requestedSubtaskId, requestNonce }) {
  const [subtaskIdInput, setSubtaskIdInput] = useState("");
  const [trace, setTrace] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function lookup(id) {
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      const result = await getDecisionTrace(id);
      setTrace(result);
    } catch {
      setError(`Could not find a trace for subtask ${id}.`);
      setTrace(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (requestedSubtaskId != null) {
      setSubtaskIdInput(String(requestedSubtaskId));
      lookup(requestedSubtaskId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedSubtaskId, requestNonce]);

  function handleSubmit(event) {
    event.preventDefault();
    lookup(subtaskIdInput);
  }

  return (
    <section className="admin-section">
      <h2>Trace a Decision</h2>
      <p className="subtask-explanation">
        Assembles the full causal trail for one subtask -- its own rationale/confidence, the
        request that produced it, and every audit log entry tied to it, in order (NFR-3).
      </p>
      <form onSubmit={handleSubmit} className="trace-lookup">
        <input
          type="number"
          value={subtaskIdInput}
          onChange={(e) => setSubtaskIdInput(e.target.value)}
          placeholder="Subtask ID"
        />
        <button type="submit" disabled={loading}>
          {loading ? "Looking up..." : "Look Up"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {trace && (
        <>
          <table className="admin-table">
            <tbody>
              <tr>
                <td>Request</td>
                <td>
                  #{trace.request.id} — "{trace.request.text}"
                </td>
              </tr>
              <tr>
                <td>Requester</td>
                <td>{trace.request.requester_email}</td>
              </tr>
              <tr>
                <td>Agent</td>
                <td>{humanizeAgent(trace.subtask.agent_type)}</td>
              </tr>
              <tr>
                <td>Status</td>
                <td>{humanizeStatus(trace.subtask.status)}</td>
              </tr>
              <tr>
                <td>Confidence</td>
                <td>
                  {trace.subtask.confidence != null
                    ? `${Math.round(trace.subtask.confidence * 100)}%`
                    : "—"}
                </td>
              </tr>
              <tr>
                <td>Result</td>
                <td>{trace.subtask.result}</td>
              </tr>
              <tr>
                <td>Explanation</td>
                <td>{trace.subtask.explanation}</td>
              </tr>
              {trace.subtask.approved_by_email && (
                <tr>
                  <td>Reviewed by</td>
                  <td>
                    {trace.subtask.approved_by_email} at{" "}
                    {new Date(trace.subtask.approved_at).toLocaleString()}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <h3>Audit Trail</h3>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Action</th>
                <th>Role</th>
                <th>Context</th>
              </tr>
            </thead>
            <tbody>
              {trace.audit_trail.map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.created_at).toLocaleString()}</td>
                  <td>{entry.event_type}</td>
                  <td>{entry.action}</td>
                  <td>{entry.role ?? "—"}</td>
                  <td className="audit-context">
                    {entry.context ? JSON.stringify(entry.context) : "—"}
                  </td>
                </tr>
              ))}
              {trace.audit_trail.length === 0 && (
                <tr>
                  <td colSpan={5}>No audit log entries for this subtask.</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const [traceRequest, setTraceRequest] = useState({ subtaskId: null, nonce: 0 });
  const [roles, setRoles] = useState(["employee", "hr", "admin"]);

  useEffect(() => {
    getPermissionsMatrix()
      .then((data) => setRoles(data.roles))
      .catch(() => {});
  }, []);

  if (user && user.role !== "admin") {
    return <Navigate to="/requests" replace />;
  }

  function handleTrace(subtaskId) {
    setTraceRequest({ subtaskId, nonce: Date.now() });
  }

  return (
    <div className="requests-page">
      <header>
        <h1>Admin</h1>
      </header>
      {user && (
        <>
          <UsersSection currentUserId={user.id} roles={roles} />
          <PermissionsSection />
          <AuditLogSection onTrace={handleTrace} />
          <TraceSection
            requestedSubtaskId={traceRequest.subtaskId}
            requestNonce={traceRequest.nonce}
          />
          <MetricsSection />
          <RagEvaluationSection />
        </>
      )}
    </div>
  );
}
