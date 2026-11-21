"""Salida de posiciones: JSONL a archivo y WebSocket para el front (capa aumentada / panel).

Cada mensaje es un frame:
  {"t": 12.34, "frame": 370, "runners": [{"id": 3, "s": 105.2, "d": 0.41, "lane": 1, ...}]}
"""
from __future__ import annotations

import asyncio
import json
import threading


class JsonlWriter:
    def __init__(self, path: str):
        self.f = open(path, "w")

    def send(self, msg: dict):
        self.f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def close(self):
        self.f.close()


class WebSocketBroadcaster:
    """Servidor WebSocket en un hilo propio; send() es seguro desde el hilo del video."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        import websockets  # dependencia opcional

        self._clients: set = set()
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()

        async def handler(ws):
            self._clients.add(ws)
            try:
                await ws.wait_closed()
            finally:
                self._clients.discard(ws)

        async def main():
            async with websockets.serve(handler, host, port):
                self._ready.set()
                await asyncio.Future()

        threading.Thread(target=lambda: self._loop.run_until_complete(main()), daemon=True).start()
        self._ready.wait(5)
        print(f"[ws] transmitiendo posiciones en ws://{host}:{port}")

    def send(self, msg: dict):
        if not self._clients:
            return
        data = json.dumps(msg, ensure_ascii=False)

        async def _bcast():
            for ws in list(self._clients):
                try:
                    await ws.send(data)
                except Exception:
                    self._clients.discard(ws)

        asyncio.run_coroutine_threadsafe(_bcast(), self._loop)

    def close(self):
        self._loop.call_soon_threadsafe(self._loop.stop)
