import { useEffect, useMemo, useRef, useState } from "react"
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  DollarSign,
  Loader2,
  Moon,
  PlayCircle,
  Sun,
  Workflow,
} from "lucide-react"

import { Badge } from "./components/ui/badge"
import { Button } from "./components/ui/button"
import { Card, CardContent, CardTitle } from "./components/ui/card"
import { Progress } from "./components/ui/progress"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

interface CompanySummary {
  company: string
  industry: string
  description: string
  employees: string
  recent_news: string[]
  products: string[]
  customers: string[]
  funding: string
  tech_stack: string[]
  ai_signals: string[]
  evidence_urls: string[]
  evidence_snippets: string[]
}

interface ICPScore {
  score: number
  reasons: string[]
  ideal_persona: string
  risk_flags: string[]
  confidence: number
}

interface PainPoint {
  description: string
  evidence: string[]
  confidence: number
  recommended_messaging_angle: string
}

interface PersonaSelection {
  persona: string
  why: string[]
  confidence: number
}

interface MessageBundle {
  subject: string
  cold_email: string
  follow_up_1: string
  follow_up_2: string
  linkedin_message: string
  call_to_action: string
}

interface ReviewerScores {
  hallucinations: number
  generic_language: number
  grammar: number
  unsupported_claims: number
  email_length: number
  personalization: number
  tone: number
}

interface ReviewerCritique {
  scores: ReviewerScores
  average_score: number
  decision: string
  reasons: string[]
  action_items: string[]
}

interface Metrics {
  latencyMs: number
  costUsd: number
  tokens: number
  iterations: number
}

type RunStatus = "idle" | "running" | "done" | "error"

interface StreamEvent {
  type: "started" | "stage" | "final" | "error"
  stage?: string
  label?: string
  detail?: string
  company_name?: string
  message?: string
  final_decision?: string
  metrics?: { latency_ms?: number; cost_usd?: number; tokens?: number; iterations?: number }
  company_summary?: CompanySummary
  icp_score?: ICPScore
  pain_points?: { top_pain_points: PainPoint[] }
  persona_selection?: PersonaSelection
  message_bundle?: MessageBundle
  reviewer_critique?: ReviewerCritique
}

const EMPTY_METRICS: Metrics = { latencyMs: 0, costUsd: 0, tokens: 0, iterations: 0 }

function normalizeWebsite(input: string): string {
  const trimmed = input.trim()
  if (!trimmed) return trimmed
  return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
}

