import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { supabase } from "@/integrations/supabase/client";
import { verifyCryptoPayment, CREDIT_PACKS, TRON_USDT } from "@/lib/voxa.functions";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/app/billing")({
  component: BillingPage,
});

function BillingPage() {
  const { data } = useQuery({
    queryKey: ["billing"],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return null;
      const [{ data: sub }, { data: usage }, { data: plans }] = await Promise.all([
        supabase
          .from("subscriptions")
          .select("plan_id, status, current_period_end, plans:plans(name, price_monthly, char_quota, audio_seconds_quota, features)")
          .eq("user_id", user.id)
          .maybeSingle(),
        supabase.from("v_current_usage").select("*").eq("user_id", user.id).maybeSingle(),
        supabase.from("plans").select("*").order("display_order"),
      ]);
      return {
        sub,
        chars: Number(usage?.characters_used ?? 0),
        seconds: Number(usage?.audio_seconds_used ?? 0),
        plans: plans ?? [],
      };
    },
  });

  const { data: credits } = useQuery({
    queryKey: ["credits"],
    queryFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return 0;
      const { data: row } = await supabase
        .from("credits")
        .select("balance")
        .eq("user_id", user.id)
        .maybeSingle();
      return Number(row?.balance ?? 0);
    },
  });

  const plan = data?.sub?.plans;
  const charPct = plan ? (data!.chars / plan.char_quota) * 100 : 0;
  const audioPct = plan ? (data!.seconds / plan.audio_seconds_quota) * 100 : 0;

  const upgrade = async (planId: string) => {
    // Stripe placeholder — switch plan immediately for now
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;
    const { error } = await supabase
      .from("subscriptions")
      .update({ plan_id: planId, current_period_start: new Date().toISOString(), current_period_end: new Date(Date.now() + 30 * 86400000).toISOString() })
      .eq("user_id", user.id);
    if (error) return toast.error(error.message);
    toast.success("Plan updated. Stripe checkout coming soon.");
    location.reload();
  };

  return (
    <div className="p-6 lg:p-10 max-w-6xl">
      <header className="mb-10">
        <div className="font-mono-label text-muted-foreground">BILLING</div>
        <h1 className="font-display text-6xl mt-2 leading-none">
          Plan & usage.
        </h1>
      </header>

      {/* Current plan oversize card */}
      <section className="hairline bg-ink text-paper border border-ink p-8 lg:p-12 mb-12">
        <div className="grid grid-cols-12 gap-6 items-end">
          <div className="col-span-12 md:col-span-6">
            <div className="font-mono-label text-paper/50">CURRENT PLAN</div>
            <div className="font-display text-7xl mt-2">{plan?.name ?? "—"}</div>
            <div className="font-mono-label text-paper/60 mt-2">
              ${plan?.price_monthly}/MO · RENEWS {data?.sub?.current_period_end ? new Date(data.sub.current_period_end).toLocaleDateString() : "—"}
            </div>
          </div>
          <div className="col-span-12 md:col-span-6 space-y-6">
            <Meter label="CHARACTERS" used={data?.chars ?? 0} total={plan?.char_quota ?? 0} pct={charPct} accent="bg-paper" />
            <Meter label="AUDIO SECONDS" used={data?.seconds ?? 0} total={plan?.audio_seconds_quota ?? 0} pct={audioPct} accent="bg-accent" />
          </div>
        </div>
      </section>

      {/* Credits — crypto top-up */}
      <CryptoCredits balance={credits ?? 0} />

      {/* Plan comparison */}
      <section>
        <div className="font-mono-label text-muted-foreground mb-4">CHANGE PLAN</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {data?.plans?.map((p) => {
            const current = p.id === data.sub?.plan_id;
            return (
              <div key={p.id} className={`hairline border border-ink/15 p-6 flex flex-col ${current ? "bg-ink text-paper border-ink" : ""}`}>
                <div className="font-mono-label">{p.name.toUpperCase()}</div>
                <div className="font-display text-5xl mt-3">${p.price_monthly}<span className="font-mono-label">/MO</span></div>
                <div className="mt-4 font-display">
                  <div>{p.char_quota.toLocaleString()} chars</div>
                  <div className="italic">{Math.round(p.audio_seconds_quota / 60)} min audio</div>
                </div>
                <ul className="mt-4 space-y-1 text-sm flex-1">
                  {(p.features as string[]).map((f: string) => (
                    <li key={f}>— {f}</li>
                  ))}
                </ul>
                <button
                  disabled={current}
                  onClick={() => upgrade(p.id)}
                  className={`hairline mt-6 px-4 py-2.5 font-mono-label border ${
                    current
                      ? "border-paper/40 text-paper/40"
                      : "border-ink bg-ink text-paper hover:bg-accent hover:text-ink"
                  }`}
                >
                  {current ? "CURRENT" : "SWITCH →"}
                </button>
              </div>
            );
          })}
        </div>
        <div className="font-mono-label text-muted-foreground mt-6">
          NOTE: STRIPE CHECKOUT INTEGRATION COMING SOON. CURRENTLY SWITCHES PLAN IMMEDIATELY (DEMO).
        </div>
      </section>

      {/* Invoice history placeholder */}
      <section className="mt-16">
        <div className="font-mono-label text-muted-foreground mb-4">INVOICE HISTORY</div>
        <div className="hairline border border-ink/15 divide-y divide-ink/10">
          <div className="px-5 py-8 text-center text-muted-foreground font-mono-label">
            NO INVOICES YET — STRIPE WILL POPULATE THIS WHEN ENABLED
          </div>
        </div>
      </section>
    </div>
  );
}

