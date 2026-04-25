"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { RateLimitError, extractAnswer, sendChat } from "./orchestrator";
import type { Session, UIMessage } from "./types";
import type { ChatRequestInput } from "./validation";
import { generateSessionId } from "./utils";

interface ChatState {
  sessions: Record<string, Session>;
  order: string[]; // session IDs newest-first
  activeSessionId: string | null;
  sending: boolean;

  ensureActive: () => string;
  newSession: () => string;
  setActive: (id: string) => void;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  send: (query: string) => Promise<void>;
  clearAll: () => void;
}

function truncateTitle(text: string): string {
  const trimmed = text.trim().replace(/\s+/g, " ");
  if (trimmed.length <= 48) return trimmed;
  return `${trimmed.slice(0, 45)}…`;
}

function emptySession(): Session {
  return {
    id: generateSessionId(),
    title: "New chat",
    createdAt: Date.now(),
    messages: [],
  };
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      sessions: {},
      order: [],
      activeSessionId: null,
      sending: false,

      ensureActive: () => {
        const state = get();
        if (state.activeSessionId && state.sessions[state.activeSessionId]) {
          return state.activeSessionId;
        }
        return get().newSession();
      },

      newSession: () => {
        const session = emptySession();
        set((state) => ({
          sessions: { ...state.sessions, [session.id]: session },
          order: [session.id, ...state.order],
          activeSessionId: session.id,
        }));
        return session.id;
      },

      setActive: (id) => set({ activeSessionId: id }),

      deleteSession: (id) =>
        set((state) => {
          const { [id]: _removed, ...rest } = state.sessions;
          const order = state.order.filter((sid) => sid !== id);
          const activeSessionId =
            state.activeSessionId === id ? (order[0] ?? null) : state.activeSessionId;
          return { sessions: rest, order, activeSessionId };
        }),

      renameSession: (id, title) =>
        set((state) => {
          const session = state.sessions[id];
          if (!session) return state;
          return {
            sessions: {
              ...state.sessions,
              [id]: { ...session, title: truncateTitle(title) },
            },
          };
        }),

      clearAll: () => set({ sessions: {}, order: [], activeSessionId: null }),

      send: async (query) => {
        const trimmed = query.trim();
        if (!trimmed) return;

        const sessionId = get().ensureActive();
        const userMessage: UIMessage = {
          id: crypto.randomUUID(),
          role: "user",
          content: trimmed,
          timestamp: Date.now(),
        };
        const assistantPlaceholder: UIMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: Date.now(),
          pending: true,
        };

        set((state) => {
          const session = state.sessions[sessionId];
          if (!session) return state;
          const isFirstUserTurn = session.messages.length === 0;
          const nextSession: Session = {
            ...session,
            title: isFirstUserTurn ? truncateTitle(trimmed) : session.title,
            messages: [...session.messages, userMessage, assistantPlaceholder],
          };
          return {
            sessions: { ...state.sessions, [sessionId]: nextSession },
            sending: true,
          };
        });

        // The browser only sends intent fields. The Next.js proxy at
        // /api/chat generates request_id, stamps user_id from the (future)
        // authenticated session, adds X-Internal-Key, and forwards to the
        // orchestrator. See apps/web/app/api/chat/route.ts + lib/validation.ts.
        const payload: ChatRequestInput = {
          query: trimmed,
          session_id: sessionId,
          metadata: { source: "web" },
        };

        try {
          const reply = await sendChat(payload);
          set((state) => {
            const session = state.sessions[sessionId];
            if (!session) return state;
            const messages = session.messages.map((m) =>
              m.id === assistantPlaceholder.id
                ? {
                    ...m,
                    pending: false,
                    reply,
                    content: extractAnswer(reply),
                  }
                : m
            );
            return {
              sessions: { ...state.sessions, [sessionId]: { ...session, messages } },
              sending: false,
            };
          });
        } catch (err) {
          const message =
            err instanceof RateLimitError
              ? `Rate limit exceeded. Retry in ${err.retryAfterSeconds}s.`
              : err instanceof Error
                ? err.message
                : "Unknown error.";
          set((state) => {
            const session = state.sessions[sessionId];
            if (!session) return state;
            const messages = session.messages.map((m) =>
              m.id === assistantPlaceholder.id
                ? { ...m, pending: false, error: message, content: message }
                : m
            );
            return {
              sessions: { ...state.sessions, [sessionId]: { ...session, messages } },
              sending: false,
            };
          });
        }
      },
    }),
    {
      name: "meridian-chat-v1",
      partialize: (state) => ({
        sessions: state.sessions,
        order: state.order,
        activeSessionId: state.activeSessionId,
      }),
    }
  )
);
