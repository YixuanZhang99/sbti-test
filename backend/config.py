import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///test.db")

# Render provides postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

# Cache TTL in seconds
STATS_CACHE_TTL = 60

# Batch write threshold for page_views
PAGEVIEW_BATCH_SIZE = 100
