import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "VOXA — Conversations that sound human" },
      {
        name: "description",
        content:
          "VOXA is the voice-first AI platform for teams who care how their product sounds. Build bots with a personality, not a script.",
      },
      { property: "og:title", content: "VOXA — Conversations that sound human" },
      {
        property: "og:description",
        content: "Voice-first AI agents with editorial-grade craft.",
      },
    ],
  }),
  component: Landing,
});

function Landing() {
  return (
    <div className="min-h-screen bg-paper text-ink font-sans selection:bg-accent">
      <Nav />
      <Hero />
      <Marquee />
      <DemoSection />
      <FeatureSplit />
      <Pricing />
      <Footer />
    </div>
  );
}

/* --------------------------------- NAV ---------------------------------- */

function Nav() {
  return (
    <header className="hairline-b sticky top-0 z-50 bg-paper/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-4 lg:px-10">
        <a href="/" className="flex items-baseline gap-2">
          <span className="font-display text-2xl font-medium tracking-tight">VOXA</span>
          <span className="font-mono-label text-muted-foreground">[001]</span>
        </a>
        <nav className="hidden items-center gap-10 md:flex">
          {["Product", "Voices", "Pricing", "Docs"].map((l) => (
            <a key={l} href={`#${l.toLowerCase()}`} className="font-mono-label hover:text-ink/60">
              {l}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <a href="/auth" className="font-mono-label hidden px-3 py-2 hover:underline md:inline">
            Sign in
          </a>
          <a
            href="/auth"
            className="hairline group relative inline-flex items-center gap-2 border border-ink bg-ink px-4 py-2.5 text-paper transition-colors hover:bg-accent hover:text-ink"
          >
            <span className="font-mono-label">Start building</span>
            <span aria-hidden>→</span>
          </a>
        </div>
      </div>
    </header>
  );
}

/* --------------------------------- HERO --------------------------------- */

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid max-w-[1400px] grid-cols-12 gap-6 px-6 pb-20 pt-16 lg:px-10 lg:pb-32 lg:pt-24">
        {/* Left metadata column */}
        <div className="col-span-12 lg:col-span-2">
          <div className="hairline-t flex justify-between pt-3 lg:flex-col lg:gap-6 lg:border-0 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0" style={{ borderColor: "var(--hairline)" }}>
            <div>
              <div className="font-mono-label text-muted-foreground">[ V.01 ]</div>
              <div className="font-mono-label mt-1">VOICE.AGENT</div>
            </div>
            <div>
              <div className="font-mono-label text-muted-foreground">EST.</div>
              <div className="font-mono-label mt-1">MMXXVI</div>
            </div>
          </div>
        </div>

        {/* Headline */}
        <div className="col-span-12 lg:col-span-10">
          <h1 className="font-display text-[clamp(3rem,9vw,9.5rem)] font-normal leading-[0.9] tracking-tight">
            Conversations <br />
            <span className="italic text-ink/90">that sound</span> <Glyph /> <br />
            <span className="relative inline-block">
              human.
              <span className="absolute -right-3 top-2 hidden h-3 w-3 rounded-full bg-accent md:block" />
            </span>
          </h1>

          <div className="mt-12 grid grid-cols-12 gap-6">
            <p className="col-span-12 max-w-xl text-lg leading-relaxed text-ink/70 md:col-span-7">
              VOXA is the voice-first AI platform for teams who care how their product sounds. Compose
              agents with personality, voice, and taste — then deploy them anywhere a customer might
              listen.
            </p>
            <div className="col-span-12 flex flex-col gap-3 md:col-span-5 md:items-end">
              <a
                href="#demo"
                className="hairline group inline-flex items-center gap-3 border border-ink bg-ink px-5 py-3 text-paper transition hover:bg-accent hover:text-ink"
              >
                <span className="font-mono-label">Hear it speak</span>
                <PlayIcon />
              </a>
              <a href="#pricing" className="font-mono-label text-muted-foreground hover:text-ink">
                or view pricing →
              </a>
            </div>
          </div>

          {/* Live waveform */}
          <div className="hairline-t mt-16 pt-8">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono-label text-muted-foreground">LIVE.WAVEFORM / NOW</span>
              <span className="font-mono-label text-muted-foreground">128 kbps · 24 kHz</span>
            </div>
            <Waveform />
          </div>
        </div>
      </div>
    </section>
  );
}

function Glyph() {
  return (
    <span className="inline-block translate-y-2 align-middle">
      <svg width="0.85em" height="0.85em" viewBox="0 0 80 80" className="inline">
        <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="2" />
        <circle cx="40" cy="40" r="10" fill="var(--acid)" />
      </svg>
    </span>
  );
}

function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
      <path d="M2 1.5v11l10-5.5z" />
    </svg>
  );
}

