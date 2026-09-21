import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


# On Lambda each invocation may run in a fresh container; keep no idle connections and let the
# Supabase pooler (Supavisor) manage pooling instead.
if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    engine = create_engine(settings.database_url, poolclass=NullPool)
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
