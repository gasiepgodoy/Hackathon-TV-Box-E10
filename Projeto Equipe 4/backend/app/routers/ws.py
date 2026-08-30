from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..ws_manager import gerenciador_ws

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await gerenciador_ws.conectar(ws)
    try:
        while True:
            # não esperamos mensagens do cliente, só mantemos a conexão viva
            await ws.receive_text()
    except WebSocketDisconnect:
        gerenciador_ws.desconectar(ws)