/* ------------------------------- WAVEFORM ------------------------------- */

function Waveform({ bars = 96 }: { bars?: number }) {
  return (
    <div className="flex h-24 items-center gap-[3px]">
      {Array.from({ length: bars }).map((_, i) => {
        const delay = (i % 12) * 0.07;
        const height = 20 + ((i * 37) % 80);
        return (
          <span
            key={i}
            className="wave-bar inline-block w-[3px] rounded-full bg-ink"
            style={{
              height: `${height}%`,
              animationDelay: `${delay}s`,
              animationDuration: `${0.9 + ((i * 13) % 10) / 20}s`,
            }}
          />
        );
      })}
    </div>
  );
}

/* -------------------------------- MARQUEE ------------------------------- */

function Marquee() {
  const items = [
    "Real-time TTS",
    "★",
    "12 languages",
    "★",
    "ElevenLabs voices",
    "★",
    "GPT-class reasoning",
    "★",
    "Streaming audio",
    "★",
    "Custom personas",
    "★",
    "Zero-latency interrupts",
    "★",
  ];
  return (
    <div className="hairline-y border-y border-ink/15 overflow-hidden bg-ink text-paper">
      <div className="flex whitespace-nowrap py-4 marquee-track">
        {[...items, ...items, ...items].map((t, i) => (
          <span key={i} className="font-display mx-6 text-2xl italic">
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

/* --------------------------------- DEMO --------------------------------- */

const VOICES = [
  { id: "callum", name: "Callum", tone: "Warm · British · Editorial" },
  { id: "sarah", name: "Sarah", tone: "Clear · Neutral · Narrator" },
  { id: "river", name: "River", tone: "Soft · Androgynous · Late-night" },
  { id: "brian", name: "Brian", tone: "Gravel · American · Deep" },
];

function DemoSection() {
  const [active, setActive] = useState(VOICES[0].id);
  const [playing, setPlaying] = useState(false);

  // Fake playback toggle
  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => setPlaying(false), 3500);
    return () => clearTimeout(t);
  }, [playing]);

  return (
    <section id="demo" className="mx-auto max-w-[1400px] px-6 py-24 lg:px-10 lg:py-32">
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-4">
          <div className="font-mono-label text-muted-foreground">[ 002 ] / DEMO</div>
          <h2 className="font-display mt-4 text-5xl leading-[0.95] lg:text-6xl">
            Pick a voice. <br />
            <em>Hear the room change.</em>
          </h2>
          <p className="mt-6 max-w-sm text-ink/70">
            Each voice is tuned for emotion, pacing, and breath. Click one and listen — these are the
            same voices powering your agents.
          </p>
        </div>

        <div className="col-span-12 lg:col-span-8">
          <div className="hairline border border-ink/15 bg-paper">
            <div className="hairline-b flex items-center justify-between px-6 py-4">
              <span className="font-mono-label">VOXA / PLAYER</span>
              <span className="font-mono-label text-muted-foreground">
                {playing ? "● TRANSMITTING" : "○ READY"}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2">
              <ul className="hairline-b md:hairline-b-0 md:hairline-r divide-y divide-ink/10">
                {VOICES.map((v, i) => (
                  <li key={v.id}>
                    <button
                      onClick={() => {
                        setActive(v.id);
                        setPlaying(true);
                      }}
                      className={`flex w-full items-center justify-between px-6 py-5 text-left transition ${
                        active === v.id ? "bg-ink text-paper" : "hover:bg-ink/5"
                      }`}
                    >
                      <div>
                        <div className="font-display text-2xl">
                          {String(i + 1).padStart(2, "0")} — {v.name}
                        </div>
                        <div
                          className={`font-mono-label mt-1 ${
                            active === v.id ? "text-paper/60" : "text-muted-foreground"
                          }`}
                        >
                          {v.tone}
                        </div>
                      </div>
                      <span className="font-mono-label">{active === v.id ? "▶ PLAY" : "○"}</span>
                    </button>
                  </li>
                ))}
              </ul>

              <div className="flex flex-col justify-between p-6">
                <div>
                  <div className="font-mono-label text-muted-foreground">NOW SPEAKING</div>
                  <div className="font-display mt-2 text-3xl italic">
                    "{VOICES.find((v) => v.id === active)?.name} reads the news at midnight."
                  </div>
                </div>
                <div className="mt-8">
                  <Waveform bars={42} />
                  <div className="font-mono-label mt-3 flex justify-between text-muted-foreground">
                    <span>00:00</span>
                    <span>00:08</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Logo strip */}
          <div className="hairline-t mt-10 pt-6">
            <div className="font-mono-label mb-4 text-muted-foreground">TRUSTED BY EDITORIAL TEAMS</div>
            <div className="flex flex-wrap items-center gap-x-10 gap-y-4 text-ink/40">
              {["KINFOLK", "MONOCLE", "ARC*", "FRAMA", "AESOP", "STÜSSY"].map((n) => (
                <span key={n} className="font-display text-2xl tracking-tight">
                  {n}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ----------------------------- FEATURE SPLIT ---------------------------- */

const FEATURES = [
  {
    num: "01",
    label: "PERSONAS",
    title: "Agents with a point of view.",
    body: "Compose system prompts, voice, temperature, and silence behavior. Save them as personas you can deploy in seconds.",
  },
  {
    num: "02",
    label: "REAL-TIME",
    title: "Streaming, end to end.",
    body: "Audio streams as the model thinks. Latency under 400ms, with interruption that feels like an actual conversation.",
  },
  {
    num: "03",
    label: "OBSERVABILITY",
    title: "Every breath, accounted for.",
    body: "Per-message logs of characters and audio seconds. Set caps, alerts, and per-team budgets without leaving the dashboard.",
  },
];

function FeatureSplit() {
  return (
    <section id="product" className="hairline-y border-y border-ink/15 bg-ink text-paper">
      <div className="mx-auto max-w-[1400px] px-6 py-24 lg:px-10 lg:py-32">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-5">
            <div className="font-mono-label text-paper/50">[ 003 ] / SYSTEM</div>
            <h2 className="font-display mt-4 text-6xl leading-[0.95] lg:text-7xl">
              Built for teams who <em>refuse</em> to sound like everyone else.
            </h2>
          </div>
          <div className="col-span-12 lg:col-span-7 lg:pl-12">
            <ul className="divide-y divide-paper/15">
              {FEATURES.map((f) => (
                <li key={f.num} className="grid grid-cols-12 gap-4 py-10 first:pt-0">
                  <div className="col-span-2 font-display text-5xl text-paper/40">{f.num}</div>
                  <div className="col-span-10">
                    <div className="font-mono-label text-accent">{f.label}</div>
                    <h3 className="font-display mt-2 text-3xl">{f.title}</h3>
                    <p className="mt-3 max-w-md text-paper/70">{f.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------- PRICING ------------------------------- */

const TIERS = [
  {
    name: "Starter",
    price: "19",
    tag: "For tinkerers",
    chars: "250K characters",
    minutes: "60 audio minutes",
    perks: ["3 personas", "8 voices", "Community support"],
  },
  {
    name: "Pro",
    price: "89",
    tag: "Most chosen",
    chars: "2M characters",
    minutes: "500 audio minutes",
    perks: ["Unlimited personas", "All voices", "Priority routing", "Email support"],
    feature: true,
  },
  {
    name: "Studio",
    price: "299",
    tag: "For agencies",
    chars: "10M characters",
    minutes: "3,000 audio minutes",
    perks: ["Custom voice cloning", "Team seats", "SSO", "Dedicated channel"],
  },
];

function Pricing() {
  return (
    <section id="pricing" className="mx-auto max-w-[1400px] px-6 py-24 lg:px-10 lg:py-32">
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 mb-12 flex items-end justify-between lg:col-span-12">
          <div>
            <div className="font-mono-label text-muted-foreground">[ 004 ] / PRICING</div>
            <h2 className="font-display mt-4 text-6xl leading-[0.95] lg:text-7xl">
              Three tiers. <em>No surprises.</em>
            </h2>
          </div>
          <div className="font-mono-label hidden text-muted-foreground md:block">
            Billed monthly · cancel anytime
          </div>
        </div>

        {TIERS.map((t) => (
          <article
            key={t.name}
            className={`col-span-12 flex flex-col md:col-span-4 ${
              t.feature ? "bg-ink text-paper" : "bg-paper"
            } hairline border border-ink/15`}
          >
            <div className="hairline-b flex items-center justify-between px-6 py-4">
              <span className="font-mono-label">{t.name.toUpperCase()}</span>
              <span
                className={`font-mono-label ${
                  t.feature ? "text-accent" : "text-muted-foreground"
                }`}
              >
                {t.tag}
              </span>
            </div>
            <div className="px-6 py-8">
              <div className="flex items-baseline gap-1">
                <span className="font-display text-7xl">${t.price}</span>
                <span className="font-mono-label">/MO</span>
              </div>
              <div className={`mt-6 space-y-1 ${t.feature ? "text-paper/80" : "text-ink/80"}`}>
                <div className="font-display text-xl">{t.chars}</div>
                <div className="font-display text-xl italic">{t.minutes}</div>
              </div>
              <ul className="mt-8 space-y-2">
                {t.perks.map((p) => (
                  <li key={p} className="flex items-start gap-3 text-sm">
                    <span className={t.feature ? "text-accent" : "text-ink"}>—</span>
                    <span className={t.feature ? "text-paper/80" : "text-ink/80"}>{p}</span>
                  </li>
                ))}
              </ul>
            </div>
            <a
              href="/auth"
              className={`hairline-t mt-auto flex items-center justify-between px-6 py-4 transition ${
                t.feature
                  ? "bg-accent text-ink hover:bg-paper"
                  : "bg-paper hover:bg-ink hover:text-paper"
              }`}
            >
              <span className="font-mono-label">Choose {t.name}</span>
              <span>→</span>
            </a>
          </article>
        ))}
      </div>
    </section>
  );
}

/* --------------------------------- FOOTER -------------------------------- */

function Footer() {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <footer className="hairline-t border-t border-ink/15">
      <div className="mx-auto max-w-[1400px] px-6 py-20 lg:px-10">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 md:col-span-6">
            <div className="font-display text-[clamp(3rem,7vw,7rem)] leading-[0.9]">
              Hear the <br /> <em>difference.</em>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (ref.current) ref.current.value = "";
              }}
              className="hairline mt-10 flex max-w-md items-center border border-ink/30"
            >
              <input
                ref={ref}
                type="email"
                placeholder="you@studio.com"
                className="flex-1 bg-transparent px-4 py-3 outline-none placeholder:text-ink/40"
              />
              <button
                type="submit"
                className="font-mono-label bg-ink px-5 py-3 text-paper transition hover:bg-accent hover:text-ink"
              >
                Subscribe
              </button>
            </form>
            <p className="font-mono-label mt-3 text-muted-foreground">
              One letter per month. Voice samples included.
            </p>
          </div>

          <div className="col-span-12 grid grid-cols-3 gap-6 md:col-span-6">
            {[
              { h: "PRODUCT", l: ["Chat", "Voices", "Dashboard", "API"] },
              { h: "COMPANY", l: ["About", "Manifesto", "Careers", "Press"] },
              { h: "LEGAL", l: ["Privacy", "Terms", "DPA", "Status"] },
            ].map((c) => (
              <div key={c.h}>
                <div className="font-mono-label text-muted-foreground">{c.h}</div>
                <ul className="mt-4 space-y-2">
                  {c.l.map((x) => (
                    <li key={x}>
                      <a href="#" className="hover:text-ink/60">
                        {x}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="hairline-t mt-16 flex flex-wrap items-end justify-between gap-4 pt-6">
          <div className="font-display text-[clamp(6rem,18vw,18rem)] leading-[0.8]">VOXA</div>
          <div className="font-mono-label space-y-1 text-right text-muted-foreground">
            <div>© MMXXVI VOXA STUDIOS</div>
            <div>BERLIN · TOKYO · NEW YORK</div>
            <div>V.01.0 — BUILD 0001</div>
          </div>
        </div>
      </div>
    </footer>
  );
}
