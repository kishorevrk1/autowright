"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle, GitBranch, GitCommit, Loader2, XCircle } from "lucide-react";
import type { Task } from "@/app/page";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL;

interface ResultPayload {
  branch?: string;
  commit_sha?: string;
  summary?: string;
  files_changed?: string[];
}

interface Props {
  task: Task;
}

export default function TaskFeed({ task }: Props) {
  const [status, setStatus] = useState<"running" | "done" | "failed">("running");
  const [result, setResult] = useState<ResultPayload | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // `active` guards against React Strict Mode's double-invoke: the first
    // effect instance is immediately cleaned up, closing the WS and firing
    // onerror. Without this flag, that spurious onerror would lock the UI to
    // "Failed" even though the second (real) WS is healthy.
    let active = true;

    const ws = new WebSocket(`${WS_URL}/ws/${task.id}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (!active) return;
      const msg = JSON.parse(event.data);

      if (msg.error) {
        setErrorMsg(msg.error);
        setStatus("failed");
        return;
      }

      const wfStatus: string = msg.workflow_status ?? "";

      if (wfStatus === "COMPLETED") {
        setResult(msg.result ?? {});
        setStatus("done");
      } else if (["FAILED", "TIMED_OUT", "TERMINATED"].includes(wfStatus)) {
        setErrorMsg("Workflow ended with non-success status: " + wfStatus);
        setStatus("failed");
      } else {
        // Recover from any transient error: if the workflow is still running
        // (RUNNING / UNKNOWN), reset to running state.
        setStatus("running");
        setErrorMsg(null);
      }
    };

    ws.onerror = () => {
      if (!active) return;
      setErrorMsg("WebSocket connection error");
      setStatus("failed");
    };

    return () => {
      active = false;
      ws.close();
    };
  }, [task.id]);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 flex flex-col gap-4">
      {/* Requirement header */}
      <div>
        <p className="text-xs text-zinc-500 mb-1 truncate">{task.repoUrl}</p>
        <p className="text-sm font-medium leading-snug">{task.requirement}</p>
      </div>

      {/* Status indicator */}
      <div className="flex items-center gap-2">
        {status === "running" && (
          <>
            <Loader2 size={16} className="animate-spin text-indigo-400" />
            <span className="text-xs text-indigo-300 font-medium">
              Agent working — writing · reviewing · committing
            </span>
          </>
        )}
        {status === "done" && (
          <>
            <CheckCircle size={16} className="text-emerald-400" />
            <span className="text-xs text-emerald-400 font-medium">Done</span>
          </>
        )}
        {status === "failed" && (
          <>
            <XCircle size={16} className="text-red-400" />
            <span className="text-xs text-red-400 font-medium">Failed</span>
          </>
        )}
      </div>

      {/* Error message */}
      {errorMsg && (
        <p className="text-xs text-red-400 bg-red-950/30 rounded-lg px-3 py-2">{errorMsg}</p>
      )}

      {/* Result details */}
      {status === "done" && result && (
        <div className="flex flex-col gap-3 border-t border-zinc-800 pt-3">
          {result.summary && (
            <p className="text-sm text-zinc-300 leading-relaxed">{result.summary}</p>
          )}

          <div className="flex flex-wrap gap-3">
            {result.branch && (
              <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                <GitBranch size={13} className="text-sky-400" />
                <span className="font-mono text-sky-300">{result.branch}</span>
              </div>
            )}
            {result.commit_sha && (
              <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                <GitCommit size={13} className="text-violet-400" />
                <span className="font-mono text-violet-300">{result.commit_sha.slice(0, 8)}</span>
              </div>
            )}
          </div>

          {result.files_changed && result.files_changed.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="text-xs text-zinc-500">
                {result.files_changed.length} file{result.files_changed.length !== 1 ? "s" : ""} changed
              </p>
              <ul className="flex flex-col gap-0.5 max-h-32 overflow-y-auto">
                {result.files_changed.map((f) => (
                  <li key={f} className="font-mono text-xs text-zinc-400 truncate">
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Temporal UI deep link */}
      <a
        href={`http://localhost:8080/namespaces/default/workflows/${task.workflowId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
      >
        View in Temporal UI →
      </a>
    </div>
  );
}
