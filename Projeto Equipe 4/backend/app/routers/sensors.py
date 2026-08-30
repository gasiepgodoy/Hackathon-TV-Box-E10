from fastapi import APIRouter, HTTPException

from .. import database
from ..adapters.manager import gerenciador_adapters
from ..models import Sensor, SensorCreate, SensorUpdate

router = APIRouter(prefix="/api/sensores", tags=["sensores"])


@router.get("", response_model=list[Sensor])
def listar():
    return database.listar_sensores()


@router.get("/{sensor_id}", response_model=Sensor)
def obter(sensor_id: str):
    sensor = database.obter_sensor(sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor não encontrado")
    return sensor


@router.post("", response_model=Sensor, status_code=201)
async def criar(dados: SensorCreate):
    sensor = database.criar_sensor(dados)
    if sensor.ativo:
        await gerenciador_adapters.iniciar_sensor(sensor)
        sensor = database.obter_sensor(sensor.id)
    return sensor


@router.put("/{sensor_id}", response_model=Sensor)
async def atualizar(sensor_id: str, dados: SensorUpdate):
    sensor = database.atualizar_sensor(sensor_id, dados)
    if not sensor:
        raise HTTPException(404, "Sensor não encontrado")
    # reinicia o adapter pra aplicar a config nova
    await gerenciador_adapters.parar_sensor(sensor_id)
    if sensor.ativo:
        await gerenciador_adapters.iniciar_sensor(sensor)
    return database.obter_sensor(sensor_id)


@router.post("/{sensor_id}/alternar", response_model=Sensor)
async def alternar_ativo(sensor_id: str):
    sensor = database.obter_sensor(sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor não encontrado")
    novo_estado = not sensor.ativo
    sensor = database.atualizar_sensor(sensor_id, SensorUpdate(ativo=novo_estado))
    if novo_estado:
        await gerenciador_adapters.iniciar_sensor(sensor)
    else:
        await gerenciador_adapters.parar_sensor(sensor_id)
    return database.obter_sensor(sensor_id)


@router.delete("/{sensor_id}", status_code=204)
async def remover(sensor_id: str):
    await gerenciador_adapters.parar_sensor(sensor_id)
    ok = database.remover_sensor(sensor_id)
    if not ok:
        raise HTTPException(404, "Sensor não encontrado")
