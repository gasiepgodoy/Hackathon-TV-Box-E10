#!/usr/bin/env python3
# ==============================================================================
# MultiForge — Google Cloud Spot VM (32 vCPUs) Distro Compiler & Launcher
# ==============================================================================
# Executa a compilação completa da distro ForgeOS em uma máquina spot efêmera
# de alta performance (32 vCPUs) e auto-destrói a VM assim que termina.
# Custo estimado: ~R$ 0,10 a 0,30 por compilação (menos de 5 minutos).
# ==============================================================================

import os
import sys
import time
import tarfile
import subprocess
import argparse

INSTANCE_NAME = "forgeos-builder-spot-32"
ZONE = "us-central1-a"
ZONES = ["us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f"]
PROJECT = "stt-465818"
BOOT_DISK_SIZE = "60GB"
MACHINE_TYPES = [
    "n2-standard-32",   # 32 vCPUs / 128GB RAM (Intel Ice Lake - Max Quota)
    "c2d-standard-32",  # 32 vCPUs / 128GB RAM (AMD EPYC Milan - Max Quota)
    "n2-standard-16",   # 16 vCPUs / 64GB RAM (Intel Ice Lake)
    "c2d-standard-16",  # 16 vCPUs / 64GB RAM (AMD EPYC Milan)
    "n2-standard-8",    # 8 vCPUs / 32GB RAM (Intel Ice Lake)
    "e2-standard-8"     # 8 vCPUs / 32GB RAM (Fallback)
]
IMAGE_FAMILY = "ubuntu-2404-lts-amd64"
IMAGE_PROJECT = "ubuntu-os-cloud"

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOWNLOADS_DIR = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\Aluno"), "Downloads")
GCLOUD_CMD = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\Aluno"), "google-cloud-sdk", "bin", "gcloud.cmd")
if not os.path.exists(GCLOUD_CMD):
    GCLOUD_CMD = "gcloud"


def log(msg):
    print(f"\033[1;34m[GCP-SPOT]\033[0m {msg}", flush=True)


def ok(msg):
    print(f"\033[1;32m[GCP-SPOT OK]\033[0m {msg}", flush=True)


def err(msg):
    print(f"\033[1;31m[GCP-SPOT ERROR]\033[0m {msg}", file=sys.stderr, flush=True)


def run_gcloud(args, check=True):
    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = r"C:\Users\Aluno\AppData\Local\Programs\Python\Python312\python.exe"
    cmd = [GCLOUD_CMD] + args + [f"--project={PROJECT}"]
    log(f"Executando: {' '.join(cmd)}")
    res = subprocess.run(cmd, text=True, capture_output=True, env=env)
    if res.returncode != 0 and check:
        err(f"Comando falhou com código {res.returncode}:\n{res.stderr}")
        raise RuntimeError(res.stderr)
    return res


def create_spot_vm():
    global ZONE
    for mtype in MACHINE_TYPES:
        for z in ZONES:
            log(f"1. Tentando criar Instância Spot ({mtype}) na zona {z}...")
            args = [
                "compute", "instances", "create", INSTANCE_NAME,
                f"--zone={z}",
                f"--machine-type={mtype}",
                "--provisioning-model=SPOT",
                "--instance-termination-action=DELETE",
                f"--boot-disk-size={BOOT_DISK_SIZE}",
                "--boot-disk-type=pd-ssd",
                f"--image-family={IMAGE_FAMILY}",
                f"--image-project={IMAGE_PROJECT}",
                "--scopes=cloud-platform"
            ]
            res = run_gcloud(args, check=False)
            if res.returncode == 0:
                ZONE = z
                ok(f"Instância Spot ({mtype}) criada com sucesso na zona {ZONE}!")
                return True
            log(f"Máquina {mtype} indisponível na zona {z}, tentando próxima...")
    
    raise RuntimeError("Não foi possível alocar uma instância Spot nas configurações solicitadas.")


def wait_for_ssh():
    log("2. Aguardando inicialização do SSH na VM (até 90s)...")
    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = r"C:\Users\Aluno\AppData\Local\Programs\Python\Python312\python.exe"
    
    for i in range(18):
        time.sleep(5)
        res = subprocess.run(
            [GCLOUD_CMD, "compute", "ssh", INSTANCE_NAME, f"--zone={ZONE}", f"--project={PROJECT}", "--command=echo ready", "--quiet"],
            capture_output=True, text=True, env=env
        )
        if "ready" in res.stdout:
            ok("SSH pronto e conectado!")
            return True
        print(".", end="", flush=True)
    print()
    return False


