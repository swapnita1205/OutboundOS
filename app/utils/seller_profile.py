import json
import logging
from functools import lru_cache
from pathlib import Path

from app.schemas.seller_profile import SellerProfile
from app.utils.settings import get_settings

logger = logging.getLogger("outboundos.utils.seller_profile")


@lru_cache(maxsize=1)
def get_seller_profile() -> SellerProfile:
    """Load the configured seller ('us') profile that ICP/persona scoring runs against.

    Falls back to `SellerProfile()`'s built-in defaults (which describe OutboundOS
    itself) if no config file is set or it can't be found/parsed, so the system
    always has *some* concrete seller context instead of scoring against nothing.
    """
    settings = get_settings()
    if not settings.seller_profile_path:
        return SellerProfile()

    path = Path(settings.seller_profile_path)
    if not path.exists():
        logger.warning("seller_profile_not_found | %s", {"path": str(path)})
        return SellerProfile()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SellerProfile(**data)
    except Exception:  # noqa: BLE001
        logger.exception("seller_profile_load_failed | %s", {"path": str(path)})
        return SellerProfile()
