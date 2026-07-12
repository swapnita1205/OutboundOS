from pydantic import BaseModel, Field


class SellerProfile(BaseModel):
    """Describes the seller ('us') that ICP/persona scoring is evaluated against.

    Every field has a sensible default so existing callers keep working without
    changes, but a real deployment should override this via the seller profile
    config file (see `app/utils/seller_profile.py`) so ICP fit is scored against
    an actual target profile instead of a generic notion of "a good company."
    """

    company_name: str = "OutboundOS"
    product_description: str = (
        "An AI-native outbound sales platform that researches companies, scores ICP fit, "
        "identifies pain points, and drafts evidence-grounded personalized outreach "
        "automatically for sales and revenue teams."
    )
    value_propositions: list[str] = Field(
        default_factory=lambda: [
            "Cuts SDR research and drafting time from ~20 minutes to under a minute per account.",
            "Grounds every claim in live web evidence instead of generic templates.",
            "Adds a self-reviewing quality gate before any email goes out.",
        ]
    )
    target_industries: list[str] = Field(
        default_factory=lambda: [
            "B2B SaaS",
            "Sales technology",
            "Marketing technology",
            "Revenue operations tooling",
        ]
    )
    target_company_size: str = "50-2000 employees, Series A and later"
    target_geographies: list[str] = Field(default_factory=lambda: ["North America", "Europe"])
    ideal_tech_signals: list[str] = Field(
        default_factory=lambda: [
            "Uses a CRM (Salesforce, HubSpot, etc.)",
            "Has a dedicated outbound/SDR function",
            "Recent GTM or sales-team hiring activity",
        ]
    )
    target_buyer_titles: list[str] = Field(
        default_factory=lambda: [
            "VP Sales",
            "Head of Revenue Operations",
            "Chief Revenue Officer",
            "Sales Development Manager",
        ]
    )
    disqualifiers: list[str] = Field(
        default_factory=lambda: [
            "Pure consumer (B2C) company with no B2B sales motion",
            "No dedicated sales or GTM team",
        ]
    )
