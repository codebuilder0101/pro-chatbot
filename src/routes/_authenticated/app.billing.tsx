import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
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
