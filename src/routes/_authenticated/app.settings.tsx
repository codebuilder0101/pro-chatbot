import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/app/settings")({
  component: SettingsPage,
});

type Voice = {
  id: string;
  name: string;
  elevenlabs_id: string;
  tone: string | null;
  preview_text: string | null;
};

function SettingsPage() {
  const qc = useQueryClient();
  const [voiceId, setVoiceId] = useState<string | null>(null);
  const [age, setAge] = useState<string>("");
  const [playing, setPlaying] = useState<string | null>(null);

  const { data: voices } = useQuery({
    queryKey: ["voices-full"],
    queryFn: async () => {
      const { data } = await supabase
        .from("voices")
        .select("id, name, elevenlabs_id, tone, preview_text")
        .order("name");
      return (data ?? []) as Voice[];
    },
  });

  const { data: settings } = useQuery({
    queryKey: ["user-settings"],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return null;
      const { data } = await supabase
        .from("user_settings")
        .select("voice_id, speaker_age")
        .eq("user_id", user.id)
        .maybeSingle();
      return data;
    },
  });

  // Seed the form once settings load.
  useEffect(() => {
    if (settings) {
      setVoiceId(settings.voice_id ?? null);
      setAge(settings.speaker_age != null ? String(settings.speaker_age) : "");
    }
  }, [settings]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error("Not signed in");
      const parsedAge = age.trim() === "" ? null : Number(age);
      if (parsedAge !== null && (!Number.isFinite(parsedAge) || parsedAge < 1 || parsedAge > 120)) {
        throw new Error("Age must be between 1 and 120");
      }
      const { error } = await supabase.from("user_settings").upsert({
        user_id: user.id,
        voice_id: voiceId,
        speaker_age: parsedAge,
      });
      if (error) throw error;
    },
    onSuccess: () => {
      toast.success("Voice saved — your agent will speak with it.");
      qc.invalidateQueries({ queryKey: ["user-settings"] });
      // Refresh the chat's voice so the change applies immediately.
      qc.invalidateQueries({ queryKey: ["settings-voice"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Save failed"),
  });

  const savedVoice = voices?.find((v) => v.id === (settings?.voice_id ?? null)) ?? null;
  const dirty = voiceId !== (settings?.voice_id ?? null);

  const preview = async (id: string, voiceKey: string, text: string) => {
    setPlaying(id);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const r = await fetch("/api/tts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ text, voice: voiceKey }),
      });
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      audio.onended = () => setPlaying(null);
      await audio.play();
    } catch (e) {
      setPlaying(null);
      toast.error(e instanceof Error ? e.message : "Preview failed");
    }
  };

  return (
    <div className="p-6 lg:p-10 max-w-4xl">
      <header className="mb-10">
        <div className="font-mono-label text-muted-foreground">SETTINGS</div>
        <h1 className="font-display text-6xl mt-2 leading-none">
          Tune your <em>speaker.</em>
        </h1>
        <p className="text-muted-foreground mt-3 max-w-xl">
          Choose the house voice and the speaker age your agents should default to.
        </p>
        <div className="font-mono-label text-muted-foreground mt-4">
          ACTIVE VOICE / <span className="text-ink">{(savedVoice?.name ?? "Alloy").toUpperCase()}</span>
          {savedVoice ? "" : " (DEFAULT)"}
        </div>
      </header>

      {/* Speaker age */}
      <section className="mb-10">
        <div className="font-mono-label text-muted-foreground mb-2">SPEAKER AGE</div>
        <div className="flex items-center gap-3">
          <input
            type="number"
            min={1}
            max={120}
            value={age}
            onChange={(e) => setAge(e.target.value)}
            placeholder="e.g. 32"
            className="hairline w-40 border border-ink/25 bg-transparent px-3 py-2.5 outline-none focus:border-ink"
          />
          <span className="text-muted-foreground text-sm">years</span>
        </div>
      </section>

      {/* Speaker voice */}
      <section className="mb-10">
        <div className="font-mono-label text-muted-foreground mb-3">SPEAKER VOICE</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {voices?.map((v) => {
            const selected = voiceId === v.id;
            return (
              <div
                key={v.id}
                role="button"
                tabIndex={0}
                onClick={() => setVoiceId(v.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setVoiceId(v.id); }
                }}
                className={`hairline border p-5 text-left cursor-pointer transition ${
                  selected ? "border-ink bg-ink text-paper" : "border-ink/15 hover:border-ink"
                }`}
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-display text-3xl">{v.name}</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      preview(v.id, v.elevenlabs_id, v.preview_text ?? "Hello.");
                    }}
                    className={`font-mono-label ${selected ? "text-paper/70 hover:text-paper" : "text-muted-foreground hover:text-ink"}`}
                  >
                    {playing === v.id ? "● PLAYING" : "▶ PLAY"}
                  </button>
                </div>
                <div className={`font-mono-label mt-2 ${selected ? "text-paper/60" : "text-muted-foreground"}`}>
                  {v.tone}
                  {selected ? " · SELECTED" : ""}
                </div>
                <div className={`mt-3 font-display italic ${selected ? "text-paper/80" : "text-ink/80"}`}>
                  "{v.preview_text}"
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="flex items-center gap-4">
        <button
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending}
          className="hairline border border-ink bg-ink px-6 py-3 text-paper font-mono-label hover:bg-accent hover:text-ink disabled:opacity-50"
        >
          {saveMut.isPending ? "Saving..." : "Save settings"}
        </button>
        {dirty && !saveMut.isPending && (
          <span className="font-mono-label text-muted-foreground">UNSAVED CHANGES</span>
        )}
      </div>
    </div>
  );
}
