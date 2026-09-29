import { useCallback, useEffect, useRef, useState } from "react";
import NavBar from "../components/NavBar";
import { useAuth } from "../context/AuthContext";
import { listAuditLogs, listAllRequests } from "../api/admin";
import { fetchTraceSpans, fetchTraceTree } from "../api/observability";

// ─── colour palette ───────────────────────────────────────────────────────────
const STATUS_COLOUR = {
  completed: "#22c55e",
  failed: "#ef4444",
  pending_approval: "#f59e0b",
  denied: "#6b7280",
  running: "#3b82f6",
};

const SPAN_TYPE_LABEL = {
  agent: "Agent",
  llm_call: "LLM Call",
  rag_retrieve: "RAG Retrieve",
  workflow_step: "Workflow Step",
  hitl_gate: "HITL Gate",
};

const EVENT_COLOUR = {
  "agent_action": "#3b82f6",
  "data_access": "#8b5cf6",
  "admin": "#6b7280",
};

function statusColour(s) {
  return STATUS_COLOUR[s] || "#6b7280";
}

// ─── Timeline (Gantt) ─────────────────────────────────────────────────────────
function Timeline({ spans, requestCreatedAt, totalMs, onSelect, selected }) {
  const agentSpans = spans.filter((s) => s.span_type === "agent");
  const reqStart = requestCreatedAt ? new Date(requestCreatedAt).getTime() : null;

  if (!agentSpans.length) {
    return <p className="obs-empty">No agent spans yet for this request.</p>;
  }

  return (
    <div className="timeline-wrap">
      <div className="timeline-header">
        <span>Agent</span>
        <span>Execution timeline</span>
        <span>Duration</span>
      </div>
      {agentSpans.map((span) => {
        const startMs = reqStart ? new Date(span.started_at).getTime() - reqStart : 0;
        const dur = span.duration_ms || 0;
        const total = totalMs || 1;
        const leftPct = Math.max(0, (startMs / total) * 100);
        const widthPct = Math.max(1, (dur / total) * 100);
        const colour = statusColour(span.status);
        const isSelected = selected?.id === span.id;

        return (
          <div
            key={span.id}
            className={`timeline-row${isSelected ? " timeline-row--selected" : ""}`}
            onClick={() => onSelect(span)}
          >
            <span className="timeline-label" title={span.name}>
              {span.name}
            </span>
            <div className="timeline-track">
              <div
                className="timeline-bar"
                style={{
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                  background: colour,
                  opacity: isSelected ? 1 : 0.85,
                }}
                title={`${span.name} — ${span.status} — ${dur}ms`}
              />
            </div>
            <span className="timeline-dur">{dur ? `${dur}ms` : "—"}</span>
          </div>
        );
      })}
      <p className="timeline-total">
        Total request duration: <strong>{totalMs ? `${totalMs}ms` : "—"}</strong>
      </p>
    </div>
  );
}

// ─── Agent Graph (SVG tree) ───────────────────────────────────────────────────
const NODE_W = 140;
const NODE_H = 52;
const H_GAP = 24;
const V_GAP = 60;

function layoutTree(nodes, x = 0, depth = 0) {
  // Assigns x/y coords to each node in the tree (simple top-down layout).
  if (!nodes.length) return { items: [], width: 0 };
  const items = [];
  let cursor = x;
  for (const node of nodes) {
    const childResult = layoutTree(node.children || [], cursor, depth + 1);
    const nodeWidth = Math.max(NODE_W, childResult.width);
    const nodeX = cursor + nodeWidth / 2 - NODE_W / 2;
    items.push({
      ...node,
      _x: nodeX,
      _y: depth * (NODE_H + V_GAP),
      _children: childResult.items,
    });
    cursor += nodeWidth + H_GAP;
  }
  return { items, width: cursor - H_GAP };
}

