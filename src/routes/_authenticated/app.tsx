import { createFileRoute, Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/app")({
  component: AppShell,
});

type NavItem = { to: string; label: string; adminOnly?: boolean };
const NAV: NavItem[] = [
  { to: "/app", label: "Chat" },
  { to: "/app/settings", label: "Settings" },
  { to: "/app/billing", label: "Billing" },
  { to: "/app/admin", label: "Admin", adminOnly: true },
];

function AppShell() {
  const navigate = useNavigate();
  const currentPath = useRouterState({ select: (s) => s.location.pathname });
  const [userId, setUserId] = useState<string | null>(null);
  const [email, setEmail] = useState<string>("");

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUserId(data.user?.id ?? null);
      setEmail(data.user?.email ?? "");
    });
  }, []);

  const { data: isAdmin } = useQuery({
    queryKey: ["isAdmin", userId],
    enabled: !!userId,
    queryFn: async () => {
      const { data } = await supabase
        .from("user_roles")
        .select("role")
        .eq("user_id", userId!)
        .eq("role", "admin")
        .maybeSingle();
      return !!data;
    },
  });

  const { data: usage } = useQuery({
    queryKey: ["usage", userId],
    enabled: !!userId,
    queryFn: async () => {
      const [{ data: sub }, { data: u }] = await Promise.all([
        supabase
          .from("subscriptions")
          .select("plan_id, plans:plans(name, char_quota, audio_seconds_quota)")
          .eq("user_id", userId!)
          .maybeSingle(),
        supabase.from("v_current_usage").select("*").eq("user_id", userId!).maybeSingle(),
      ]);
      return {
        plan: sub?.plans,
        planId: sub?.plan_id,
        chars: Number(u?.characters_used ?? 0),
        seconds: Number(u?.audio_seconds_used ?? 0),
      };
    },
    refetchInterval: 30000,
  });

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    toast.success("Signed out");
    navigate({ to: "/auth", replace: true });
  };

  const charPct = usage?.plan ? Math.min(100, (usage.chars / usage.plan.char_quota) * 100) : 0;
  const audioPct = usage?.plan ? Math.min(100, (usage.seconds / usage.plan.audio_seconds_quota) * 100) : 0;

  return (
    <div className="min-h-screen bg-paper text-ink flex">
      {/* Sidebar */}
      <aside className="hairline-r border-r border-ink/15 w-60 shrink-0 hidden md:flex flex-col">
        <div className="hairline-b border-b border-ink/15 p-5">
          <Link to="/" className="font-display text-2xl tracking-tight">VOXA</Link>
          <div className="font-mono-label text-muted-foreground mt-1">STUDIO / V.01</div>
        </div>

        <nav className="flex-1 p-3 space-y-0.5">
          {NAV.filter((n) => !n.adminOnly || isAdmin).map((n) => {
            const active = currentPath === n.to || (n.to !== "/app" && currentPath.startsWith(n.to));
            return (
              <Link
                key={n.to}
                to={n.to as "/app"}
                className={`flex items-center px-3 py-2 transition ${
                  active ? "bg-ink text-paper" : "hover:bg-ink/5"
                }`}
              >
                <span className="font-mono-label">{n.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Usage meters */}
        <div className="hairline-t border-t border-ink/15 p-4 space-y-3">
          <div>
            <div className="flex justify-between font-mono-label text-muted-foreground">
              <span>CHARS</span>
              <span>{Math.round(charPct)}%</span>
            </div>
            <div className="hairline mt-1 h-1 bg-ink/10">
              <div className="h-full bg-ink" style={{ width: `${charPct}%` }} />
            </div>
          </div>
          <div>
            <div className="flex justify-between font-mono-label text-muted-foreground">
              <span>AUDIO</span>
              <span>{Math.round(audioPct)}%</span>
            </div>
            <div className="hairline mt-1 h-1 bg-ink/10">
              <div className="h-full bg-accent" style={{ width: `${audioPct}%` }} />
            </div>
          </div>
          {usage?.plan && (
            <div className="font-mono-label text-muted-foreground pt-1">
              PLAN / {String(usage.plan.name).toUpperCase()}
            </div>
          )}
        </div>

        <div className="hairline-t border-t border-ink/15 p-4">
          <div className="text-xs truncate">{email}</div>
          <button
            onClick={handleSignOut}
            className="font-mono-label mt-2 text-muted-foreground hover:text-ink"
          >
            Sign out →
          </button>
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
