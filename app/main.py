from fastapi import FastAPI

from app.routers import router

app = FastAPI(
    title="Approval Service",
    description="Content approval workflow service (publications, scenarios, edits, external items).",
    version="0.1.0",
)

app.include_router(router)


@app.get("/healthz", tags=["health"])
def healthz():
    return {"status": "ok"}