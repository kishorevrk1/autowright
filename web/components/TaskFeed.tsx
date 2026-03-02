"use client";

import { useEffect, useRef, useState } from "react";
import {
  CheckCircle,
  Circle,
  GitBranch,
  GitCommit,
  Loader2,
  ShieldCheck,
  ShieldX,
  XCircle,
} from "lucide-react";
import type { Task } from "@/app/page";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL;

interface ResultPayload {
  branch?: string;
  commit_sha?: string;
  summary?: string;
  files_changed?: string[];
  qa_verdict?: string;
  qa_feedback?: string;
  planning_used?: boolean;
}

interface Props {
  task: Task;
}

// Pipeline stages in order
const PIPELINE_STAGES = [
  { key: "classifying", label: "Classify" },
  { key: "analyzing", label: "Analyze" },
  { key: "planning", label: "Plan" },
  { key: "architecting", label: "Architect" },
  { key: "writing_stories", label: "Stories" },
  { key: "developing", label: "Develop" },
  { key: "reviewing", label: "Review" },
] as const;

type StageKey = (typeof PIPELINE_STAGES)[number]["key"];

export default function TaskFeed({ task }: Props) {
  const [status, setStatus] = useState<"running" | "done" | "failed">("running");
  const [currentStage, setCurrentStage] = useState<StageKey | null>(null);
  const [completedStages, setCompletedStages] = useState<Set<StageKey>>(new Set());
  const [result, setResult] = useState<ResultPayload | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const prevStageRef = useRef<StageKey | null>(null);

  useEffect(() => {
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
        setCurrentStage(null);
        // Mark all stages as completed
        setCompletedStages(new Set(PIPELINE_STAGES.map((s) => s.key)));
      } else if (["FAILED", "TIMED_OUT", "TERMINATED"].includes(wfStatus)) {
        setErrorMsg("Workflow ended with non-success status: " + wfStatus);
        setStatus("failed");
      } else {
        setStatus("running");
        setErrorMsg(null);

        // Derive current stage from pending activities
        const activities: string[] = msg.pending_activities ?? [];
        if (activities.length > 0) {
          const stage = activities[0] as StageKey;
          setCurrentStage(stage);

          // Mark previous stage as completed when we move to a new one
          if (prevStageRef.current && prevStageRef.current !== stage) {
            setCompletedStages((prev) => new Set([...prev, prevStageRef.current!]));
          }
          prevStageRef.current = stage;
        }
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

  // Determine which stages to show (skip planning stages for quick flow if done)
  const skippedPlanning =
    status === "done" && result && result.planning_used === false;

  const visibleStages = skippedPlanning
    ? PIPELINE_STAGES.filter(
        (s) => !["analyzing", "planning", "architecting", "writing_stories"].includes(s.key)
      )
    : PIPELINE_STAGES;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 flex flex-col gap-4">
      {/* Requirement header */}
      <div>
        <p className="text-xs text-zinc-500 mb-1 truncate">{task.repoUrl}</p>
        <p className="text-sm font-medium leading-snug">{task.requirement}</p>
      </div>

      {/* Pipeline stepper */}
      {status !== "failed" && (
        <div className="flex items-center gap-1 overflow-x-auto py-1">
          {visibleStages.map((stage, i) => {
            const isCompleted = completedStages.has(stage.key) || status === "done";
            const isCurrent = currentStage === stage.key && status === "running";
            const isFuture = !isCompleted && !isCurrent;

            return (
              <div key={stage.key} className="flex items-center">
                <div className="flex flex-col items-center gap-1">
                  <div className="flex items-center justify-center w-5 h-5">
                    {isCompleted && (
                      <CheckCircle size={14} className="text-emerald-400" />
                    )}
                    {isCurrent && (
                      <Loader2 size={14} className="animate-spin text-indigo-400" />
                    )}
                    {isFuture && (
                      <Circle size={14} className="text-zinc-700" />
                    )}
                  </div>
                  <span
                    className={`text-[10px] font-medium whitespace-nowrap ${
                      isCompleted
                        ? "text-emerald-400"
                        : isCurrent
                        ? "text-indigo-300"
                        : "text-zinc-600"
                    }`}
                  >
                    {stage.label}
                  </span>
                </div>
                {i < visibleStages.length - 1 && (
                  <div
                    className={`w-4 h-px mx-0.5 mt-[-12px] ${
                      isCompleted ? "bg-emerald-700" : "bg-zinc-800"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Error state */}
      {status === "failed" && (
        <div className="flex items-center gap-2">
          <XCircle size={16} className="text-red-400" />
          <span className="text-xs text-red-400 font-medium">Failed</span>
        </div>
      )}

      {/* Error message */}
      {errorMsg && (
        <p className="text-xs text-red-400 bg-red-950/30 rounded-lg px-3 py-2">{errorMsg}</p>
      )}

      {/* Result details */}
      {status === "done" && result && (
        <div className="flex flex-col gap-3 border-t border-zinc-800 pt-3">
          {/* QA Verdict */}
          {result.qa_verdict && (
            <div className="flex items-center gap-2">
              {result.qa_verdict === "APPROVED" ? (
                <>
                  <ShieldCheck size={16} className="text-emerald-400" />
                  <span className="text-xs text-emerald-400 font-medium">QA: Approved</span>
                </>
              ) : (
                <>
                  <ShieldX size={16} className="text-amber-400" />
                  <span className="text-xs text-amber-400 font-medium">QA: {result.qa_verdict}</span>
                </>
              )}
            </div>
          )}

          {result.qa_feedback && (
            <p className="text-xs text-zinc-400 bg-zinc-800/50 rounded-lg px-3 py-2">
              {result.qa_feedback}
            </p>
          )}

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

          {/* Quick flow indicator */}
          {result.planning_used === false && (
            <p className="text-[10px] text-zinc-600">Quick flow — planning phases skipped</p>
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