function renderNodes(nodes, onSelect, selected, parentX, parentY) {
  const elems = [];
  for (const node of nodes) {
    const cx = node._x + NODE_W / 2;
    const cy = node._y + NODE_H / 2;
    const colour = statusColour(node.status);
    const isSelected = selected?.id === node.id;

    // Arrow from parent
    if (parentX !== undefined) {
      elems.push(
        <line
          key={`line-${node.id}`}
          x1={parentX}
          y1={parentY + NODE_H}
          x2={cx}
          y2={node._y}
          stroke="#64748b"
          strokeWidth="1.5"
          markerEnd="url(#arrowhead)"
        />
      );
    }

    // Node box
    elems.push(
      <g
        key={`node-${node.id}`}
        onClick={() => onSelect(node)}
        style={{ cursor: "pointer" }}
      >
        <rect
          x={node._x}
          y={node._y}
          width={NODE_W}
          height={NODE_H}
          rx={6}
          fill={isSelected ? colour : "#1e293b"}
          stroke={colour}
          strokeWidth={isSelected ? 2.5 : 1.5}
        />
        <text
          x={node._x + NODE_W / 2}
          y={node._y + 18}
          textAnchor="middle"
          fill="#f1f5f9"
          fontSize="12"
          fontWeight="600"
        >
          {node.name}
        </text>
        <text
          x={node._x + NODE_W / 2}
          y={node._y + 34}
          textAnchor="middle"
          fill="#94a3b8"
          fontSize="10"
        >
          {SPAN_TYPE_LABEL[node.span_type] || node.span_type}
          {node.duration_ms ? ` · ${node.duration_ms}ms` : ""}
        </text>
      </g>
    );

    // Children
    if (node._children?.length) {
      elems.push(...renderNodes(node._children, onSelect, selected, cx, node._y));
    }
  }
  return elems;
}

function AgentGraph({ tree, onSelect, selected }) {
  if (!tree?.spans?.length) {
    return <p className="obs-empty">No span tree available for this request.</p>;
  }

  const layout = layoutTree(tree.spans);
  const svgWidth = Math.max(600, layout.width + 40);
  const maxDepth = (function findDepth(nodes, d = 0) {
    let max = d;
    for (const n of nodes) max = Math.max(max, findDepth(n._children || [], d + 1));
    return max;
  })(layout.items);
  const svgHeight = (maxDepth + 1) * (NODE_H + V_GAP) + 20;

  return (
    <div className="graph-scroll">
      <svg
        width={svgWidth}
        height={svgHeight}
        style={{ display: "block", minWidth: svgWidth }}
      >
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#64748b" />
          </marker>
        </defs>
        {renderNodes(layout.items, onSelect, selected, undefined, undefined)}
      </svg>
    </div>
  );
}

