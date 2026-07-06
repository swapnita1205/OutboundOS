import random

from app.evaluation.models import EvaluationSample, GroundTruth

INDUSTRIES = ["saas", "fintech", "healthcare", "ecommerce", "logistics"]
PERSONAS = [
    "Founder",
    "CEO",
    "CTO",
    "VP Engineering",
    "Head of AI",
    "VP Sales",
    "RevOps",
    "Product",
]
PAIN_POOL = [
    "manual lead research causes slow outreach",
    "inconsistent outbound quality across reps",
    "personalization does not scale reliably",
    "pipeline volatility during launches",
    "limited GTM visibility across channels",
    "high prep time for account-level context",
]


def generate_dataset(size: int = 100, seed: int = 42) -> list[EvaluationSample]:
    rng = random.Random(seed)
    samples: list[EvaluationSample] = []

    for index in range(size):
        company_name = f"Company{index + 1:03d}"
        industry = rng.choice(INDUSTRIES)
        persona = _persona_for_industry(industry, rng)
        pains = rng.sample(PAIN_POOL, k=3)
        reference = (
            f"Hi team at {company_name}, saw your momentum in {industry}. "
            f"If {pains[0]} is a priority, OutboundOS can help your {persona} org."
        )
        website = f"https://{company_name.lower()}.example.com"
        sample = EvaluationSample(
            company_name=company_name,
            website=website,
            hiring_trends=[f"Hiring for {industry} growth", "Scaling outbound operations"],
            ground_truth=GroundTruth(
                industry=industry,
                persona=persona,
                pain_points=pains,
                reference_outreach=reference,
                icp_target=_icp_target(industry, persona),
            ),
        )
        samples.append(sample)
    return samples


def _persona_for_industry(industry: str, rng: random.Random) -> str:
    if industry in {"saas", "fintech"}:
        return rng.choice(["CTO", "VP Engineering", "Head of AI"])
    if industry == "healthcare":
        return rng.choice(["CEO", "Founder", "Product"])
    return rng.choice(PERSONAS)


def _icp_target(industry: str, persona: str) -> float:
    base = 65.0
    if industry in {"saas", "fintech"}:
        base += 12.0
    if persona in {"Head of AI", "VP Engineering", "CTO"}:
        base += 10.0
    return min(100.0, base)
