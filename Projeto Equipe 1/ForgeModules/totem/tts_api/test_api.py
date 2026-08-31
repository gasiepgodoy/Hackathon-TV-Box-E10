"""
test_api.py — Testes de latência e qualidade da TTS API local
Executa contra http://localhost:8000 (inicie com: uvicorn main:app --reload)
"""
import asyncio
import json
import os
import statistics
import time

import httpx

BASE_URL = "http://localhost:8000"
OUT_DIR = os.path.join(os.path.dirname(__file__), "tts_api_outputs")
os.makedirs(OUT_DIR, exist_ok=True)

TEXTOS = [
    "Olá! Eu sou sua assistente virtual. Como posso te ajudar hoje?",
    "A previsão do tempo para amanhã é de sol com algumas nuvens.",
    "Seu pedido foi confirmado e será entregue em até dois dias úteis.",
    "Atenção: reunião de equipe às quatorze horas na sala de conferências.",
    "Parabéns! Você completou todas as suas metas do dia. Continue assim!",
]

REPORT: list[dict] = []


def print_sep(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print(f"{'='*60}")


async def test_health(client: httpx.AsyncClient):
    print_sep("1. Health Check")
    r = await client.get("/health")
    assert r.status_code == 200, f"Health falhou: {r.text}"
    data = r.json()
    print(f"  Status   : {data['status']}")
    print(f"  Voz padrão: {data['default_voice']}")
    print(f"  Cache    : {data['cache_entries']} entradas")
    return data


async def test_voices(client: httpx.AsyncClient):
    print_sep("2. Vozes pt-BR disponíveis")
    r = await client.get("/voices", params={"locale": "pt-BR"})
    assert r.status_code == 200, f"Vozes falhou: {r.text}"
    voices = r.json()
    print(f"  Total de vozes pt-BR: {len(voices)}")
    for v in voices[:8]:
        print(f"  [{v['gender']:<6}] {v['name']:<35} {v['friendly_name']}")
    return voices


async def test_synthesize_latency(client: httpx.AsyncClient):
    print_sep("3. Latência de síntese (5 textos × 2 passadas)")

    latencies_cold: list[float] = []
    latencies_warm: list[float] = []

    for i, texto in enumerate(TEXTOS):
        # 1ª passada — cold (sem cache)
        t0 = time.perf_counter()
        r = await client.post("/synthesize", json={"text": texto})
        dt_cold = time.perf_counter() - t0
        assert r.status_code == 200, f"Síntese falhou: {r.text}"
        audio_cold = r.content

        # 2ª passada — warm (cache hit)
        t0 = time.perf_counter()
        r2 = await client.post("/synthesize", json={"text": texto})
        dt_warm = time.perf_counter() - t0
        audio_warm = r2.content

        latency_hdr = float(r.headers.get("x-latency-seconds", dt_cold))
        chars = len(texto)

        print(
            f"  [{i+1}] chars={chars:<4} | cold={dt_cold:.3f}s | warm={dt_warm:.3f}s "
            f"| server_lat={latency_hdr:.3f}s | bytes={len(audio_cold)}"
        )

        latencies_cold.append(dt_cold)
        latencies_warm.append(dt_warm)

        # salva o áudio da 1ª solicitação
        fname = os.path.join(OUT_DIR, f"api_sample_{i+1:02d}.mp3")
        with open(fname, "wb") as f:
            f.write(audio_cold)

        REPORT.append({
            "sample": i + 1,
            "chars": chars,
            "latency_cold_s": round(dt_cold, 4),
            "latency_warm_s": round(dt_warm, 4),
            "server_latency_s": round(latency_hdr, 4),
            "bytes": len(audio_cold),
            "file": fname,
        })

    print(f"\n  Média cold : {statistics.mean(latencies_cold):.3f}s")
    print(f"  Mediana cold: {statistics.median(latencies_cold):.3f}s")
    print(f"  Média warm : {statistics.mean(latencies_warm):.3f}s")
    print(f"  P95 cold   : {sorted(latencies_cold)[int(len(latencies_cold)*0.95)]:.3f}s")


async def test_get_endpoint(client: httpx.AsyncClient):
    print_sep("4. Endpoint GET /synthesize (browser-friendly)")
    texto = "Testando acesso via GET, fácil de usar no navegador!"
    t0 = time.perf_counter()
    r = await client.get("/synthesize", params={"text": texto})
    dt = time.perf_counter() - t0
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/mpeg")
    fname = os.path.join(OUT_DIR, "api_get_test.mp3")
    with open(fname, "wb") as f:
        f.write(r.content)
    print(f"  Latência: {dt:.3f}s | bytes: {len(r.content)} | salvo: {fname}")


async def test_streaming(client: httpx.AsyncClient):
    print_sep("5. Streaming /synthesize (stream=true)")
    texto = "Esta é uma resposta em modo streaming. Os chunks chegam conforme são gerados."
    t0 = time.perf_counter()
    chunks = []
    first_chunk_time = None
    async with client.stream("POST", "/synthesize", json={"text": texto, "stream": True}) as r:
        assert r.status_code == 200
        async for chunk in r.aiter_bytes(1024):
            if first_chunk_time is None:
                first_chunk_time = time.perf_counter() - t0
            chunks.append(chunk)
    total_time = time.perf_counter() - t0
    total_bytes = sum(len(c) for c in chunks)
    fname = os.path.join(OUT_DIR, "api_stream_test.mp3")
    with open(fname, "wb") as f:
        for c in chunks:
            f.write(c)
    print(f"  Tempo até 1º chunk: {first_chunk_time:.3f}s")
    print(f"  Tempo total       : {total_time:.3f}s")
    print(f"  Chunks recebidos  : {len(chunks)} | bytes: {total_bytes}")
    print(f"  Arquivo           : {fname}")
    REPORT.append({
        "sample": "stream",
        "first_chunk_s": round(first_chunk_time, 4),
        "total_s": round(total_time, 4),
        "chunks": len(chunks),
        "bytes": total_bytes,
    })


async def test_cache_efficiency(client: httpx.AsyncClient):
    print_sep("6. Eficiência do Cache (10x mesmo texto)")
    texto = "Cache de voz ativado para respostas instantâneas."
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        r = await client.post("/synthesize", json={"text": texto})
        times.append(time.perf_counter() - t0)
    print(f"  1ª chamada (cold): {times[0]:.3f}s")
    print(f"  Média 2-10 (warm): {statistics.mean(times[1:]):.3f}s")
    print(f"  Speedup cache    : {times[0]/statistics.mean(times[1:]):.1f}×")


async def main():
    print("\n🎙️  TTS API — Testes locais")
    print(f"  Base URL: {BASE_URL}")
    print(f"  Saída   : {OUT_DIR}")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Verifica se servidor está rodando
        try:
            await client.get("/health")
        except httpx.ConnectError:
            print("\n❌  Servidor não está rodando. Inicie com:")
            print("     python -m uvicorn main:app --reload")
            return

        await test_health(client)
        await test_voices(client)
        await test_synthesize_latency(client)
        await test_get_endpoint(client)
        await test_streaming(client)
        await test_cache_efficiency(client)

    # Salva relatório JSON
    report_path = os.path.join(OUT_DIR, "api_benchmark_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=2)

    print_sep("RESUMO")
    print(f"  ✅ Todos os testes passaram")
    print(f"  📁 Áudios salvos em: {OUT_DIR}")
    print(f"  📊 Relatório JSON  : {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
