import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

export const Route = createFileRoute("/auth")({
  head: () => ({
    meta: [
      { title: "Sign in — VOXA" },
      { name: "description", content: "Sign in to your VOXA workspace." },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) navigate({ to: "/app" });
    });
  }, [navigate]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const fn =
        mode === "signin"
          ? supabase.auth.signInWithPassword({ email, password })
          : supabase.auth.signUp({
              email,
              password,
              options: { emailRedirectTo: window.location.origin + "/app" },
            });
      const { error } = await fn;
      if (error) throw error;
      toast.success(mode === "signin" ? "Welcome back." : "Account created.");
      navigate({ to: "/app" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-paper grid lg:grid-cols-2">
      {/* Left editorial panel */}
      <div className="hidden lg:flex relative flex-col justify-between bg-ink p-10 text-paper">
        <Link to="/" className="font-display text-3xl">VOXA</Link>
        <div>
          <div className="font-mono-label text-paper/50">[ 001 ] / ACCESS</div>
          <h1 className="font-display mt-4 text-7xl leading-[0.9]">
            Step <em>inside</em><br /> the studio.
          </h1>
          <p className="mt-6 max-w-md text-paper/70">
            Compose voice agents that sound less like software and more like the people you'd hire.
          </p>
        </div>
        <div className="font-mono-label text-paper/40">© MMXXVI · BERLIN · TOKYO · NEW YORK</div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-sm">
          <Link to="/" className="lg:hidden font-display text-2xl">VOXA</Link>
          <div className="font-mono-label mt-8 text-muted-foreground">
            [ {mode === "signin" ? "01" : "02"} ] / {mode === "signin" ? "SIGN IN" : "CREATE ACCOUNT"}
          </div>
          <h2 className="font-display mt-3 text-4xl">
            {mode === "signin" ? "Welcome back." : <>Make something <em>good.</em></>}
          </h2>

          <form onSubmit={onSubmit} className="mt-8 space-y-3">
            <div>
              <label className="font-mono-label text-muted-foreground">EMAIL</label>
              <input
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="hairline mt-1 w-full border border-ink/25 bg-transparent px-3 py-2.5 outline-none focus:border-ink"
              />
            </div>
            <div>
              <label className="font-mono-label text-muted-foreground">PASSWORD</label>
              <input
                type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
                className="hairline mt-1 w-full border border-ink/25 bg-transparent px-3 py-2.5 outline-none focus:border-ink"
              />
            </div>
            <button
              type="submit" disabled={busy}
              className="hairline mt-2 flex w-full items-center justify-between border border-ink bg-ink px-4 py-3 text-paper transition hover:bg-accent hover:text-ink disabled:opacity-50"
            >
              <span className="font-mono-label">
                {busy ? "Working..." : mode === "signin" ? "Sign in" : "Create account"}
              </span>
              <span>→</span>
            </button>
          </form>

          <button
            onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
            className="font-mono-label mt-6 text-muted-foreground hover:text-ink"
          >
            {mode === "signin"
              ? "Need an account? Create one →"
              : "Already a member? Sign in →"}
          </button>
        </div>
      </div>
    </div>
  );
}
