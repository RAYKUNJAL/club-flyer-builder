import os

DATABASE_URL = os.environ.get("SBI_DATABASE_URL", "sqlite:///./skin_blend_iq.db")
JWT_SECRET = os.environ.get("SBI_JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("SBI_JWT_EXPIRE_MINUTES", "480"))
UPLOAD_DIR = os.environ.get("SBI_UPLOAD_DIR", "./uploads")
FRONTEND_DIST = os.environ.get("SBI_FRONTEND_DIST", "../frontend/dist")
