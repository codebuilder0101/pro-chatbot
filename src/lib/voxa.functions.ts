import { createServerFn } from "@tanstack/react-start";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { z } from "zod";

const ChatInput = z.object({
  conversationId: z.string().uuid(),
  personalityId: z.string().uuid().nullable().optional(),
  message: z.string().min(1).max(8000),
});

/**
 * Send a chat message: persists user message, calls Lovable AI Gateway,
 * persists assistant reply, logs usage (characters).
 */
export const sendChatMessage = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d: unknown) => ChatInput.parse(d))
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;

    // Verify conversation ownership
    const { data: conv, error: convErr } = await supabase
      .from("conversations")
      .select("id, personality_id")
      .eq("id", data.conversationId)
      .single();
    if (convErr || !conv) throw new Error("Conversation not found");

    // Load personality (system prompt + voice + temp)
    const personalityId = data.personalityId ?? conv.personality_id;
    let systemPrompt = "You are VOXA, a warm, articulate AI with editorial taste. Keep replies concise and human.";
    let temperature = 0.7;
    if (personalityId) {
      const { data: p } = await supabase
        .from("bot_personalities")
        .select("system_prompt, temperature")
        .eq("id", personalityId)
        .single();
      if (p) {
        systemPrompt = p.system_prompt;
        temperature = Number(p.temperature);
      }
    }

    // Load recent history
    const { data: history } = await supabase
      .from("messages")
      .select("role, content")
      .eq("conversation_id", data.conversationId)
      .order("created_at", { ascending: true })
      .limit(40);

    // Persist user message
    await supabase.from("messages").insert({
      conversation_id: data.conversationId,
      user_id: userId,
      role: "user",
      content: data.message,
      char_count: data.message.length,
    });

    // Call Lovable AI Gateway
    const apiKey = process.env.LOVABLE_API_KEY;
    if (!apiKey) throw new Error("Missing LOVABLE_API_KEY");

    const messages = [
      { role: "system", content: systemPrompt },
      ...(history ?? []).map((h) => ({ role: h.role, content: h.content })),
      { role: "user", content: data.message },
    ];

    const aiResp = await fetch("https://ai.gateway.lovable.dev/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "google/gemini-3-flash-preview",
        messages,
        temperature,
      }),
    });

    if (!aiResp.ok) {
      const errText = await aiResp.text();
      if (aiResp.status === 429) throw new Error("Rate limit reached. Try again in a moment.");
      if (aiResp.status === 402) throw new Error("AI credits exhausted. Add credits in workspace settings.");
      throw new Error(`AI error: ${errText.slice(0, 200)}`);
    }

    const aiJson = (await aiResp.json()) as {
      choices: { message: { content: string } }[];
    };
    const reply = aiJson.choices?.[0]?.message?.content ?? "";

    // Persist assistant message
    const { data: saved } = await supabase
      .from("messages")
      .insert({
        conversation_id: data.conversationId,
        user_id: userId,
        role: "assistant",
        content: reply,
        char_count: reply.length,
      })
      .select("id, content, created_at, role")
      .single();

    // Log usage
    await supabase.from("usage_logs").insert({
      user_id: userId,
      conversation_id: data.conversationId,
      kind: "chat",
      characters: data.message.length + reply.length,
      audio_seconds: 0,
    });

    // Update conversation title if first exchange
    if ((history ?? []).length === 0) {
      const title = data.message.slice(0, 60);
      await supabase.from("conversations").update({ title }).eq("id", data.conversationId);
    }

    return { message: saved };
  });

/**
 * Create a new conversation.
 */
export const createConversation = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d: unknown) =>
    z.object({ personalityId: z.string().uuid().nullable().optional() }).parse(d),
  )
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;
    const { data: conv, error } = await supabase
      .from("conversations")
      .insert({ user_id: userId, personality_id: data.personalityId ?? null })
      .select("id")
      .single();
    if (error) throw error;
    return conv;
  });

/**
 * Log a TTS generation (characters → audio seconds estimate).
 * Called by the client after the audio finishes loading.
 */
export const logTtsUsage = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d: unknown) =>
    z
      .object({
        messageId: z.string().uuid().optional(),
        characters: z.number().int().min(0),
        audioSeconds: z.number().int().min(0),
      })
      .parse(d),
  )
  .handler(async ({ data, context }) => {
    const { supabase, userId } = context;
    await supabase.from("usage_logs").insert({
      user_id: userId,
      kind: "tts",
      characters: data.characters,
      audio_seconds: data.audioSeconds,
    });
    return { ok: true };
  });
