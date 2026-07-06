import logging

from app.dataset.schemas import EnrichmentBundle, SeedCompany
from app.tools.company_evidence import collect_company_evidence
from app.utils.settings import Settings

logger = logging.getLogger("outboundos.dataset.enrichers")


async def enrich_company(seed: SeedCompany, settings: Settings) -> EnrichmentBundle:
    bundle = await collect_company_evidence(seed.company_name, seed.website, settings)
    return EnrichmentBundle(
        company_name=bundle.company_name,
        website=bundle.website,
        homepage_scraped=bundle.homepage_scraped,
        evidence=bundle.evidence,
        scrape_errors=bundle.scrape_errors,
    )
