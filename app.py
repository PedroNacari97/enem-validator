from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from browser import startup_event, shutdown_event
from routes import router

app = FastAPI(title="Servidor ENEM - Verificação via INEP", version="2.7")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)
