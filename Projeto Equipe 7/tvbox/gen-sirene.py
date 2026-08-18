#!/usr/bin/env python3
# Gera a sirene do alarme localmente. WAV de proposito: o aplay (alsa-utils)
# toca nativo, sem mpg123 nem decoder, e o arquivo nao depende de download --
# um curl que falha vira HTML salvo com nome de mp3, e o erro so aparece na
# hora em que o alarme precisava tocar.
#
# A varredura de 600 a 1400 Hz e escolha deliberada: e a faixa onde o ouvido e
# mais sensivel e onde alto-falante pequeno reproduz bem. Tom agudo puro (9 kHz,
# comum nos "sons de alarme" de banco de audio) soa alto no celular e some na
# caixinha ligada na saida de linha.
import math, struct, sys, wave

OUT  = sys.argv[1] if len(sys.argv) > 1 else "/opt/secbox/sounds/sirene.wav"
SEC  = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
RATE = 44100
LO, HI, SWEEP = 600.0, 1400.0, 0.5   # grave, agudo, ciclos por segundo

frames = bytearray()
phase = 0.0
for i in range(int(RATE * SEC)):
    t = i / RATE
    freq = LO + (HI - LO) * (0.5 - 0.5 * math.cos(2 * math.pi * SWEEP * t))
    # a fase e integrada em vez de calculada por sin(2*pi*f*t): sem isso a
    # mudanca de frequencia produz saltos de fase, que viram estalos.
    phase += 2 * math.pi * freq / RATE
    v = int(32767 * 0.8 * math.sin(phase))
    frames += struct.pack("<hh", v, v)

with wave.open(OUT, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(bytes(frames))
print(f"{OUT}: {SEC:.0f}s, {RATE} Hz, estereo")
