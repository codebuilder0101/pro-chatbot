import { createServerFn } from "@tanstack/react-start";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { z } from "zod";

/**
 * Crypto top-up config — USDT on Tron (TRC-20). Shared deposit address; payments
 * are verified by transaction hash on-chain. Amounts are fixed in USDT.
 */
export const CREDIT_PACKS = [
  { id: "p1", credits: 1000, usdt: 10 },
  { id: "p2", credits: 5500, usdt: 50, bonus: "+10% bonus" },
  { id: "p3", credits: 12000, usdt: 100, bonus: "+20% bonus" },
] as const;

export const TRON_USDT = {
  network: "Tron (TRC-20)",
  contract: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", // USDT TRC-20 mainnet contract
  // TODO: replace with YOUR real Tron USDT receiving address before going live.
  // Verification only credits payments sent to THIS address.
  depositAddress: "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb",
};

const TRON_API = "https://api.trongrid.io";
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

// Tron base58 address → 20-byte hex (matches the hex `to`/`from` in TronGrid events).
function tronToHex20(addr: string): string {
  let num = 0n;
  for (const c of addr) {
    const i = B58.indexOf(c);
    if (i < 0) throw new Error("Invalid Tron address");
    num = num * 58n + BigInt(i);
  }
  let hex = num.toString(16);
  if (hex.length % 2) hex = "0" + hex;
  if (hex.length < 50) hex = hex.padStart(50, "0");
  return hex.slice(2, 42).toLowerCase();
}

function evmHex20(addr: string | undefined): string {
  if (!addr) return "";
  return addr.replace(/^0x/, "").toLowerCase().padStart(40, "0").slice(-40);
}

function tronHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const key = process.env.TRONGRID_API_KEY;
  if (key) h["TRON-PRO-API-KEY"] = key;
  return h;
}

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
  .validator((d: unknown) => ChatInput.parse(d))
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

    // Call OpenAI Chat Completions
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) throw new Error("Missing OPENAI_API_KEY");
    const model = process.env.OPENAI_MODEL || "gpt-4o-mini";

    const messages = [
      { role: "system", content: systemPrompt },
      ...(history ?? []).map((h) => ({ role: h.role, content: h.content })),
      { role: "user", content: data.message },
    ];

    const aiResp = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages,
        temperature,
      }),
    });

    if (!aiResp.ok) {
      const errText = await aiResp.text();
      if (aiResp.status === 429) throw new Error("Rate limit reached. Try again in a moment.");
      if (aiResp.status === 401) throw new Error("OpenAI rejected the API key. Check OPENAI_API_KEY.");
      if (aiResp.status === 402) throw new Error("OpenAI quota exhausted. Check your billing.");
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
  .validator((d: unknown) =>
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
  .validator((d: unknown) =>
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

/**
 * Verify a USDT (TRC-20) payment by transaction hash and grant credits.
 *
 * Verification (all must pass, server-side only):
 *   1. The tx contains a USDT Transfer to our deposit address.
 *   2. The transferred amount is >= the pack's fixed USDT price.
 *   3. The tx is finalized (present on Tron's solidified node).
 *   4. The tx hash has not already been redeemed (DB unique constraint).
 * Crediting runs via the service role so a client can never mint credits directly.
 */
export const verifyCryptoPayment = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .validator((d: unknown) =>
    z
      .object({
        packId: z.string(),
        txHash: z
          .string()
          .trim()
          .regex(/^[0-9a-fA-F]{64}$/, "Enter the 64-character Tron transaction hash."),
      })
      .parse(d),
  )
  .handler(async ({ data, context }) => {
    const { userId } = context;

    const pack = CREDIT_PACKS.find((p) => p.id === data.packId);
    if (!pack) throw new Error("Unknown credit pack.");

    const txHash = data.txHash.toLowerCase();
    const depositHex = tronToHex20(TRON_USDT.depositAddress);
    const expectedUnits = BigInt(pack.usdt) * 1_000_000n; // USDT has 6 decimals

    // 1. Read the decoded transfer events for this transaction.
    const evResp = await fetch(`${TRON_API}/v1/transactions/${txHash}/events`, {
      headers: tronHeaders(),
    });
    if (!evResp.ok) throw new Error(`Tron API error (${evResp.status}). Try again shortly.`);
    const evJson = (await evResp.json()) as {
      data?: Array<{
        event_name?: string;
        contract_address?: string;
        result?: { from?: string; to?: string; value?: string };
      }>;
    };
    const transfers = (evJson.data ?? []).filter(
      (e) => e.event_name === "Transfer" && e.contract_address === TRON_USDT.contract,
    );
    if (transfers.length === 0) {
      throw new Error("No USDT (TRC-20) transfer was found in that transaction.");
    }

    const match = transfers.find((t) => evmHex20(t.result?.to) === depositHex);
    if (!match) {
      throw new Error("That transaction did not send USDT to the VOXA deposit address.");
    }

    const value = BigInt(match.result?.value ?? "0");
    if (value < expectedUnits) {
      const sent = (Number(value) / 1_000_000).toString();
      throw new Error(`Underpaid: this pack needs ${pack.usdt} USDT but only ${sent} USDT was sent.`);
    }

    // 2. Require finalization: the solidified node only returns irreversible txs.
    const infoResp = await fetch(`${TRON_API}/walletsolidity/gettransactioninfobyid`, {
      method: "POST",
      headers: tronHeaders(),
      body: JSON.stringify({ value: txHash }),
    });
    const info = (await infoResp.json()) as { id?: string; receipt?: { result?: string } };
    if (!info || !info.id) {
      throw new Error("Payment isn't confirmed yet. Tron finalizes in about a minute — wait and retry.");
    }
    if (info.receipt?.result && info.receipt.result !== "SUCCESS") {
      throw new Error("That on-chain transaction failed.");
    }

    // 3. Credit atomically via service role; unique tx_hash prevents double-spend.
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { data: balance, error } = await supabaseAdmin.rpc("redeem_crypto_payment", {
      _user_id: userId,
      _credits: pack.credits,
      _amount_usd: pack.usdt,
      _asset: "USDT",
      _network: TRON_USDT.network,
      _tx_hash: txHash,
      _from_address: match.result?.from ?? "",
      _amount_crypto: Number(value) / 1_000_000,
    });
    if (error) {
      if (/already_redeemed|duplicate|unique/i.test(error.message)) {
        throw new Error("This transaction has already been used to buy credits.");
      }
      throw new Error(error.message);
    }

    return { balance: balance as number, credits: pack.credits };
  });
