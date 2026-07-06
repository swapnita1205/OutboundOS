import { useEffect, useMemo, useState } from "react"
import {
  Activity,
  CheckCircle2,
  Clock3,
  DollarSign,
  Moon,
  Sun,
  Workflow,
} from "lucide-react"

import { Badge } from "./components/ui/badge"
import { Button } from "./components/ui/button"
import { Card, CardContent, CardTitle } from "./components/ui/card"
import { Progress } from "./components/ui/progress"

const dashboardData = {
  lead: {
    company: "Acme AI",
    website: "acmeai.com",
    owner: "Ava Johnson",
    stage: "Qualified",
  },
  research: {
    industry: "SaaS",
    summary:
      "Acme AI is expanding enterprise automation offerings after launching a new AI copilot line.",
    painPoints: [
      "Manual outbound research slows SDR execution.",
      "Message quality varies across reps and channels.",
      "Pipeline consistency drops during product launch cycles.",
    ],
  },
  agentTrace: [
    "research: gathered company profile and market signals",
    "pain_points: ranked GTM bottlenecks with evidence",
    "persona: selected Head of AI as primary buyer",
    "messaging: generated outreach bundle under word limits",
    "review: requested rewrite for stronger personalization",
    "rewrite: regenerated copy with company-specific details",
    "review: approved all quality dimensions",
  ],
  email: {
    subject: "Acme AI: quick thought on outbound consistency",
    coldEmail:
      "Hi Ava, saw Acme AI's new copilot launch. Teams often face uneven outbound quality during moments like this. OutboundOS helps automate research and keep messaging natural across channels. Open to a quick 15-minute chat next week?",
    followUp1:
      "Quick follow-up in case this is relevant: we help teams remove manual prep from outreach while keeping personalization high.",
    followUp2:
      "Last note from me. If pipeline consistency is still a focus, I can share a short workflow tailored for your team.",
    linkedin:
      "Hi Ava, congrats on the launch at Acme AI. If outbound consistency is a focus, happy to share a short playbook.",
    cta: "Open to a 15-minute intro next week?",
  },
  review: {
    comments: [
      "Rewrite improved personalization by referencing launch context.",
      "Tone is consultative and avoids hard-sell language.",
      "No unsupported claims detected in final pass.",
    ],
    qualityScore: 92,
  },
  metrics: {
    iterations: 3,
    latencyMs: 4280,
    costUsd: 0.0264,
    tokenUsage: 10642,
  },
  finalApproval: true,
}

function App() {
  const [darkMode, setDarkMode] = useState(true)

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
  }, [darkMode])

  const latencySeconds = useMemo(
    () => (dashboardData.metrics.latencyMs / 1000).toFixed(2),
    [],
  )

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

        <section className="mb-6 grid gap-4 md:grid-cols-4">
          <MetricCard
            title="Iterations"
            value={dashboardData.metrics.iterations.toString()}
            icon={<Workflow className="h-4 w-4" />}
          />
          <MetricCard
            title="Latency"
            value={`${latencySeconds}s`}
            icon={<Clock3 className="h-4 w-4" />}
          />
          <MetricCard
            title="Cost"
            value={`$${dashboardData.metrics.costUsd.toFixed(4)}`}
            icon={<DollarSign className="h-4 w-4" />}
          />
          <MetricCard
            title="Final Approval"
            value={dashboardData.finalApproval ? "Approved" : "Pending"}
            icon={<CheckCircle2 className="h-4 w-4" />}
          />
        </section>

        <div className="grid gap-4 xl:grid-cols-3">
          <Card className="xl:col-span-1">
            <CardTitle>Lead</CardTitle>
            <CardContent className="space-y-2 text-sm">
              <p><span className="text-muted-foreground">Company:</span> {dashboardData.lead.company}</p>
              <p><span className="text-muted-foreground">Website:</span> {dashboardData.lead.website}</p>
              <p><span className="text-muted-foreground">Owner:</span> {dashboardData.lead.owner}</p>
              <div className="pt-1">
                <Badge>{dashboardData.lead.stage}</Badge>
              </div>
            </CardContent>
          </Card>

          <Card className="xl:col-span-2">
            <CardTitle>Research</CardTitle>
            <CardContent className="space-y-3 text-sm">
              <p className="text-muted-foreground">{dashboardData.research.industry}</p>
              <p>{dashboardData.research.summary}</p>
              <div className="space-y-2">
                {dashboardData.research.painPoints.map((point) => (
                  <div key={point} className="rounded-md bg-muted/60 px-3 py-2">
                    {point}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="xl:col-span-2">
            <CardTitle>Email</CardTitle>
            <CardContent className="space-y-3 text-sm">
              <div className="rounded-md bg-muted/60 p-3">
                <p className="text-xs uppercase text-muted-foreground">Subject</p>
                <p className="mt-1">{dashboardData.email.subject}</p>
              </div>
              <MessageBlock label="Cold Email" content={dashboardData.email.coldEmail} />
              <MessageBlock label="Follow-up #1" content={dashboardData.email.followUp1} />
              <MessageBlock label="Follow-up #2" content={dashboardData.email.followUp2} />
              <MessageBlock label="LinkedIn Message" content={dashboardData.email.linkedin} />
              <MessageBlock label="Call To Action" content={dashboardData.email.cta} />
            </CardContent>
          </Card>

          <Card className="xl:col-span-1">
            <CardTitle>Review Comments</CardTitle>
            <CardContent className="space-y-3 text-sm">
              <div className="rounded-md bg-muted/60 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-muted-foreground">Quality score</span>
                  <Badge variant="success">{dashboardData.review.qualityScore}%</Badge>
                </div>
                <Progress value={dashboardData.review.qualityScore} />
              </div>
              {dashboardData.review.comments.map((comment) => (
                <div key={comment} className="rounded-md border border-border/70 p-3">
                  {comment}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="xl:col-span-3">
            <CardTitle>Agent Trace</CardTitle>
            <CardContent className="grid gap-2">
              {dashboardData.agentTrace.map((step, idx) => (
                <div key={step} className="flex items-start gap-3 rounded-md border border-border/60 p-3">
                  <div className="mt-0.5 rounded-full bg-primary/15 p-1.5 text-primary">
                    <Activity className="h-3.5 w-3.5" />
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
      <p className="mt-1">{content}</p>
    </div>
  )
}

export default App
