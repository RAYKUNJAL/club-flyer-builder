from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .db import Base, SessionLocal, engine
from .routers import (
    auth_router,
    captures_router,
    clients_router,
    formulas_router,
    misc_router,
    pigments_router,
    sessions_router,
)


def create_app(seed_demo: bool = True) -> FastAPI:
    app = FastAPI(
        title="Skin Blend IQ",
        version="1.0.0",
        description=(
            "Professional decision-support platform for paramedical tattoo "
            "practitioners. Not a medical device; it does not diagnose and "
            "does not guarantee healed color."
        ),
    )
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        from .seed import seed

        seed(db, demo=seed_demo)

    app.include_router(auth_router.router)
    app.include_router(clients_router.router)
    app.include_router(captures_router.router)
    app.include_router(pigments_router.router)
    app.include_router(formulas_router.router)
    app.include_router(sessions_router.router)
    app.include_router(misc_router.router)

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "service": "skin-blend-iq"}

    dist = os.path.abspath(config.FRONTEND_DIST)
    if os.path.isdir(dist):
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
