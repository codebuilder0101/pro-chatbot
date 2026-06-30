import { createFileRoute, redirect } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";

export const Route = createFileRoute("/_authenticated/app/admin")({
  beforeLoad: async () => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) throw redirect({ to: "/auth" });
    const { data: role } = await supabase
      .from("user_roles")
      .select("role")
      .eq("user_id", user.id)
      .eq("role", "admin")
      .maybeSingle();
    if (!role) throw redirect({ to: "/app" });
  },
  component: AdminPage,
});

function AdminPage() {
  const { data: stats } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: async () => {
      const [users, convs, msgs, usage] = await Promise.all([
        supabase.from("profiles").select("id", { count: "exact", head: true }),
        supabase.from("conversations").select("id", { count: "exact", head: true }),
        supabase.from("messages").select("id", { count: "exact", head: true }),
        supabase.from("usage_logs").select("characters, audio_seconds"),
      ]);
      const totalChars = (usage.data ?? []).reduce((s, r) => s + (r.characters ?? 0), 0);
      const totalAudio = (usage.data ?? []).reduce((s, r) => s + (r.audio_seconds ?? 0), 0);
      return {
        users: users.count ?? 0,
        convs: convs.count ?? 0,
        msgs: msgs.count ?? 0,
        chars: totalChars,
        audio: totalAudio,
      };
    },
  });

  const { data: recentUsers } = useQuery({
    queryKey: ["admin-users"],
    queryFn: async () => {
      const { data } = await supabase
        .from("profiles")
        .select("id, display_name, created_at, subscriptions:subscriptions(plan_id)")
        .order("created_at", { ascending: false })
        .limit(20);
      return data ?? [];
    },
  });

  const { data: activity } = useQuery({
    queryKey: ["admin-activity"],
    queryFn: async () => {
      const { data } = await supabase
        .from("usage_logs")
        .select("id, kind, characters, audio_seconds, created_at, user_id")
        .order("created_at", { ascending: false })
        .limit(20);
      return data ?? [];
    },
  });

  return (
    <div className="p-6 lg:p-10 max-w-6xl">
      <header className="mb-10">
        <div className="font-mono-label text-muted-foreground">[ 099 ] / ADMIN.CONSOLE</div>
        <h1 className="font-display text-6xl mt-2 leading-none">
          Operations.
        </h1>
      </header>

      {/* Stat grid */}
      <section className="grid grid-cols-2 lg:grid-cols-5 gap-px bg-ink/15 hairline border border-ink/15 mb-12">
        <Stat label="USERS" value={stats?.users ?? 0} />
        <Stat label="CONVERSATIONS" value={stats?.convs ?? 0} />
        <Stat label="MESSAGES" value={stats?.msgs ?? 0} />
        <Stat label="CHARACTERS" value={stats?.chars ?? 0} />
        <Stat label="AUDIO SECONDS" value={stats?.audio ?? 0} />
      </section>

      {/* Users table */}
      <section className="mb-12">
        <div className="font-mono-label text-muted-foreground mb-3">RECENT USERS</div>
        <div className="hairline border border-ink/15">
          <table className="w-full">
            <thead>
              <tr className="hairline-b border-b border-ink/15">
                <Th>USER</Th>
                <Th>ID</Th>
                <Th>PLAN</Th>
                <Th>JOINED</Th>
              </tr>
            </thead>
            <tbody>
              {recentUsers?.map((u) => (
                <tr key={u.id} className="hairline-b border-b border-ink/10 last:border-0">
                  <Td><span className="font-display">{u.display_name ?? "—"}</span></Td>
                  <Td><span className="font-mono text-xs text-muted-foreground">{u.id.slice(0, 8)}</span></Td>
                  <Td><span className="font-mono-label">{(((u.subscriptions as unknown as { plan_id: string }[])?.[0]?.plan_id) ?? "—").toUpperCase()}</span></Td>
                  <Td><span className="font-mono text-xs text-muted-foreground">{new Date(u.created_at).toLocaleString()}</span></Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Activity log */}
      <section>
        <div className="font-mono-label text-muted-foreground mb-3">ACTIVITY LOG</div>
        <div className="hairline border border-ink/15 divide-y divide-ink/10">
          {activity?.map((a) => (
            <div key={a.id} className="px-4 py-3 flex items-center justify-between text-sm">
              <div className="flex items-center gap-4">
                <span className="font-mono-label text-muted-foreground">
                  {new Date(a.created_at).toISOString().replace("T", " ").slice(0, 19)}
                </span>
                <span className={`font-mono-label px-2 py-0.5 ${a.kind === "tts" ? "bg-accent text-ink" : "bg-ink text-paper"}`}>
                  {a.kind.toUpperCase()}
                </span>
                <span className="font-mono text-xs text-muted-foreground">{a.user_id.slice(0, 8)}</span>
              </div>
              <span className="font-mono-label">
                {a.characters > 0 && <>{a.characters} CHARS </>}
                {a.audio_seconds > 0 && <>· {a.audio_seconds}s AUDIO</>}
              </span>
            </div>
          ))}
          {!activity?.length && (
            <div className="px-4 py-12 text-center font-mono-label text-muted-foreground">
              NO ACTIVITY YET
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-paper p-5">
      <div className="font-mono-label text-muted-foreground">{label}</div>
      <div className="font-display text-4xl lg:text-5xl mt-2 leading-none">
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="text-left px-4 py-3 font-mono-label text-muted-foreground">{children}</th>;
}
function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-4 py-3">{children}</td>;
}
