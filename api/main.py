from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.tasks import router as tasks_router
from api.routes.ws import router as ws_router

app = FastAPI(title="OpenClaw Orchestrator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
