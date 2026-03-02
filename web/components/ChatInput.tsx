"use client";

import { useState, FormEvent } from "react";
import { SendHorizonal } from "lucide-react";
import type { Task } from "@/app/page";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface Props {
  onTaskCreated: (task: Task) => void;
}

export default function ChatInput({ onTaskCreated }: Props) {
  const [repoUrl, setRepoUrl] = useState("");
  const [requirement, setRequirement] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!repoUrl.trim() || !requirement.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl.trim(), requirement: requirement.trim() }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }

      const data = await res.json();
      onTaskCreated({
        id: data.task_id,
        repoUrl: data.repo_url,
        requirement: data.requirement,
        workflowId: data.workflow_id,
      });

      setRepoUrl("");
      setRequirement("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <input
        type="url"
        placeholder="Repository URL  (e.g. https://github.com/you/repo)"
        value={repoUrl}
        onChange={(e) => setRepoUrl(e.target.value)}
        className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-4 py-2.5 text-sm
                   placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500"
        required
      />
      <div className="flex gap-2">
        <textarea
          placeholder="Describe what you want the agents to build or change..."
          value={requirement}
          onChange={(e) => setRequirement(e.target.value)}
          rows={3}
          className="flex-1 rounded-lg bg-zinc-900 border border-zinc-700 px-4 py-2.5 text-sm
                     placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-zinc-500 resize-none"
          required
        />
        <button
          type="submit"
          disabled={loading}
          className="self-end rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50
                     px-4 py-2.5 text-sm font-medium transition-colors flex items-center gap-1.5"
        >
          <SendHorizonal size={15} />
          {loading ? "Sending..." : "Send"}
        </button>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
    </form>
  );
}
