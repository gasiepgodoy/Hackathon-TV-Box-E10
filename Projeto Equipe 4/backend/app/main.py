import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import database, influx_writer
from .adapters.manager import gerenciador_adapters
from .config import settings
from .routers import data, sensors, ws, analytics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando gateway IoT...")
    database.iniciar_banco()
    influx_writer.conectar()
    await gerenciador_adapters.iniciar_todos_ativos()
    logger.info("Gateway pronto.")
    yield
    logger.info("Encerrando gateway...")
    await gerenciador_adapters.parar_todos()
    influx_writer.desconectar()


app = FastAPI(title="Gateway IoT Universal", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router)
app.include_router(data.router)
app.include_router(analytics.router)
app.include_router(ws.router)


@app.get("/api/saude")
def saude():
    return {"status": "ok"}
