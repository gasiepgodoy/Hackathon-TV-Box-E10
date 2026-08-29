#!/usr/bin/env python3
# Impede que UMA porta USB instável derrube as outras.
#
# O problema real: as duas portas desta box penduram no mesmo controlador
# (xhci-hcd.2.auto — a USB 3.0 não é um controlador separado, só outro root hub
# do mesmo bloco). Um dispositivo que falha a enumeração fica em laço, e cada
# tentativa mexe no controlador inteiro: já bastou uma câmera ruim para levar
# junto a câmera boa, que estava num hub com fonte própria.
#
# Isolamento de verdade seria hardware. O que dá para fazer em software é tirar
# do ar a porta que está stormando, em vez de deixar o kernel tentando para
# sempre. Duas camadas:
#
#   1. early_stop=1 em toda porta. O kernel desiste de um dispositivo que falha
#      a enumeração repetidas vezes, em vez de repetir indefinidamente. É o
#      remédio barato, e vale mesmo com este serviço fora do ar.
#   2. Quarentena. Uma porta que reenumera demais em pouco tempo é desligada
#      por um tempo crescente, e depois ganha nova chance. Uma câmera ruim para
#      de existir; as outras continuam funcionando.
#
# A quarentena NUNCA cai sobre uma porta que tem um hub: desligar o hub levaria
# junto tudo que está pendurado nele, que é exatamente o dano que este serviço
# existe para evitar.
import json, os, time
from glob import glob

BASE = "/opt/secbox"
STATUS = BASE + "/usb-guard.json"

INTERVAL = 5      # segundos entre varreduras
WINDOW = 300      # janela de observação
LIMIT = 8         # reenumerações na janela que caracterizam um laço
BACKOFF0 = 900    # 15 min de quarentena na primeira vez
BACKOFF_MAX = 4 * 3600
LOG_EVENTS = 40   # eventos guardados para o relatório


def portas():
    """{caminho real da porta: nome legível}. Redescoberto a cada volta, porque
    as portas de um hub deixam de existir quando o hub cai."""
    achadas = {}
    for p in glob("/sys/bus/usb/devices/*/*-port[0-9]*") + \
             glob("/sys/bus/usb/devices/*/*/*-port[0-9]*"):
        real = os.path.realpath(p)
        if os.path.isdir(real):
            achadas[real] = os.path.basename(real)
    return achadas


def ler(caminho, arquivo, padrao=""):
    try:
        with open(os.path.join(caminho, arquivo)) as f:
            return f.read().strip()
    except OSError:
        return padrao


def escrever(caminho, arquivo, valor):
    try:
        with open(os.path.join(caminho, arquivo), "w") as f:
            f.write(valor)
        return True
    except OSError:
        return False


def anexado(porta):
    """(devnum, produto, é_hub) do dispositivo na porta; devnum None se vazia."""
    dev = os.path.join(porta, "device")
    if not os.path.isdir(dev):
        return None, "", False
    devnum = ler(dev, "devnum")
    # bDeviceClass 09 = hub. Guardado porque desligar a porta de um hub
    # derrubaria todos os filhos dele.
    ehub = ler(dev, "bDeviceClass") == "09"
    return (devnum or None), ler(dev, "product"), ehub


class Vigia:
    def __init__(self):
        self.hist = {}       # porta -> [instantes de reenumeração]
        self.ultimo = {}     # porta -> ultimo devnum visto
        self.quarentena = {} # porta -> {"ate": ts, "backoff": s, "nome": str}
        self.eventos = []
        self.early = set()
        self.reincidencia = {}  # porta -> quantas quarentenas ja teve

    def registrar(self, texto):
        agora = int(time.time())
        self.eventos.append({"ts": agora, "texto": texto})
        del self.eventos[:-LOG_EVENTS]
        print(texto, flush=True)

    def varrer(self):
        agora = time.time()
        achadas = portas()

        for porta, nome in achadas.items():
            # early_stop vale para portas novas também: quando o hub volta, as
            # portas dele são objetos novos e nascem com o padrão do kernel.
            if porta not in self.early:
                if ler(porta, "early_stop") == "no":
                    escrever(porta, "early_stop", "1")
                self.early.add(porta)

            q = self.quarentena.get(porta)
            if q:
                if agora >= q["ate"]:
                    escrever(porta, "disable", "0")
                    self.hist[porta] = []
                    self.registrar("porta %s reabilitada apos quarentena" % nome)
                    del self.quarentena[porta]
                continue

            devnum, prod, ehub = anexado(porta)
            anterior = self.ultimo.get(porta, "nunca visto")
            if anterior != "nunca visto" and devnum != anterior:
                # Mudou o numero do dispositivo: houve uma enumeração nova.
                # Conta tanto conectar quanto desconectar.
                self.hist.setdefault(porta, []).append(agora)
            self.ultimo[porta] = devnum

            recentes = [t for t in self.hist.get(porta, []) if agora - t <= WINDOW]
            self.hist[porta] = recentes
            if len(recentes) < LIMIT:
                continue

            if ehub:
                # Um hub instável é problema de verdade, mas desligá-lo mataria
                # todos os filhos. Denuncia e não age.
                self.registrar("porta %s tem um HUB reenumerando (%d vezes em "
                               "%ds) -- NAO desligada, derrubaria tudo que esta "
                               "nela" % (nome, len(recentes), WINDOW))
                self.hist[porta] = []
                continue

            # Reincidente fica de fora por mais tempo: a porta que volta a
            # stormar logo depois de reabilitada nao vai melhorar sozinha, e
            # tentar de novo a cada 15 min so devolve o problema ao barramento.
            n = self.reincidencia.get(porta, 0)
            backoff = min(BACKOFF0 * (2 ** n), BACKOFF_MAX)
            self.reincidencia[porta] = n + 1
            if escrever(porta, "disable", "1"):
                como = "porta desligada"
            elif escrever(os.path.join(porta, "device"), "authorized", "0"):
                como = "dispositivo desautorizado"
            else:
                self.registrar("porta %s stormando (%d em %ds) e nao consegui "
                               "desliga-la" % (nome, len(recentes), WINDOW))
                self.hist[porta] = []
                continue

            self.quarentena[porta] = {"ate": agora + backoff, "backoff": backoff,
                                      "nome": nome}
            self.registrar("porta %s (%s) reenumerou %d vezes em %ds: %s por "
                           "%d min" % (nome, prod or "sem produto",
                                       len(recentes), WINDOW, como, backoff // 60))
            self.hist[porta] = []

        # Porta que sumiu do sysfs (o hub caiu) sai da quarentena logica.
        for porta in list(self.quarentena):
            if porta not in achadas:
                del self.quarentena[porta]

    def gravar_status(self):
        estado = {
            "ts": int(time.time()),
            "quarentena": [{"porta": q["nome"],
                            "faltam_s": max(0, int(q["ate"] - time.time()))}
                           for q in self.quarentena.values()],
            "eventos": self.eventos[-10:],
        }
        tmp = STATUS + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(estado, f, indent=2)
            os.replace(tmp, STATUS)
        except OSError:
            pass


def main():
    v = Vigia()
    print("usb-guard iniciado (janela %ds, limite %d reenumeracoes)"
          % (WINDOW, LIMIT), flush=True)
    while True:
        try:
            v.varrer()
            v.gravar_status()
        except Exception as e:               # nunca morrer por um caso raro
            print("erro na varredura:", e, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
