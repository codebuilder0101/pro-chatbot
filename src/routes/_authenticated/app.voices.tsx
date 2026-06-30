import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/app/voices")({
  component: VoicesPage,
});

function VoicesPage() {
  const [playing, setPlaying] = useState<string | null>(null);

  const { data: voices } = useQuery({
    queryKey: ["voices-full"],
    queryFn: async () => {
      const { data } = await supabase
        .from("voices")
        .select("id, name, elevenlabs_id, tone, preview_text")
        .order("name");
      return data ?? [];
    },
  });

  const preview = async (id: string, voiceId: string, text: string) => {
    setPlaying(id);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const r = await fetch("/api/tts", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session?.access_token}`,
        },
        body: JSON.stringify({ text, voice: voiceId }),
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
    <div className="p-6 lg:p-10 max-w-6xl">
      <header className="mb-10">
        <div className="font-mono-label text-muted-foreground">VOICE.LIBRARY</div>
        <h1 className="font-display text-6xl mt-2 leading-none">
          Voices, <em>auditioned.</em>
        </h1>
        <p className="text-muted-foreground mt-3 max-w-xl">
          Eight house voices, each tuned for tone and pacing. Click any to hear it speak its line.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {voices?.map((v, i) => (
          <button
            key={v.id}
            onClick={() => preview(v.id, v.elevenlabs_id, v.preview_text ?? "Hello.")}
            className="hairline border border-ink/15 p-5 text-left hover:border-ink transition group"
          >
            <div className="flex items-baseline justify-between">
              <div>
                <span className="font-mono-label text-muted-foreground mr-2">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="font-display text-3xl">{v.name}</span>
              </div>
              <span className="font-mono-label text-muted-foreground group-hover:text-ink">
                {playing === v.id ? "● PLAYING" : "▶ PLAY"}
              </span>
            </div>
            <div className="font-mono-label text-muted-foreground mt-2">{v.tone}</div>
            <div className="mt-4 font-display italic text-ink/80">"{v.preview_text}"</div>
          </button>
        ))}
      </div>
    </div>
  );
}