// ─── Trace Details panel ──────────────────────────────────────────────────────
function TraceDetails({ span }) {
  if (!span) {
    return (
      <div className="trace-details-empty">
        <p>Click a span in the Timeline or Agent Graph to see details.</p>
      </div>
    );
  }

  const meta = span.metadata || span.metadata_ || {};
  const rows = [
    ["Span type", SPAN_TYPE_LABEL[span.span_type] || span.span_type],
    ["Name", span.name],
    ["Status", span.status],
    ["Started", span.started_at ? new Date(span.started_at).toLocaleString() : "—"],
    ["Ended", span.ended_at ? new Date(span.ended_at).toLocaleString() : "—"],
    ["Duration", span.duration_ms != null ? `${span.duration_ms} ms` : "—"],
    ["Input tokens", span.input_tokens ?? "—"],
    ["Output tokens", span.output_tokens ?? "—"],
    ["Confidence", meta.confidence != null ? `${(meta.confidence * 100).toFixed(0)}%` : "—"],
    ["Sensitive", meta.sensitive != null ? String(meta.sensitive) : "—"],
  ];

  return (
    <div className="trace-details">
      <h3>Span details — {span.name}</h3>
      <table className="metrics-table">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <td><strong>{k}</strong></td>
              <td>{String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {meta.explanation && (
        <div className="trace-explanation">
          <strong>Explanation:</strong>
          <p>{meta.explanation}</p>
        </div>
      )}
      {meta.sources?.length > 0 && (
        <div className="trace-explanation">
          <strong>Sources:</strong>
          <p>{meta.sources.join(", ")}</p>
        </div>
      )}
      {meta.error && (
        <div className="trace-explanation trace-error">
          <strong>Error:</strong>
          <p>{meta.error}</p>
        </div>
      )}
      {meta.reason && (
        <div className="trace-explanation">
          <strong>HITL reason:</strong>
          <p>{meta.reason}</p>
        </div>
      )}
    </div>
  );
}

// ─── Events feed ─────────────────────────────────────────────────────────────
function EventsFeed({ events }) {
  return (
    <div className="events-feed">
      <h3>Live events (last 50)</h3>
      {events.length === 0 ? (
        <p className="obs-empty">No events yet.</p>
      ) : (
        <div className="events-scroll">
          <table className="metrics-table events-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Action</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr
                  key={e.id}
                  style={{
                    borderLeft: `3px solid ${EVENT_COLOUR[e.event_type] || "#6b7280"}`,
                  }}
                >
                  <td style={{ whiteSpace: "nowrap" }}>
                    {new Date(e.created_at).toLocaleTimeString()}
                  </td>
                  <td>{e.event_type}</td>
                  <td>{e.action}</td>
                  <td>{e.role || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function ObservabilityPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  // All hooks must be declared unconditionally before any early return.
  const [requests, setRequests] = useState([]);
  const [selectedReqId, setSelectedReqId] = useState(null);
  const [spans, setSpans] = useState([]);
  const [tree, setTree] = useState(null);
  const [selectedSpan, setSelectedSpan] = useState(null);
  const [events, setEvents] = useState([]);
  const [loadingSpans, setLoadingSpans] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  // Load request list — skipped for non-admins (isAdmin guard prevents 403).
  useEffect(() => {
    if (!isAdmin) return;
    listAllRequests()
      .then(setRequests)
      .catch((e) => setError(e.message));
  }, [isAdmin]);

  // Poll audit-log events every 10s — skipped for non-admins.
  useEffect(() => {
    if (!isAdmin) return;
    function fetchEvents() {
      listAuditLogs(null, null, 50)
        .then(setEvents)
        .catch(() => {});
    }
    fetchEvents();
    pollRef.current = setInterval(fetchEvents, 10000);
    return () => clearInterval(pollRef.current);
  }, [isAdmin]);

  const loadRequest = useCallback((reqId) => {
    setSelectedReqId(reqId);
    setSelectedSpan(null);
    setSpans([]);
    setTree(null);
    setError(null);
    setLoadingSpans(true);

    Promise.all([fetchTraceSpans(reqId), fetchTraceTree(reqId)])
      .then(([spansData, treeData]) => {
        setSpans(spansData);
        setTree(treeData);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingSpans(false));
  }, []);

  // Gate: render access-denied for non-admins after all hooks have run.
  if (user && !isAdmin) {
    return (
      <>
        <NavBar />
        <main className="page-container">
          <h1 className="page-title">Observability</h1>
          <p style={{ color: "#ef4444" }}>
            Access denied — this page is restricted to administrators.
          </p>
        </main>
      </>
    );
  }

  const selectedReq = requests.find((r) => r.id === selectedReqId);

  return (
    <>
      <NavBar />
      <main className="page-container">
        <h1 className="page-title">Observability</h1>

        {error && <div className="error-banner">{error}</div>}

        {/* Request selector */}
        <section className="obs-section">
          <h2>Select request</h2>
          <div className="request-selector">
            {requests.length === 0 ? (
              <p className="obs-empty">No requests yet.</p>
            ) : (
              <select
                value={selectedReqId || ""}
                onChange={(e) => e.target.value && loadRequest(Number(e.target.value))}
                className="obs-select"
              >
                <option value="">— choose a request —</option>
                {requests.map((r) => (
                  <option key={r.id} value={r.id}>
                    #{r.id} · {r.status} · {r.text.slice(0, 60)}
                    {r.text.length > 60 ? "…" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>
        </section>

        {selectedReqId && (
          <>
            {loadingSpans && <p className="obs-loading">Loading trace data…</p>}

            {/* Metrics summary row */}
            {tree && (
              <section className="obs-section">
                <div className="obs-metric-row">
                  <div className="obs-metric-card">
                    <span className="obs-metric-label">Total duration</span>
                    <span className="obs-metric-value">
                      {tree.total_duration_ms != null ? `${tree.total_duration_ms}ms` : "—"}
                    </span>
                  </div>
                  <div className="obs-metric-card">
                    <span className="obs-metric-label">Agent spans</span>
                    <span className="obs-metric-value">
                      {spans.filter((s) => s.span_type === "agent").length}
                    </span>
                  </div>
                  <div className="obs-metric-card">
                    <span className="obs-metric-label">LLM calls</span>
                    <span className="obs-metric-value">
                      {spans.filter((s) => s.span_type === "llm_call").length}
                    </span>
                  </div>
                  <div className="obs-metric-card">
                    <span className="obs-metric-label">Total tokens</span>
                    <span className="obs-metric-value">
                      {spans
                        .filter((s) => s.span_type === "llm_call")
                        .reduce((acc, s) => acc + (s.input_tokens || 0) + (s.output_tokens || 0), 0) || "—"}
                    </span>
                  </div>
                  <div className="obs-metric-card">
                    <span className="obs-metric-label">Status</span>
                    <span
                      className="obs-metric-value"
                      style={{ color: statusColour(tree.request_status) }}
                    >
                      {tree.request_status}
                    </span>
                  </div>
                </div>
              </section>
            )}

            {/* Two-column: Timeline + Trace Details */}
            <section className="obs-section obs-two-col">
              <div className="obs-col obs-col--wide">
                <h2>Timeline</h2>
                <Timeline
                  spans={spans}
                  requestCreatedAt={tree?.created_at}
                  totalMs={tree?.total_duration_ms}
                  onSelect={setSelectedSpan}
                  selected={selectedSpan}
                />
              </div>
              <div className="obs-col obs-col--narrow">
                <h2>Trace details</h2>
                <TraceDetails span={selectedSpan} />
              </div>
            </section>

            {/* Agent Graph */}
            <section className="obs-section">
              <h2>Agent graph</h2>
              <AgentGraph
                tree={tree}
                onSelect={setSelectedSpan}
                selected={selectedSpan}
              />
            </section>
          </>
        )}

        {/* Events feed — always visible */}
        <section className="obs-section">
          <EventsFeed events={events} />
        </section>
      </main>

      <style>{`
        .obs-section {
          margin-bottom: 2rem;
        }
        .obs-section h2 {
          font-size: 1rem;
          font-weight: 600;
          margin-bottom: 0.75rem;
          color: var(--text-secondary, #64748b);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .obs-empty {
          color: var(--text-secondary, #64748b);
          font-style: italic;
        }
        .obs-loading {
          color: var(--text-secondary, #64748b);
        }
        .obs-select {
          width: 100%;
          max-width: 640px;
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          border: 1px solid var(--border, #334155);
          background: var(--surface, #1e293b);
          color: inherit;
          font-size: 0.9rem;
        }

        /* Metric summary cards */
        .obs-metric-row {
          display: flex;
          gap: 1rem;
          flex-wrap: wrap;
        }
        .obs-metric-card {
          flex: 1;
          min-width: 120px;
          background: var(--surface, #1e293b);
          border: 1px solid var(--border, #334155);
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }
        .obs-metric-label {
          font-size: 0.75rem;
          color: var(--text-secondary, #64748b);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }
        .obs-metric-value {
          font-size: 1.25rem;
          font-weight: 700;
        }

        /* Two-column layout */
        .obs-two-col {
          display: flex;
          gap: 1.5rem;
          align-items: flex-start;
        }
        .obs-col { flex: 1; }
        .obs-col--wide { flex: 2; }
        .obs-col--narrow { flex: 1; min-width: 260px; }
        @media (max-width: 768px) {
          .obs-two-col { flex-direction: column; }
        }

        /* Timeline */
        .timeline-wrap { display: flex; flex-direction: column; gap: 0.4rem; }
        .timeline-header {
          display: grid;
          grid-template-columns: 110px 1fr 64px;
          gap: 0.5rem;
          font-size: 0.75rem;
          color: var(--text-secondary, #64748b);
          padding-bottom: 0.25rem;
          border-bottom: 1px solid var(--border, #334155);
        }
        .timeline-row {
          display: grid;
          grid-template-columns: 110px 1fr 64px;
          gap: 0.5rem;
          align-items: center;
          cursor: pointer;
          border-radius: 4px;
          padding: 0.2rem 0;
          transition: background 0.15s;
        }
        .timeline-row:hover { background: rgba(255,255,255,0.04); }
        .timeline-row--selected { background: rgba(255,255,255,0.07); }
        .timeline-label {
          font-size: 0.8rem;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .timeline-track {
          position: relative;
          height: 22px;
          background: rgba(255,255,255,0.06);
          border-radius: 3px;
          overflow: hidden;
        }
        .timeline-bar {
          position: absolute;
          top: 0;
          height: 100%;
          border-radius: 3px;
          transition: opacity 0.15s;
        }
        .timeline-dur { font-size: 0.75rem; text-align: right; color: var(--text-secondary, #64748b); }
        .timeline-total { font-size: 0.8rem; color: var(--text-secondary, #64748b); margin-top: 0.5rem; }

        /* Graph */
        .graph-scroll { overflow-x: auto; }

        /* Trace details */
        .trace-details { font-size: 0.875rem; }
        .trace-details h3 { font-size: 0.95rem; margin-bottom: 0.75rem; }
        .trace-details-empty {
          color: var(--text-secondary, #64748b);
          font-style: italic;
          font-size: 0.875rem;
        }
        .trace-explanation {
          margin-top: 0.75rem;
          font-size: 0.8rem;
          line-height: 1.5;
        }
        .trace-explanation p { margin: 0.25rem 0 0; }
        .trace-error { color: #ef4444; }

        /* Events */
        .events-feed h3 { font-size: 1rem; margin-bottom: 0.75rem; }
        .events-scroll { max-height: 260px; overflow-y: auto; }
        .events-table td { padding: 0.3rem 0.5rem; }
        .events-table td:first-child { padding-left: 0.75rem; }
      `}</style>
    </>
  );
}
