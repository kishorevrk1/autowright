"use client";

import { useState } from "react";
import ChatInput from "@/components/ChatInput";
import TaskFeed from "@/components/TaskFeed";
import PodStatus from "@/components/PodStatus";

export interface Task {
  id: string;
  repoUrl: string;
  requirement: string;
  workflowId: string;
}

export default function Home() {
  const [tasks, setTasks] = useState<Task[]>([]);

  function handleTaskCreated(task: Task) {
    setTasks((prev) => [task, ...prev]);
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">
          OpenClaw <span className="text-zinc-500 font-normal">/ Manager</span>
        </h1>
        <PodStatus />
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col max-w-3xl w-full mx-auto px-4 py-8 gap-6">
        <ChatInput onTaskCreated={handleTaskCreated} />

        {tasks.length === 0 ? (
          <p className="text-center text-zinc-600 text-sm mt-16">
            Send a requirement above to get started.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {tasks.map((task) => (
              <TaskFeed key={task.id} task={task} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