function CryptoCredits({ balance }: { balance: number }) {
  const qc = useQueryClient();
  const verifyFn = useServerFn(verifyCryptoPayment);
  const [packIdx, setPackIdx] = useState(0);
  const [txHash, setTxHash] = useState("");
  const pack = CREDIT_PACKS[packIdx];

  const copyAddress = async () => {
    try {
      await navigator.clipboard.writeText(TRON_USDT.depositAddress);
      toast.success("Address copied");
    } catch {
      toast.error("Couldn't copy address");
    }
  };

  const verifyMut = useMutation({
    mutationFn: async () => {
      return verifyFn({ data: { packId: pack.id, txHash: txHash.trim() } });
    },
    onSuccess: (res) => {
      toast.success(`Verified — +${res.credits.toLocaleString()} credits added`);
      qc.setQueryData(["credits"], res.balance);
      qc.invalidateQueries({ queryKey: ["credits"] });
      setTxHash("");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Verification failed"),
  });

  const hashLooksValid = /^[0-9a-fA-F]{64}$/.test(txHash.trim());

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between mb-4">
        <div className="font-mono-label text-muted-foreground">CREDITS · PAY WITH USDT (TRON)</div>
        <div className="font-mono-label text-muted-foreground">
          BALANCE / <span className="text-ink">{balance.toLocaleString()}</span>
        </div>
      </div>

      <div className="hairline border border-ink/15 grid grid-cols-1 lg:grid-cols-2">
        {/* Pack selection */}
        <div className="p-6 lg:p-8 lg:border-r border-ink/15">
          <div className="font-mono-label text-muted-foreground mb-3">1 · CHOOSE A PACK</div>
          <div className="space-y-2">
            {CREDIT_PACKS.map((p, i) => {
              const active = i === packIdx;
              return (
                <button
                  key={p.id}
                  onClick={() => setPackIdx(i)}
                  className={`hairline w-full border p-4 flex items-baseline justify-between transition ${
                    active ? "border-ink bg-ink text-paper" : "border-ink/15 hover:border-ink"
                  }`}
                >
                  <span className="font-display text-2xl">
                    {p.credits.toLocaleString()} <span className="font-mono-label">CREDITS</span>
                  </span>
                  <span className="text-right">
                    <span className="font-display text-xl">{p.usdt} USDT</span>
                    {"bonus" in p && p.bonus && (
                      <span className={`font-mono-label block ${active ? "text-accent" : "text-muted-foreground"}`}>
                        {p.bonus}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Pay + verify */}
        <div className="p-6 lg:p-8 bg-ink/[0.03]">
          <div className="font-mono-label text-muted-foreground mb-2">
            2 · SEND EXACTLY {pack.usdt} USDT (TRC-20) TO
          </div>
          <div className="hairline border border-ink/20 bg-paper p-4 break-all font-mono text-sm">
            {TRON_USDT.depositAddress}
          </div>
          <div className="flex items-center justify-between mt-2">
            <button onClick={copyAddress} className="font-mono-label text-muted-foreground hover:text-ink">
              Copy address →
            </button>
            <span className="font-mono-label text-muted-foreground">NETWORK / {TRON_USDT.network.toUpperCase()}</span>
          </div>

          <div className="font-mono-label text-muted-foreground mt-6 mb-2">3 · PASTE THE TRANSACTION HASH</div>
          <input
            value={txHash}
            onChange={(e) => setTxHash(e.target.value)}
            placeholder="64-character Tron tx hash"
            spellCheck={false}
            className="hairline w-full border border-ink/25 bg-paper px-3 py-2.5 outline-none focus:border-ink font-mono text-sm break-all"
          />

          <button
            onClick={() => verifyMut.mutate()}
            disabled={verifyMut.isPending || !hashLooksValid}
            className="hairline mt-3 w-full border border-ink bg-ink px-4 py-3 text-paper font-mono-label hover:bg-accent hover:text-ink disabled:opacity-40"
          >
            {verifyMut.isPending ? "Verifying on-chain…" : `Verify & claim ${pack.credits.toLocaleString()} credits →`}
          </button>

          <div className="font-mono-label text-muted-foreground mt-3 leading-relaxed">
            PAYMENT IS VERIFIED ON THE TRON BLOCKCHAIN. CREDITS ARE GRANTED ONLY AFTER THE
            TRANSFER IS CONFIRMED (~1 MIN) AND CAN BE CLAIMED ONCE PER TRANSACTION.
          </div>
        </div>
      </div>
    </section>
  );
}

function Meter({ label, used, total, pct, accent }: { label: string; used: number; total: number; pct: number; accent: string }) {
  return (
    <div>
      <div className="flex justify-between font-mono-label text-paper/60">
        <span>{label}</span>
        <span>{used.toLocaleString()} / {total.toLocaleString()}</span>
      </div>
      <div className="hairline mt-2 h-2 bg-paper/10">
        <div className={`h-full ${accent}`} style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
    </div>
  );
}
