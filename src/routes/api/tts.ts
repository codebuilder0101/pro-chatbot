import { createFileRoute } from "@tanstack/react-router";
import { createClient } from "@supabase/supabase-js";
import type { Database } from "@/integrations/supabase/types";

/**
 * POST /api/tts — proxies to OpenAI text-to-speech (gpt-4o-mini-tts).
 * Returns raw MP3 bytes. Requires bearer token of an authenticated user.
 * Body: { text: string, voice?: string }
 */
export const Route = createFileRoute("/api/tts")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const auth = request.headers.get("authorization") ?? "";
        const token = auth.replace(/^Bearer\s+/i, "");
        if (!token) return new Response("Unauthorized", { status: 401 });

        const SUPABASE_URL = process.env.SUPABASE_URL!;
        const SUPABASE_PUBLISHABLE_KEY = process.env.SUPABASE_PUBLISHABLE_KEY!;
        const supabase = createClient<Database>(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
          global: { headers: { Authorization: `Bearer ${token}` } },
          auth: { persistSession: false, autoRefreshToken: false },
        });
        const { data: claims, error: claimsErr } = await supabase.auth.getClaims(token);
        if (claimsErr || !claims?.claims?.sub) {
          return new Response("Unauthorized", { status: 401 });
        }

        const body = (await request.json()) as { text?: string; voice?: string };
        const text = (body.text ?? "").slice(0, 4000);
        const voice = body.voice || "alloy";
        if (!text) return new Response("Missing text", { status: 400 });

        const apiKey = process.env.OPENAI_API_KEY;
        if (!apiKey) return new Response("Missing OPENAI_API_KEY", { status: 500 });

        const r = await fetch("https://api.openai.com/v1/audio/speech", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model: "gpt-4o-mini-tts",
            input: text,
            voice,
            response_format: "mp3",
          }),
        });

        if (!r.ok) {
          const t = await r.text();
          return new Response(t, { status: r.status });
        }
        const buf = await r.arrayBuffer();
        return new Response(buf, {
          headers: {
            "Content-Type": "audio/mpeg",
            "Cache-Control": "no-store",
          },
        });
      },
    },
  },
});
