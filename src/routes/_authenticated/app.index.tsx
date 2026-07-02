import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { sendChatMessage, createConversation, logTtsUsage } from "@/lib/voxa.functions";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/app/")({
  component: ChatPage,
});

type Personality = {
  id: string;
  name: string;
  avatar_emoji: string | null;
  voice_id: string | null;
  voices?: { name: string; elevenlabs_id: string } | null;
};

type Message = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};

function ChatPage() {
  const qc = useQueryClient();
  const sendFn = useServerFn(sendChatMessage);
  const createFn = useServerFn(createConversation);
  const logTtsFn = useServerFn(logTtsUsage);

  const [activePersonality, setActivePersonality] = useState<Personality | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load personalities (with voices)
  const { data: personalities } = useQuery({
    queryKey: ["personalities"],
    queryFn: async () => {
      const { data } = await supabase
        .from("bot_personalities")
        .select("id, name, avatar_emoji, voice_id, voices:voices(name, elevenlabs_id)")
        .order("created_at", { ascending: false });
      return (data ?? []) as unknown as Personality[];
    },
  });

  // Preferred speaker voice from Settings (used when no persona voice is set)
  const { data: settingsVoice } = useQuery({
    queryKey: ["settings-voice"],
    refetchOnWindowFocus: true,
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return null;
      const { data, error } = await supabase
        .from("user_settings")
        .select("voices:voice_id(name, elevenlabs_id)")
        .eq("user_id", user.id)
        .maybeSingle();
      if (error) return null;
      return (data as unknown as { voices?: { name: string; elevenlabs_id: string } } | null)?.voices ?? null;
    },
  });

  // Most recent conversation for this user (so history survives reloads)
  const latestConv = useQuery({
    queryKey: ["latest-conversation"],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return null;
      const { data } = await supabase
        .from("conversations")
        .select("id")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      return data?.id ?? null;
    },
  });

  // Load messages for current conversation
  const { data: messages } = useQuery({
    queryKey: ["messages", conversationId],
    enabled: !!conversationId,
    queryFn: async () => {
      const { data } = await supabase
        .from("messages")
        .select("id, role, content, created_at")
        .eq("conversation_id", conversationId!)
        .order("created_at", { ascending: true });
      return (data ?? []) as Message[];
    },
  });

  // Resume the most recent conversation on load. A new one is created lazily on
  // first send (see ensureConversation), so we never make empty conversations.
  useEffect(() => {
    if (conversationId) return;
    if (latestConv.data) setConversationId(latestConv.data);
  }, [conversationId, latestConv.data]);

  // Guarantee a conversation exists, creating one on demand. Returns its id.
  const ensureConversation = async () => {
    if (conversationId) return conversationId;
    const conv = await createFn({ data: { personalityId: activePersonality?.id ?? null } });
    setConversationId(conv.id);
    qc.invalidateQueries({ queryKey: ["latest-conversation"] });
    return conv.id;
  };

  // Auto-pick first personality
  useEffect(() => {
    if (!activePersonality && personalities && personalities.length > 0) {
      setActivePersonality(personalities[0]);
    }
  }, [personalities, activePersonality]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages?.length]);

  const sendMut = useMutation({
    mutationFn: async (text: string) => {
      const convId = await ensureConversation();
      const result = await sendFn({
        data: { conversationId: convId, personalityId: activePersonality?.id ?? null, message: text },
      });
      return { convId, result };
    },
    onSuccess: async ({ convId, result }) => {
      qc.invalidateQueries({ queryKey: ["messages", convId] });
      qc.invalidateQueries({ queryKey: ["usage"] });
      if (result?.message) {
        await playTts(result.message.id, result.message.content);
      }
    },
    onError: (e) => {
      // The user's message is persisted before the AI call, so surface it even on failure.
      qc.invalidateQueries({ queryKey: ["messages"] });
      console.error("[chat] send failed:", e);
      const msg =
        e instanceof Error ? e.message : typeof e === "string" ? e : JSON.stringify(e);
      toast.error(msg || "Send failed");
    },
  });

  const playTts = async (msgId: string, text: string) => {
    setSpeakingId(msgId);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) throw new Error("Not signed in");
      const voice = activePersonality?.voices?.elevenlabs_id || settingsVoice?.elevenlabs_id || "alloy";
      const resp = await fetch("/api/tts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ text, voice }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      await audio.play();
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setSpeakingId(null);
        logTtsFn({
          data: {
            messageId: msgId,
            characters: text.length,
            audioSeconds: Math.ceil(audio.duration || text.length / 15),
          },
        });
        qc.invalidateQueries({ queryKey: ["usage"] });
      };
    } catch (e) {
      setSpeakingId(null);
      toast.error(e instanceof Error ? e.message : "Playback failed");
    }
  };

  return (
    <div className="grid h-screen grid-cols-1 lg:grid-cols-[1fr_320px]">
      {/* Conversation column */}
      <section className="flex h-full flex-col min-w-0">
        <header className="hairline-b border-b border-ink/15 flex items-center justify-between px-6 py-4">
          <div>
            <div className="font-mono-label text-muted-foreground">VOXA.CHAT</div>
            <div className="font-display text-xl mt-0.5">
              {activePersonality?.name ?? "Untitled agent"}
            </div>
          </div>
          <div className="font-mono-label text-muted-foreground text-right">
            VOICE / {(activePersonality?.voices?.name ?? settingsVoice?.name ?? "Alloy").toUpperCase()}
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-8">
          <div className="mx-auto max-w-2xl space-y-6">
            {!messages?.length && (
              <EmptyState personality={activePersonality} />
            )}
            {messages?.map((m) => (
              <MessageRow
                key={m.id}
                msg={m}
                speaking={speakingId === m.id}
                onSpeak={() => playTts(m.id, m.content)}
              />
            ))}
            {sendMut.isPending && <TypingIndicator />}
          </div>
        </div>

        <footer className="hairline-t border-t border-ink/15 p-4">
          <div className="mx-auto max-w-2xl">
            <Composer
              value={input}
              onChange={setInput}
              onSubmit={() => {
                if (!input.trim() || sendMut.isPending) return;
                const text = input.trim();
                setInput("");
                sendMut.mutate(text);
              }}
              onVoiceSubmit={(text) => {
                const trimmed = text.trim();
                if (!trimmed || sendMut.isPending) return;
                sendMut.mutate(trimmed);
              }}
              busy={sendMut.isPending}
            />
          </div>
        </footer>
      </section>

      {/* Persona panel */}
      <aside className="hairline-l border-l border-ink/15 hidden lg:flex flex-col bg-paper">
        <div className="hairline-b border-b border-ink/15 p-5">
          <div className="font-mono-label text-muted-foreground">PERSONAS</div>
          <div className="font-display text-2xl mt-1">Cast</div>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {personalities?.length === 0 && (
            <div className="p-6 text-sm text-muted-foreground">
              No personas yet.
            </div>
          )}
          {personalities?.map((p) => (
            <button
              key={p.id}
              onClick={() => setActivePersonality(p)}
              className={`hairline w-full border text-left p-4 transition ${
                activePersonality?.id === p.id
                  ? "border-ink bg-ink text-paper"
                  : "border-ink/15 hover:border-ink/40"
              }`}
            >
              <div className="flex items-baseline justify-between">
                <span className="font-display text-lg">{p.name}</span>
                <span className={`font-mono-label ${activePersonality?.id === p.id ? "text-paper/60" : "text-muted-foreground"}`}>
                  {p.avatar_emoji}
                </span>
              </div>
              {p.voices && (
                <div className={`font-mono-label mt-1 ${activePersonality?.id === p.id ? "text-paper/60" : "text-muted-foreground"}`}>
                  VOICE / {p.voices.name.toUpperCase()}
                </div>
              )}
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}

function EmptyState({ personality }: { personality: Personality | null }) {
  return (
    <div className="text-center py-20">
      <div className="font-mono-label text-muted-foreground">READY / TRANSMITTING</div>
      <h2 className="font-display text-5xl mt-3 leading-tight">
        Say something <em>worth</em><br /> remembering.
      </h2>
      <p className="text-muted-foreground mt-4 max-w-md mx-auto">
        {personality
          ? `You're talking to ${personality.name}. Replies play aloud automatically — or tap the mic to speak.`
          : "Type a message, or tap the mic to start a voice conversation."}
      </p>
    </div>
  );
}

function MessageRow({
  msg, speaking, onSpeak,
}: { msg: Message; speaking: boolean; onSpeak: () => void }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-2`}>
        <div className="font-mono-label text-muted-foreground">
          {isUser ? "YOU" : "AGENT"} · {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>
        <div
          className={`hairline px-4 py-3 ${
            isUser
              ? "bg-ink text-paper border border-ink"
              : "bg-paper border border-ink/15"
          }`}
        >
          <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
        </div>
        {!isUser && (
          <button
            onClick={onSpeak}
            className="font-mono-label flex items-center gap-2 text-muted-foreground hover:text-ink"
          >
            {speaking ? <SpeakingBars /> : <PlayIcon />}
            <span>{speaking ? "PLAYING" : "PLAY"}</span>
          </button>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 items-center text-muted-foreground">
      <span className="font-mono-label">AGENT THINKING</span>
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span key={i} className="wave-bar inline-block w-1 h-3 bg-ink" style={{ animationDelay: `${i * 0.15}s` }} />
        ))}
      </span>
    </div>
  );
}

function SpeakingBars() {
  return (
    <span className="flex gap-0.5 items-end h-3">
      {[0,1,2,3].map((i) => (
        <span key={i} className="wave-bar inline-block w-0.5 bg-accent" style={{ height: "100%", animationDelay: `${i*0.1}s` }} />
      ))}
    </span>
  );
}

function PlayIcon() {
  return <svg width="10" height="10" viewBox="0 0 14 14" fill="currentColor"><path d="M2 1.5v11l10-5.5z" /></svg>;
}

function Composer({
  value, onChange, onSubmit, onVoiceSubmit, busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onVoiceSubmit: (text: string) => void;
  busy: boolean;
}) {
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      className="hairline flex items-end gap-2 border border-ink/25 bg-paper p-2 focus-within:border-ink"
    >
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSubmit(); }
        }}
        rows={1}
        placeholder="Say something worth remembering…"
        className="flex-1 resize-none bg-transparent px-2 py-2 outline-none placeholder:text-ink/30"
        style={{ minHeight: 36, maxHeight: 200 }}
      />
      <MicButton disabled={busy} onTranscript={onVoiceSubmit} />
      <button
        type="submit" disabled={busy || !value.trim()}
        className="hairline border border-ink bg-ink px-4 py-2 text-paper font-mono-label hover:bg-accent hover:text-ink disabled:opacity-40 disabled:hover:bg-ink disabled:hover:text-paper"
      >
        {busy ? "..." : "SEND"}
      </button>
    </form>
  );
}

function MicButton({ disabled, onTranscript }: { disabled: boolean; onTranscript: (text: string) => void }) {
  const [listening, setListening] = useState(false);
  const recRef = useRef<any>(null);

  useEffect(() => () => recRef.current?.abort?.(), []);

  const toggle = () => {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      toast.error("Voice input isn't supported in this browser. Try Chrome or Edge.");
      return;
    }
    const rec = new SR();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e: any) => {
      const text = Array.from(e.results)
        .map((r: any) => r[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (text) onTranscript(text);
    };
    rec.onerror = (e: any) => {
      if (e.error !== "aborted" && e.error !== "no-speech") {
        toast.error(`Voice error: ${e.error}`);
      }
      setListening(false);
    };
    rec.onend = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled}
      title={listening ? "Listening… click to stop" : "Speak to send"}
      aria-pressed={listening}
      className={`hairline border px-3 py-2 font-mono-label transition disabled:opacity-40 ${
        listening
          ? "border-accent bg-accent text-ink animate-pulse"
          : "border-ink/25 hover:bg-ink hover:text-paper"
      }`}
    >
      {listening ? "● REC" : <MicIcon />}
    </button>
  );
}

function MicIcon() {
  return (
    <svg width="12" height="14" viewBox="0 0 12 16" fill="currentColor" aria-hidden="true">
      <path d="M6 0a2.5 2.5 0 0 0-2.5 2.5v5a2.5 2.5 0 0 0 5 0v-5A2.5 2.5 0 0 0 6 0z" />
      <path d="M10 7a4 4 0 0 1-8 0H.8a5.2 5.2 0 0 0 4.4 5.14V16h1.6v-3.86A5.2 5.2 0 0 0 11.2 7H10z" />
    </svg>
  );
}
