"use client";

import { create } from "zustand";

import {
  RateLimitError,
  createSession as apiCreateSession,
  deleteSession as apiDeleteSession,
  extractAnswer,
  listMessages,
  listSessions,
  renameSession as apiRenameSession,
  sendChat,
} from "./orchestrator";
import type { ServerSession, UIMessage } from "./types";

/**
 * Server-side sessions store. Local state is a cache + optimistic UI; the
 * source of truth is Postgres. Every mutation talks to /api/* which forwards
 * to the orchestrator with the authenticated workspace context.
 */
interface ChatState {
  sessions: Record<string, ServerSession>;
  order: string[]; // newest first
  messagesBySession: Record<string, UIMessage[]>;
  activeSessionId: string | null;
  loadingSessions: boolean;
  loadingMessages: boolean;
  sending: boolean;
  error: string | null;

  loadSessions: () => Promise<void>;
  setActive: (id: string) => Promise<void>;
  newSession: (title?: string) => Promise<string>;
  renameSession: (id: string, title: string) => Promise<void>;
  removeSession: (id: string) => Promise<void>;
  send: (query: string) => Promise<void>;
}

function indexSessions(rows: ServerSession[]): {
  sessions: Record<string, ServerSession>;
  order: string[];
} {
  const sessions: Record<string, ServerSession> = {};
  const order: string[] = [];
  for (const row of rows) {
    sessions[row.id] = row;
    order.push(row.id);
  }
  return { sessions, order };
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: {},
  order: [],
  messagesBySession: {},
  activeSessionId: null,
  loadingSessions: false,
  loadingMessages: false,
  sending: false,
  error: null,

  loadSessions: async () => {
    set({ loadingSessions: true, error: null });
    try {
      const rows = await listSessions();
      const indexed = indexSessions(rows);
      set({
        ...indexed,
        loadingSessions: false,
        // Only auto-pick the first session if nothing is active yet.
        activeSessionId: get().activeSessionId ?? indexed.order[0] ?? null,
      });
      const active = get().activeSessionId;
      if (active) await get().setActive(active);
    } catch (err) {
      set({
        loadingSessions: false,
        error: err instanceof Error ? err.message : "failed to load sessions",
      });
    }
  },

  setActive: async (id) => {
    set({ activeSessionId: id, loadingMessages: true, error: null });
    try {
      const messages = await listMessages(id);
      const ui: UIMessage[] = messages.map((m) => ({
        id: m.id,
        role: m.role === "system" ? "assistant" : (m.role as "user" | "assistant"),
        content: m.content,
        timestamp: new Date(m.created_at).getTime(),
        reply: m.reply ?? undefined,
      }));
      set((state) => ({
        messagesBySession: { ...state.messagesBySession, [id]: ui },
        loadingMessages: false,
      }));
    } catch (err) {
      set({
        loadingMessages: false,
        error: err instanceof Error ? err.message : "failed to load messages",
      });
    }
  },

  newSession: async (title?: string) => {
    const session = await apiCreateSession(title);
    set((state) => ({
      sessions: { ...state.sessions, [session.id]: session },
      order: [session.id, ...state.order.filter((sid) => sid !== session.id)],
      activeSessionId: session.id,
      messagesBySession: { ...state.messagesBySession, [session.id]: [] },
    }));
    return session.id;
  },

  renameSession: async (id, title) => {
    const updated = await apiRenameSession(id, title);
    set((state) => ({
      sessions: { ...state.sessions, [id]: updated },
    }));
  },

  removeSession: async (id) => {
    await apiDeleteSession(id);
    set((state) => {
      const { [id]: _drop, ...rest } = state.sessions;
      const order = state.order.filter((sid) => sid !== id);
      const activeSessionId = state.activeSessionId === id ? (order[0] ?? null) : state.activeSessionId;
      const { [id]: _msgs, ...msgs } = state.messagesBySession;
      return { sessions: rest, order, messagesBySession: msgs, activeSessionId };
    });
  },

  send: async (query) => {
    const trimmed = query.trim();
    if (!trimmed) return;

    let sessionId = get().activeSessionId;
    if (!sessionId) {
      sessionId = await get().newSession(trimmed.slice(0, 64));
    }

    const userMessage: UIMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
    };
    const placeholder: UIMessage = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      pending: true,
    };

    // Optimistic local append.
    set((state) => {
      const existing = state.messagesBySession[sessionId!] ?? [];
      return {
        messagesBySession: {
          ...state.messagesBySession,
          [sessionId!]: [...existing, userMessage, placeholder],
        },
        sending: true,
      };
    });

    try {
      const reply = await sendChat({
        session_id: sessionId,
        query: trimmed,
        metadata: { source: "web" },
      });
      set((state) => {
        const messages = (state.messagesBySession[sessionId!] ?? []).map((m) =>
          m.id === placeholder.id
            ? {
                ...m,
                pending: false,
                reply,
                content: extractAnswer(reply),
              }
            : m
        );
        return {
          messagesBySession: { ...state.messagesBySession, [sessionId!]: messages },
          sending: false,
        };
      });
    } catch (err) {
      const detail =
        err instanceof RateLimitError
          ? `Rate limit exceeded. Retry in ${err.retryAfterSeconds}s.`
          : err instanceof Error
            ? err.message
            : "Unknown error.";
      set((state) => {
        const messages = (state.messagesBySession[sessionId!] ?? []).map((m) =>
          m.id === placeholder.id
            ? { ...m, pending: false, error: detail, content: detail }
            : m
        );
        return {
          messagesBySession: { ...state.messagesBySession, [sessionId!]: messages },
          sending: false,
        };
      });
    }
  },
}));
