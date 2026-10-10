import logging
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.config import load_settings
from app.db.session import session_factory
from app.logging_config import configure_logging
from app.services.admin_seed import AdminSeedError, seed_admin

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    settings = load_settings()
    if not settings.admin_email or not settings.admin_password:
        logger.error("ADMIN_EMAIL and ADMIN_PASSWORD are required")
        return 1
    session = session_factory()()
    try:
        seed_admin(session, settings.admin_email, settings.admin_password)
    except AdminSeedError as exc:
        logger.error("%s", exc)
        return 1
    except SQLAlchemyError:
        logger.error("Could not seed admin. Run alembic upgrade head first.")
        return 1
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
