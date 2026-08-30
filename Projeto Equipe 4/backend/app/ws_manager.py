"""
Gerencia as conexões WebSocket ativas e faz o broadcast de novas leituras
para todos os clientes conectados (o dashboard no navegador).
"""
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class WebSocketManager:
    def __init__(self) -> None:
        self._conexoes: set[WebSocket] = set()

    async def conectar(self, ws: WebSocket) -> None:
        await ws.accept()
        self._conexoes.add(ws)
        logger.info("Cliente WS conectado (%d ativos)", len(self._conexoes))

    def desconectar(self, ws: WebSocket) -> None:
        self._conexoes.discard(ws)
        logger.info("Cliente WS desconectado (%d ativos)", len(self._conexoes))

    async def broadcast(self, mensagem: dict) -> None:
        if not self._conexoes:
            return
        payload = json.dumps(mensagem, ensure_ascii=False)
        mortas = []
        for ws in self._conexoes:
            try:
                await ws.send_text(payload)
            except Exception:
                mortas.append(ws)
        for ws in mortas:
            self._conexoes.discard(ws)


gerenciador_ws = WebSocketManager()