function App() {
  const [darkMode, setDarkMode] = useState(true)
  const [companyName, setCompanyName] = useState("Stripe")
  const [website, setWebsite] = useState("stripe.com")

  const [status, setStatus] = useState<RunStatus>("idle")
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [trace, setTrace] = useState<string[]>([])
  const [companySummary, setCompanySummary] = useState<CompanySummary | null>(null)
  const [icpScore, setIcpScore] = useState<ICPScore | null>(null)
  const [painPoints, setPainPoints] = useState<PainPoint[]>([])
  const [persona, setPersona] = useState<PersonaSelection | null>(null)
  const [messageBundle, setMessageBundle] = useState<MessageBundle | null>(null)
  const [reviewerCritique, setReviewerCritique] = useState<ReviewerCritique | null>(null)
  const [finalDecision, setFinalDecision] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<Metrics>(EMPTY_METRICS)

  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
  }, [darkMode])

  const latencySeconds = useMemo(() => (metrics.latencyMs / 1000).toFixed(1), [metrics.latencyMs])

  function resetRun() {
    setErrorMessage(null)
    setTrace([])
    setCompanySummary(null)
    setIcpScore(null)
    setPainPoints([])
    setPersona(null)
    setMessageBundle(null)
    setReviewerCritique(null)
    setFinalDecision(null)
    setMetrics(EMPTY_METRICS)
  }

  function applyEvent(evt: StreamEvent) {
    if (evt.metrics) {
      setMetrics((prev) => ({
        latencyMs: evt.metrics?.latency_ms ?? prev.latencyMs,
        costUsd: evt.metrics?.cost_usd ?? prev.costUsd,
        tokens: evt.metrics?.tokens ?? prev.tokens,
        iterations: evt.metrics?.iterations ?? prev.iterations,
      }))
    }

    if (evt.type === "started") {
      setTrace((prev) => [...prev, `Starting workflow for ${evt.company_name ?? "company"}...`])
      return
    }

    if (evt.type === "stage") {
      const detail = evt.detail
      if (detail) {
        const shortDetail = detail.split(": ").slice(1).join(": ") || detail
        setTrace((prev) => [...prev, `${evt.label ?? evt.stage}: ${shortDetail}`])
      }
      if (evt.company_summary) setCompanySummary(evt.company_summary)
      if (evt.icp_score) setIcpScore(evt.icp_score)
      if (evt.pain_points) setPainPoints(evt.pain_points.top_pain_points)
      if (evt.persona_selection) setPersona(evt.persona_selection)
      if (evt.message_bundle) setMessageBundle(evt.message_bundle)
      if (evt.reviewer_critique) setReviewerCritique(evt.reviewer_critique)
      return
    }

    if (evt.type === "final") {
      setFinalDecision(evt.final_decision ?? null)
      setStatus("done")
      return
    }

    if (evt.type === "error") {
      setErrorMessage(evt.message ?? "Workflow failed")
      setStatus("error")
    }
  }

  async function runWorkflow() {
    if (!companyName.trim() || !website.trim()) {
      setErrorMessage("Enter a company name and website first.")
      setStatus("error")
      return
    }

    resetRun()
    setStatus("running")

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch(`${API_BASE}/api/v1/ops/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          company_name: companyName.trim(),
          website: normalizeWebsite(website),
          max_iterations: 4,
        }),
      })

      if (!response.ok || !response.body) {
        throw new Error(`Backend returned ${response.status}. Is the API running at ${API_BASE}?`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split("\n\n")
        buffer = blocks.pop() ?? ""

        for (const block of blocks) {
          const dataLine = block.split("\n").find((line) => line.startsWith("data: "))
          if (!dataLine) continue
          try {
            const evt = JSON.parse(dataLine.slice("data: ".length)) as StreamEvent
            applyEvent(evt)
          } catch {
            // ignore malformed chunk boundaries
          }
        }
      }

      setStatus((prev) => (prev === "running" ? "done" : prev))
    } catch (err) {
      if (controller.signal.aborted) return
      setErrorMessage(err instanceof Error ? err.message : "Unknown error contacting the API")
      setStatus("error")
    }
  }

  const isRunning = status === "running"
  const stageLabel =
    status === "idle"
      ? "Not started"
      : status === "running"
        ? trace[trace.length - 1] ?? "Starting..."
        : status === "error"
          ? "Failed"
          : finalDecision ?? "Complete"

  return (
    <div className="min-h-screen bg-background">
      <div className="container py-8">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
              OutboundOS Dashboard
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              Multi-Agent GTM Control Center
            </h1>
          </div>
          <Button variant="ghost" onClick={() => setDarkMode((prev) => !prev)}>
            {darkMode ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}
            {darkMode ? "Light mode" : "Dark mode"}
          </Button>
        </header>

        <Card className="mb-6">
          <CardTitle>Run the live agent pipeline</CardTitle>
          <CardContent>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[180px] flex-1">
                <label className="text-xs text-muted-foreground">Company name</label>
                <input
                  className="mt-1 w-full rounded-md border border-border bg-muted/40 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/60"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Stripe"
                  disabled={isRunning}
                />
              </div>
              <div className="min-w-[180px] flex-1">
                <label className="text-xs text-muted-foreground">Website</label>
                <input
                  className="mt-1 w-full rounded-md border border-border bg-muted/40 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/60"
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  placeholder="stripe.com"
                  disabled={isRunning}
                />
              </div>
              <Button onClick={runWorkflow} disabled={isRunning} className="disabled:opacity-60">
                {isRunning ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <PlayCircle className="mr-2 h-4 w-4" />
                )}
                {isRunning ? "Running..." : "Run pipeline"}
              </Button>
              <Badge variant={status === "error" ? "destructive" : status === "done" ? "success" : "outline"}>
                {stageLabel}
              </Badge>
            </div>
            {status === "error" && errorMessage && (
              <div className="mt-3 flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                <AlertTriangle className="h-4 w-4" /> {errorMessage}
              </div>
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              This calls the real FastAPI backend ({API_BASE}) and runs the actual 6-agent
              LangGraph workflow with live web research. A full run takes roughly 30-60 seconds.
            </p>
          </CardContent>
        </Card>

        <section className="mb-6 grid gap-4 md:grid-cols-4">
          <MetricCard
            title="Iterations"
            value={metrics.iterations ? metrics.iterations.toString() : "—"}
            icon={<Workflow className="h-4 w-4" />}
          />
          <MetricCard
            title="Latency"
            value={metrics.latencyMs ? `${latencySeconds}s` : "—"}
            icon={<Clock3 className="h-4 w-4" />}
          />
          <MetricCard
            title="Cost"
            value={metrics.costUsd ? `$${metrics.costUsd.toFixed(4)}` : "—"}
            icon={<DollarSign className="h-4 w-4" />}
          />
          <MetricCard
            title="Final Decision"
            value={finalDecision ?? "—"}
            icon={<CheckCircle2 className="h-4 w-4" />}
          />
        </section>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-1">
            <CardTitle>Lead</CardTitle>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="text-muted-foreground">Company:</span>{" "}
                {companySummary?.company ?? companyName ?? "—"}
              </p>
              <p>
                <span className="text-muted-foreground">Website:</span> {website || "—"}
              </p>
              <p>
                <span className="text-muted-foreground">Industry:</span>{" "}
                {companySummary?.industry ?? "—"}
              </p>
              <div className="pt-1">
                <Badge variant={status === "done" ? "success" : "outline"}>
                  {status === "idle" ? "Not started" : status}
                </Badge>
              </div>
            </CardContent>
          </Card>

          <Card className="xl:col-span-2">
            <CardTitle>Research</CardTitle>
            <CardContent className="space-y-3 text-sm">
              {companySummary ? (
                <>
                  <p>{companySummary.description}</p>
                  {companySummary.recent_news.length > 0 && (
                    <div className="space-y-2">
                      {companySummary.recent_news.slice(0, 3).map((news) => (
                        <div key={news} className="rounded-md bg-muted/60 px-3 py-2">
                          {news}
                        </div>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Grounded in {companySummary.evidence_urls.length} live sources (Firecrawl +
                    Tavily).
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">Run the pipeline to see live research.</p>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-1">
            <CardTitle>ICP Fit</CardTitle>
            <CardContent className="space-y-3 text-sm">
              {icpScore ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Score</span>
                    <Badge variant="success">{Math.round(icpScore.score)}/100</Badge>
                  </div>
                  <Progress value={icpScore.score} />
                  <p className="text-muted-foreground">{icpScore.ideal_persona}</p>
                </>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-1">
            <CardTitle>Persona</CardTitle>
            <CardContent className="space-y-2 text-sm">
              {persona ? (
                <>
                  <Badge>{persona.persona}</Badge>
                  <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
                    {persona.why.slice(0, 2).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-1">
            <CardTitle>Pain Points</CardTitle>
            <CardContent className="space-y-2 text-sm">
              {painPoints.length > 0 ? (
                painPoints.slice(0, 3).map((point) => (
                  <div key={point.description} className="rounded-md bg-muted/60 px-3 py-2">
                    {point.description}
                  </div>
                ))
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-2">
            <CardTitle>Email</CardTitle>
            <CardContent className="space-y-3 text-sm">
              {messageBundle ? (
                <>
                  <div className="rounded-md bg-muted/60 p-3">
                    <p className="text-xs uppercase text-muted-foreground">Subject</p>
                    <p className="mt-1">{messageBundle.subject}</p>
                  </div>
                  <MessageBlock label="Cold Email" content={messageBundle.cold_email} />
                  <MessageBlock label="Follow-up #1" content={messageBundle.follow_up_1} />
                  <MessageBlock label="Follow-up #2" content={messageBundle.follow_up_2} />
                  <MessageBlock label="LinkedIn Message" content={messageBundle.linkedin_message} />
                  <MessageBlock label="Call To Action" content={messageBundle.call_to_action} />
                </>
              ) : (
                <p className="text-muted-foreground">Run the pipeline to generate outreach.</p>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-1">
            <CardTitle>Review</CardTitle>
            <CardContent className="space-y-3 text-sm">
              {reviewerCritique ? (
                <>
                  <div className="rounded-md bg-muted/60 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-muted-foreground">Quality score</span>
                      <Badge variant={reviewerCritique.decision === "APPROVE" ? "success" : "warning"}>
                        {Math.round(reviewerCritique.average_score * 100)}%
                      </Badge>
                    </div>
                    <Progress value={reviewerCritique.average_score * 100} />
                  </div>
                  <Badge variant="outline">{reviewerCritique.decision}</Badge>
                  {reviewerCritique.reasons.slice(0, 3).map((reason) => (
                    <div key={reason} className="rounded-md border border-border/70 p-3">
                      {reason}
                    </div>
                  ))}
                </>
              ) : (
                <p className="text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>

          <Card className="xl:col-span-3">
            <CardTitle>Agent Trace (live)</CardTitle>
            <CardContent className="grid gap-2">
              {trace.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No run yet. Enter a company above and click "Run pipeline" to watch the six
                  agents work in real time.
                </p>
              )}
              {trace.map((step, idx) => (
                <div
                  key={`${idx}-${step}`}
                  className="flex items-start gap-3 rounded-md border border-border/60 p-3"
                >
                  <div className="mt-0.5 rounded-full bg-primary/15 p-1.5 text-primary">
                    {isRunning && idx === trace.length - 1 ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Activity className="h-3.5 w-3.5" />
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Step {idx + 1}</p>
                    <p className="text-sm">{step}</p>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function MetricCard({
  title,
  value,
  icon,
}: {
  title: string
  value: string
  icon: React.ReactNode
}) {
  return (
    <Card>
      <CardTitle className="flex items-center justify-between text-xs">
        <span>{title}</span>
        <span className="rounded-md bg-muted p-1 text-muted-foreground">{icon}</span>
      </CardTitle>
      <CardContent>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
      </CardContent>
    </Card>
  )
}

function MessageBlock({ label, content }: { label: string; content: string }) {
  return (
    <div className="rounded-md border border-border/70 p-3">
      <p className="text-xs uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 whitespace-pre-wrap">{content}</p>
    </div>
  )
}

export default App
