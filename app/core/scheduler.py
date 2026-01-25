from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from app.core.config import settings
import logging
import uuid
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


async def auto_enrich_contact_job(contact_id: uuid.UUID):
    """
    Background job to auto-enrich a newly created contact.
    Runs 5 seconds after contact creation.
    """
    from app.db.session import AsyncSessionLocal
    from app.services.osint_service import OSINTService

    logger.info(f"Auto-enrichment job started for contact {contact_id}")

    try:
        async with AsyncSessionLocal() as session:
            osint_service = OSINTService(session)
            result = await osint_service.enrich_contact(contact_id)
            logger.info(f"Auto-enrichment result for {contact_id}: {result['status']}")
    except Exception as e:
        logger.exception(f"Auto-enrichment failed for {contact_id}: {e}")

# Configure Redis Job Store
redis_url_str = str(settings.REDIS_URL)
parsed_redis = urlparse(redis_url_str)

# Parse Redis URL components manually to pass as kwargs to RedisJobStore
# RedisJobStore initiates Redis(db=..., **kwargs)
# We need to extract: host, port, password, db
redis_kwargs = {
    'host': parsed_redis.hostname or 'localhost',
    'port': parsed_redis.port or 6379,
    'password': parsed_redis.password,
}

# DB is typically path '/0' -> 0
db_val = 0
if parsed_redis.path and parsed_redis.path != '/':
    try:
        db_val = int(parsed_redis.path.lstrip('/'))
    except ValueError:
        pass

jobstores = {
    'default': RedisJobStore(
        jobs_key='network_bot:jobs',
        run_times_key='network_bot:run_times',
        db=db_val,
        **redis_kwargs
    )
}

scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")

async def start_scheduler():
    """Start the scheduler."""
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")

async def shutdown_scheduler():
    """Shutdown the scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shut down.")
