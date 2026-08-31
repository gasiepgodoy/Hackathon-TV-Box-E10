#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MABI Voice Interface Integration Script
--------------------------------------
Este script demonstra como integrar o classificador de intenções local MABI 
(treinado via MatchboxNet + SVM no notebook PROJETO_MABI) com o banco de dados
e o sintetizador de voz (TTS) do repositório MINA.

Modo de uso:
1. Copie o arquivo 'btvox_model_student_svm.pkl' gerado no notebook para a pasta 'models/' deste repositório.
2. Certifique-se de ter as dependências instaladas (librosa, torch, nemo_toolkit ou similar).
3. Execute este script:
   python mabi_voice_interface.py
"""

import os
import sys
import pickle
import asyncio
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav

# Adiciona o diretório atual ao path para garantir que 'src' seja importada
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.academic_db import (
    get_professors, 
    get_recent_news_events, 
    get_active_classes, 
    get_upcoming_classes_today
)
from src.utils.tts_client import TTSClient

# Configurações de caminhos
MODELO_PKL_PATH = os.path.join("models", "btvox_model_student_svm.pkl")
AUDIO_TEMP_PATH = "temp_mabi_input.wav"

# Classes correspondentes aos dígitos falados no Google Speech Commands V2
MAPEAMENTO_CLASSES = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
    5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"
}

# --- 1. FUNÇÃO PARA CARREGAR O CLASSIFICADOR SVM ---
def carregar_classificador_svm():
    if not os.path.exists(MODELO_PKL_PATH):
        print(f"[-] Erro: O arquivo do classificador '{MODELO_PKL_PATH}' não foi encontrado.")
        print("    Por favor, mova o arquivo '.pkl' exportado pelo notebook para a pasta 'models/'.")
        return None
    
    try:
        with open(MODELO_PKL_PATH, 'rb') as f:
            pacote = pickle.load(f)
        print(f"[+] Classificador SVM '{MODELO_PKL_PATH}' carregado com sucesso!")
        return pacote.get("pipeline")
    except Exception as e:
        print(f"[-] Erro ao carregar o classificador: {e}")
        return None

# --- 2. EXTRAÇÃO DE EMBEDDINGS (TEACHER MATCHBOXNET) ---
def extrair_embedding_matchboxnet(caminho_audio):
    """
    Usa o modelo Teacher (NVIDIA NeMo MatchboxNet) para extrair os embeddings
    do áudio de entrada de forma idêntica ao notebook.
    """
    try:
        import librosa
        import torch
        from nemo.collections.asr.models import EncDecClassificationModel
    except ImportError:
        print("[-] Erro: As bibliotecas 'nemo_toolkit', 'librosa' ou 'torch' não estão instaladas.")
        print("    Instale-as rodando: pip install nemo_toolkit[asr] librosa torch")
        return None

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Carrega o modelo MatchboxNet do NeMo
        nome_modelo = "commandrecognition_en_matchboxnet3x1x64_v2"
        model = EncDecClassificationModel.from_pretrained(model_name=nome_modelo)
        model = model.to(device)
        model.eval()

        # Processa o arquivo de áudio (16kHz, mono, 1 segundo)
        sinal, sr = librosa.load(caminho_audio, sr=16000, mono=True)
        sinal = sinal.astype(np.float32)
        if len(sinal) < 16000:
            sinal = np.pad(sinal, (0, 16000 - len(sinal)), mode='constant')
        else:
            sinal = sinal[:16000]

        # Prepara tensores
        sinal_tensor = torch.tensor([sinal], dtype=torch.float32).to(device)
        comprimento_tensor = torch.tensor([len(sinal)], dtype=torch.int64).to(device)

        with torch.no_grad():
            processed_signal, processed_len = model.preprocessor(
                input_signal=sinal_tensor, length=comprimento_tensor
            )
            encoded_features, _ = model.encoder(
                audio_signal=processed_signal, length=processed_len
            )
            embeddings = torch.mean(encoded_features, dim=-1).cpu().numpy().flatten()

        return embeddings
    except Exception as e:
        print(f"[-] Erro na extração de embeddings: {e}")
        return None

# --- 3. MAPEAMENTO DE INTENÇÃO E CONSULTA AO BANCO DA MINA ---
def executar_query_com_intencao_mina(id_intencao):
    """
    Mapeia o ID da intenção predito para uma consulta real no banco da MINA.
    """
    resposta = ""
    
    # Intenção 5 (ex: "five") -> Consultar Sala de Professor
    if id_intencao == 5:
        professores = get_professors()
        if professores:
            # Pega o primeiro professor como demonstração, ou liste-os
            p = professores[0]
            resposta = f"De acordo com a agenda da MINA, o {p['name']} atende na {p['room']} do departamento de {p['department'] or 'Geral'}."
        else:
            resposta = "Não encontrei professores cadastrados no momento. Por favor, adicione docentes ao banco de dados."

    # Intenção 6 (ex: "six") -> Consultar Aulas/Horários
    elif id_intencao == 6:
        aulas_agora = get_active_classes()
        aulas_proximas = get_upcoming_classes_today()
        
        if aulas_agora:
            a = aulas_agora[0]
            resposta = f"Atualmente, a aula de {a['subject']} está ocorrendo na {a['room']} com o professor {a['teacher_name']}."
        elif aulas_proximas:
            a = aulas_proximas[0]
            resposta = f"A próxima aula cadastrada é de {a['subject']} na {a['room']} às {a['start_time']}."
        else:
            resposta = "Não há aulas registradas para hoje na base de dados da MINA."

    # Intenção 8 (ex: "eight") -> Mural de Notícias e Eventos da UNESP
    elif id_intencao == 8:
        noticias = get_recent_news_events(limit=1)
        if noticias:
            n = noticias[0]
            tipo = "evento" if n['is_event'] else "notícia"
            resposta = f"A última {tipo} no mural da UNESP Sorocaba é: {n['title']}."
        else:
            resposta = "O mural de notícias da UNESP Sorocaba está vazio no momento."

    # Intenção 2 (ex: "two") -> Cantina/Alimentação
    elif id_intencao == 2:
        resposta = "A chipa quentinha e os salgados saem na cantina principal da UNESP Sorocaba nos intervalos das 9 horas da manhã e das 20h30 da noite."

    # Outras intenções reservadas ou não mapeadas no Hackathon
    else:
        intencao_str = MAPEAMENTO_CLASSES.get(id_intencao, "desconhecida")
        resposta = f"Comando de voz {id_intencao} ('{intencao_str}') reconhecido, mas este tópico está aguardando mapeamento no assistente virtual."

    return resposta

# --- 4. GRAVAÇÃO DE ÁUDIO PELO MICROFONE ---
def gravar_audio_usuario(segundos=2, taxa_amostragem=16000):
    print(f"\n[*] Gravando áudio por {segundos} segundos... Fale agora!")
    audio = sd.rec(int(segundos * taxa_amostragem), samplerate=taxa_amostragem, channels=1, dtype='float32')
    sd.wait()  # Aguarda a gravação terminar
    print("[*] Gravação concluída.")
    
    # Salva o arquivo em formato WAV temporário
    wav.write(AUDIO_TEMP_PATH, taxa_amostragem, audio)
    return AUDIO_TEMP_PATH

# --- 5. PIPELINE INTEGRADO COMPLETO ---
async def rodar_pipeline_mabi_mina():
    # 1. Carrega o modelo SVM Student
    pipeline_svm = carregar_classificador_svm()
    if not pipeline_svm:
        return

    # 2. Captura de áudio do microfone
    caminho_wav = gravar_audio_usuario(segundos=2)

    # 3. Extração de características (MatchboxNet)
    print("[*] Extraindo embeddings profunda via MatchboxNet...")
    embeddings = extrair_embedding_matchboxnet(caminho_wav)
    if embeddings is None:
        print("[-] Falha ao extrair características do áudio.")
        return

    # 4. Predição com o SVM Student
    vetor_entrada = embeddings.reshape(1, -1)
    intencao_predita = int(pipeline_svm.predict(vetor_entrada)[0])
    intencao_nome = MAPEAMENTO_CLASSES.get(intencao_predita, "Desconhecida")
    
    print(f"\n[+] MABI Classificador: Intenção {intencao_predita} ('{intencao_nome}') identificada.")

    # 5. Consulta ao banco de dados real da MINA
    resposta_texto = executar_query_com_intencao_mina(intencao_predita)
    print(f"[+] Resposta do Banco MINA: '{resposta_texto}'")

    # 6. Síntese de Voz (TTS) com o TTSClient da MINA
    print("[*] Falando a resposta...")
    tts_client = TTSClient(voice="pt-BR-FranciscaNeural")
    
    # Realiza health check interno
    await tts_client.health_check()
    
    if tts_client.enabled:
        task = tts_client.pre_synthesize(resposta_texto)
        if task:
            audio_bytes = await task
            if audio_bytes:
                await tts_client.play(audio_bytes)
    else:
        # Fallback se o TTSClient do edge-tts não estiver habilitado
        print("[!] TTS indisponível. Resposta apenas em texto.")

    await tts_client.close()
    
    # Remove arquivo temporário de áudio
    if os.path.exists(AUDIO_TEMP_PATH):
        os.remove(AUDIO_TEMP_PATH)

if __name__ == "__main__":
    # Verifica se há suporte a sounddevice
    try:
        sd.query_devices()
    except Exception as e:
        print(f"[-] Erro ao inicializar dispositivos de áudio: {e}")
        sys.exit(1)

    asyncio.run(rodar_pipeline_mabi_mina())
