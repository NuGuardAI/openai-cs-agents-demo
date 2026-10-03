"use client";

import { useCallback, useEffect, useState } from "react";
import { AgentPanel } from "@/components/agent-panel";
import { ChatKitPanel } from "@/components/chatkit-panel";
import { LoginForm } from "@/components/login-form";
import type { Agent, AgentEvent, GuardrailCheck } from "@/lib/types";
import { callLogoutAPI, fetchBootstrapState, fetchThreadState } from "@/lib/api";

type AuthUser = {
  name: string;
  account_number: string;
  email: string;
};

export default function Home() {
  const [auth, setAuth] = useState<{ token: string; user: AuthUser } | null>(null);

  if (!auth) {
    return <LoginForm onLogin={(token, user) => setAuth({ token, user })} />;
  }

  const handleLogout = () => {
    void callLogoutAPI(auth.token);
    setAuth(null);
  };

  return <AuthenticatedHome key={auth.token} user={auth.user} onLogout={handleLogout} />;
}

function AuthenticatedHome({ user, onLogout }: { user: AuthUser; onLogout: () => void }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string>("");
  const [guardrails, setGuardrails] = useState<GuardrailCheck[]>([]);
  const [context, setContext] = useState<Record<string, any>>({});
  const [threadId, setThreadId] = useState<string | null>(null);
  const [initialThreadId, setInitialThreadId] = useState<string | null>(null);

  const normalizeEvents = useCallback((items: AgentEvent[]) => {
    if (!items.length) return items;
    const now = Date.now();
    const latestNonProgress = items
      .filter((e) => e.type !== "progress_update")
      .reduce((max, e) => Math.max(max, e.timestamp.getTime()), 0);
    const pruned = items.filter((e) => {
      if (e.type !== "progress_update") return true;
      const ts = e.timestamp.getTime();
      // Drop old progress once a newer non-progress exists, or after 15s
      if (latestNonProgress && ts < latestNonProgress) return false;
      if (now - ts > 15000) return false;
      return true;
    });
    return pruned;
  }, []);

  const hydrateState = useCallback(async (id: string | null) => {
    if (!id) return;
    const data = await fetchThreadState(id);
    if (!data) return;

    setCurrentAgent(data.current_agent || "");
    setContext(data.context || {});
    if (Array.isArray(data.agents)) setAgents(data.agents);
    if (Array.isArray(data.events)) {
      setEvents(
        data.events.map((e: any) => ({
          ...e,
          timestamp: new Date(e.timestamp ?? Date.now()),
        }))
      );
    }
    if (Array.isArray(data.guardrails)) {
      setGuardrails(
        data.guardrails.map((g: any) => ({
          ...g,
          timestamp: new Date(g.timestamp ?? Date.now()),
        }))
      );
    }
  }, []);

  useEffect(() => {
    if (threadId) {
      void hydrateState(threadId);
    }
  }, [threadId, hydrateState]);

  useEffect(() => {
    (async () => {
      const bootstrap = await fetchBootstrapState();
      if (!bootstrap) return;
      setInitialThreadId(bootstrap.thread_id || null);
      setThreadId(bootstrap.thread_id || null);
      if (bootstrap.current_agent) setCurrentAgent(bootstrap.current_agent);
      if (Array.isArray(bootstrap.agents)) setAgents(bootstrap.agents);
      if (bootstrap.context) setContext(bootstrap.context);
      if (Array.isArray(bootstrap.events)) {
        setEvents(
          normalizeEvents(
            bootstrap.events.map((e: any) => ({
              ...e,
              timestamp: new Date(e.timestamp ?? Date.now()),
            }))
          )
        );
      }
      if (Array.isArray(bootstrap.guardrails)) {
        setGuardrails(
          bootstrap.guardrails.map((g: any) => ({
            ...g,
            timestamp: new Date(g.timestamp ?? Date.now()),
          }))
        );
      }
    })();
  }, []);

  const handleThreadChange = useCallback((id: string | null) => {
    setThreadId(id);
  }, []);

  const handleBindThread = useCallback((id: string) => {
    setThreadId(id);
  }, []);

  const handleResponseEnd = useCallback(() => {
    void hydrateState(threadId);
  }, [hydrateState, threadId]);

  return (
    <main className="flex h-screen gap-2 bg-gray-100 p-2">
      <AgentPanel
        agents={agents}
        currentAgent={currentAgent}
        events={events}
        guardrails={guardrails}
        context={context}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="mb-2 flex items-center justify-between rounded-lg border bg-white px-4 py-2 text-sm">
          <span className="text-gray-600">
            Signed in as <span className="font-semibold text-gray-900">{user.name}</span>
            <span className="ml-2 font-mono text-xs text-gray-400">#{user.account_number}</span>
          </span>
          <button
            type="button"
            onClick={onLogout}
            className="text-xs text-gray-500 underline underline-offset-2 transition-colors hover:text-gray-900"
          >
            Sign out
          </button>
        </div>
        <ChatKitPanel
          initialThreadId={initialThreadId}
          onThreadChange={handleThreadChange}
          onResponseEnd={handleResponseEnd}
          onRunnerBindThread={handleBindThread}
        />
      </div>
    </main>
  );
}