def build_and_download():
    log("3. Compactando e enviando código do MultiForge para a Spot VM...")
    tar_path = os.path.join(os.environ.get("TEMP", r"C:\tmp"), "multiforge.tar.gz")
    os.makedirs(os.path.dirname(tar_path), exist_ok=True)
    
    def exclude_filter(tarinfo):
        parts = tarinfo.name.replace("\\", "/").split("/")
        excluded_dirs = {".git", "node_modules", "target", "dist", ".cargo"}
        if any(p in excluded_dirs for p in parts):
            return None
        return tarinfo

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(REPO_ROOT, arcname="multi-forge", filter=exclude_filter)
    
    log(f"Arquivo gerado ({os.path.getsize(tar_path)} bytes). Enviando via gcloud scp...")
    run_gcloud(["compute", "scp", tar_path, f"{INSTANCE_NAME}:/tmp/multiforge.tar.gz", f"--zone={ZONE}", "--quiet"])
    
    log("4. Executando compilação paralela com vCPUs na Spot VM...")
    remote_script = (
        "sudo bash -c '"
        "mkdir -p /root && "
        "tar -xzf /tmp/multiforge.tar.gz -C /root/ && "
        "chmod +x /root/multi-forge/ForgeOS/distro/build-image.sh && "
        "OUTPUT_DIR=/root/distro_output /root/multi-forge/ForgeOS/distro/build-image.sh"
        "'"
    )
    
    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = r"C:\Users\Aluno\AppData\Local\Programs\Python\Python312\python.exe"
    
    res = subprocess.run(
        [GCLOUD_CMD, "compute", "ssh", INSTANCE_NAME, f"--zone={ZONE}", f"--project={PROJECT}", f"--command={remote_script}", "--quiet"],
        text=True, env=env
    )
    if res.returncode != 0:
        err("Erro na compilação dentro da Spot VM!")
        return False

    log("5. Baixando a imagem gerada (.img.xz e .sha256) para Downloads...")
    dest_dir = DOWNLOADS_DIR
    
    # Copia para pasta temporária com permissão no guest antes do scp
    fix_perm = "sudo cp -r /root/distro_output /tmp/distro_output && sudo chmod -R 777 /tmp/distro_output"
    subprocess.run([GCLOUD_CMD, "compute", "ssh", INSTANCE_NAME, f"--zone={ZONE}", f"--project={PROJECT}", f"--command={fix_perm}", "--quiet"], env=env)
    
    run_gcloud(["compute", "scp", "--recurse", f"{INSTANCE_NAME}:/tmp/distro_output/*", dest_dir, f"--zone={ZONE}", "--quiet"])
    ok(f"Arquivos baixados com sucesso para: {dest_dir}")
    return True


def delete_spot_vm():
    log(f"6. DESTRUINDO INSTÂNCIA SPOT {INSTANCE_NAME} (Economia 100%)...")
    env = os.environ.copy()
    env["CLOUDSDK_PYTHON"] = r"C:\Users\Aluno\AppData\Local\Programs\Python\Python312\python.exe"
    subprocess.run(
        [GCLOUD_CMD, "compute", "instances", "delete", INSTANCE_NAME, f"--zone={ZONE}", f"--project={PROJECT}", "--quiet"],
        capture_output=True, text=True, env=env
    )
    ok("Instância deletada. Zero cobrança contínua!")


def main():
    global PROJECT, ZONE
    parser = argparse.ArgumentParser(description="MultiForge GCP Spot VM 32 vCPU Builder")
    parser.add_argument("--project", default=PROJECT, help="ID do projeto GCP")
    parser.add_argument("--zone", default=ZONE, help="Zona GCP")
    parser.add_argument("--keep-vm", action="store_true", help="Não deletar a VM ao final (para debug)")
    args = parser.parse_args()

    PROJECT = args.project
    ZONE = args.zone

    log(f"Iniciando Build de Alta Performance na GCP Spot (Projeto: {PROJECT}, Zona: {ZONE})...")
    try:
        create_spot_vm()
        if not wait_for_ssh():
            raise RuntimeError("Timeout esperando SSH na Spot VM.")
        success = build_and_download()
        if success:
            ok("BUILD FORGEOS CONCLUÍDO COM SUCESSO!")
        else:
            err("O build falhou.")
    finally:
        if not args.keep_vm:
            delete_spot_vm()
        else:
            log("VM mantida (--keep-vm ativo).")


if __name__ == "__main__":
    main()
