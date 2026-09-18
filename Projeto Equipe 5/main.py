import cv2
import numpy as np
import time
import json
import os
import sqlite3
import threading
import pytz
from datetime import datetime, timedelta
from shapely.geometry import Point, Polygon
from flask import Flask, Response, render_template, request, jsonify

app = Flask(__name__)

# Configurações de performance e sensibilidade da IA
cv2.setNumThreads(1)
CONFIDENCE_THRESHOLD = 0.15  # Reduzido para capturar pessoas no fundo / com oclusão
NMS_THRESHOLD = 0.45
CONFIG_FILE = "config_roi.json"
DB_NAME = "banco_dados.db"
MODO_TESTE_PC = True
TEMPO_POR_ATENDIMENTO = 30  # Segundos fixos por pessoa (Atualizado para 30s)

# Resolução HD para máxima definição da câmera
CAM_WIDTH = 1280
CAM_HEIGHT = 720

# Fuso horário padrão do sistema
FUSO_BR = pytz.timezone('America/Sao_Paulo')

# --- GERENCIAMENTO DO BANCO DE DADOS SQLITE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_fila (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            hora TEXT NOT NULL,
            pessoas_fila INTEGER NOT NULL,
            atendentes INTEGER NOT NULL,
            tempo_espera_seg INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

ultimo_registro_db = 0.0

def salvar_historico_db(qtd_fila, qtd_atendentes, tempo_espera):
    """ Grava métricas usando o fuso horário de Brasília (America/Sao_Paulo) """
    agora = datetime.now(FUSO_BR)
    hora_atual = agora.time()
    
    inicio_pico = datetime.strptime("11:00", "%H:%M").time()
    fim_pico = datetime.strptime("13:20", "%H:%M").time()

    if inicio_pico <= hora_atual <= fim_pico:
        try:
            minuto_arredondado = (agora.minute // 10) * 10
            hora_str = f"{agora.hour:02d}:{minuto_arredondado:02d}"
            data_str = agora.strftime("%Y-%m-%d")

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO historico_fila (data, hora, pessoas_fila, atendentes, tempo_espera_seg)
                VALUES (?, ?, ?, ?, ?)
            ''', (data_str, hora_str, qtd_fila, qtd_atendentes, tempo_espera))
            conn.commit()
            conn.close()
            print(f"[BD] Gravado com sucesso: {hora_str} - {qtd_fila} pessoa(s)")
        except Exception as e:
            print(f"[ERRO] Falha ao salvar no banco: {e}")

# Variáveis globais de sincronização
latest_frame = None
raw_ai_boxes = []
smoothed_boxes = []
pessoas_na_fila = 0
atendentes_ativos = 0
total_detectados = 0
tempo_inferencia = 0.0
last_detection_time = 0.0
fps_display = 0
lock = threading.Lock()

# --- CARREGAMENTO DO MODELO YOLO ---
try:
    net = cv2.dnn.readNetFromONNX("yolov8n.onnx")
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    print("[OK] Modelo YOLOv8 ONNX carregado com sucesso.")
except Exception as e:
    print(f"[ERRO] Falha ao carregar modelo ONNX: {e}")

# --- GERENCIAMENTO DE ROIS ---
roi_fila_points = []
roi_fila_polygon = None
roi_atend_points = []
roi_atend_polygon = None

def load_rois():
    global roi_fila_points, roi_fila_polygon, roi_atend_points, roi_atend_polygon
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                roi_fila_points = data.get("fila", [])
                roi_atend_points = data.get("atendimento", [])
                
            if len(roi_fila_points) == 4:
                roi_fila_polygon = Polygon(roi_fila_points)
            if len(roi_atend_points) == 4:
                roi_atend_polygon = Polygon(roi_atend_points)
            return True
        except Exception as e:
            print(f"[ERRO] Falha ao ler config_roi.json: {e}")
    return False

load_rois()

# --- INICIALIZAÇÃO DA CÂMERA (720p HD) ---
def init_camera():
    for index in [1, 0]:
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
            try:
                ret, _ = cap.read()
                if ret:
                    print(f"[OK] Câmera inicializada em /dev/video{index} ({CAM_WIDTH}x{CAM_HEIGHT})")
                    return cap
            except Exception:
                pass
            cap.release()
    print("[ERRO] Nenhuma webcam encontrada.")
    return None

cap = init_camera()

# --- THREAD DEDICADA DA IA ---
def ai_worker():
    global latest_frame, raw_ai_boxes, tempo_inferencia, last_detection_time
    
    while True:
        if latest_frame is None or 'net' not in globals():
            time.sleep(0.05)
            continue
        
        with lock:
            frame_infer = latest_frame.copy()

        h_orig, w_orig = frame_infer.shape[:2]
        t_start = time.time()

        blob = cv2.dnn.blobFromImage(frame_infer, 1/255.0, (640, 640), swapRB=True, crop=False)
        net.setInput(blob)
        outputs = net.forward()

        outputs = np.array(outputs[0]).T
        boxes, confidences = [], []
        x_factor = w_orig / 640.0
        y_factor = h_orig / 640.0

        for row in outputs:
            classes_scores = row[4:]
            class_id = np.argmax(classes_scores)
            score = classes_scores[class_id]

            if class_id == 0 and score > CONFIDENCE_THRESHOLD:
                cx, cy, w, h = row[0], row[1], row[2], row[3]
                x = int((cx - 0.5 * w) * x_factor)
                y = int((cy - 0.5 * h) * y_factor)
                width = int(w * x_factor)
                height = int(h * y_factor)

                boxes.append([x, y, width, height])
                confidences.append(float(score))

        indices = cv2.dnn.NMSBoxes(boxes, confidences, CONFIDENCE_THRESHOLD, NMS_THRESHOLD)
        
        novas_boxes = []
        if len(indices) > 0:
            for i in indices.flatten():
                novas_boxes.append(boxes[i])
            last_detection_time = time.time()
        
        t_total = time.time() - t_start

        with lock:
            if len(novas_boxes) > 0 or (time.time() - last_detection_time) < 3.0:
                if len(novas_boxes) > 0:
                    raw_ai_boxes = novas_boxes
            else:
                raw_ai_boxes = []
                
            tempo_inferencia = t_total

        time.sleep(0.01)

t_ia = threading.Thread(target=ai_worker, daemon=True)
t_ia.start()

# --- GERADOR DO STREAM PRINCIPAL ---
def generate_frames():
    global cap, latest_frame, smoothed_boxes, pessoas_na_fila, atendentes_ativos, total_detectados, fps_display, ultimo_registro_db
    
    fps_start_time = time.time()
    fps_counter = 0

    while True:
        if cap is None or not cap.isOpened():
            cap = init_camera()
            time.sleep(0.5)

        try:
            ret, frame = cap.read()
        except Exception as e:
            print(f"[AVISO] Falha ao ler frame do OpenCV: {e}")
            ret = False

        if not ret or frame is None:
            if cap:
                cap.release()
            cap = None
            time.sleep(0.5)
            continue

        with lock:
            latest_frame = frame.copy()
            ai_target_boxes = list(raw_ai_boxes)

        if len(ai_target_boxes) > 0:
            if len(smoothed_boxes) != len(ai_target_boxes):
                smoothed_boxes = [list(b) for b in ai_target_boxes]
            else:
                for idx in range(len(smoothed_boxes)):
                    for k in range(4):
                        smoothed_boxes[idx][k] = int(smoothed_boxes[idx][k] * 0.7 + ai_target_boxes[idx][k] * 0.3)
        else:
            smoothed_boxes = []

        fps_counter += 1
        if (time.time() - fps_start_time) >= 1.0:
            fps_display = fps_counter
            fps_counter = 0
            fps_start_time = time.time()

        if len(roi_fila_points) == 4:
            cv2.polylines(frame, [np.array(roi_fila_points)], True, (0, 0, 255), 2)
        else:
            for pt in roi_fila_points:
                cv2.circle(frame, (pt[0], pt[1]), 5, (0, 0, 255), -1)

        if len(roi_atend_points) == 4:
            cv2.polylines(frame, [np.array(roi_atend_points)], True, (0, 255, 255), 2)
        else:
            for pt in roi_atend_points:
                cv2.circle(frame, (pt[0], pt[1]), 5, (0, 255, 255), -1)

        novas_pessoas_fila = 0
        novos_atendentes = 0
        total_p = 0

        for box in smoothed_boxes:
            x, y, w, h = box
            total_p += 1
            
            ponto_ref = Point(x + w//2, y + h//2) if MODO_TESTE_PC else Point(x + w//2, y + h)
            cor = (255, 0, 0)

            if roi_fila_polygon and roi_fila_polygon.contains(ponto_ref):
                novas_pessoas_fila += 1
                cor = (0, 255, 0)
            elif roi_atend_polygon and roi_atend_polygon.contains(ponto_ref):
                novos_atendentes += 1
                cor = (0, 165, 255)

            cv2.rectangle(frame, (x, y), (x + w, y + h), cor, 2)

        pessoas_na_fila = novas_pessoas_fila
        atendentes_ativos = min(novos_atendentes, 2)
        total_detectados = total_p

        curr_time = time.time()
        atendentes_calc = max(atendentes_ativos, 1)
        tempo_espera_seg = int((pessoas_na_fila * TEMPO_POR_ATENDIMENTO) / atendentes_calc)

        # Salva a cada 30s
        if curr_time - ultimo_registro_db >= 30:
            salvar_historico_db(pessoas_na_fila, atendentes_ativos, tempo_espera_seg)
            ultimo_registro_db = curr_time

        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# --- ROTAS FLASK ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/dados')
def api_dados():
    agora = datetime.now(FUSO_BR)
    
    dia_solicitado = request.args.get('dia_semana', default=agora.weekday(), type=int)
    dias_diferenca = dia_solicitado - agora.weekday()
    data_alvo = (agora + timedelta(days=dias_diferenca)).strftime("%Y-%m-%d")

    historico = []
    pico = {"hora": "--:--", "pessoas": 0}
    faixa_pico = "--:-- às --:--"
    media_pessoas = 0

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT hora, MAX(pessoas_fila) 
            FROM historico_fila 
            WHERE data = ? 
            GROUP BY hora
            ORDER BY hora ASC
        ''', (data_alvo,))
        rows = cursor.fetchall()

        max_pessoas = 0

        for r in rows:
            hora, qtd = r[0], r[1]
            historico.append({"hora": hora, "pessoas": qtd})
            
            if qtd > max_pessoas:
                max_pessoas = qtd
                pico = {"hora": hora, "pessoas": qtd}

        if max_pessoas > 0:
            blocos_pico = [r[1] for r in rows if r[1] >= max_pessoas * 0.8]
            horarios_pico = [r[0] for r in rows if r[1] >= max_pessoas * 0.8]
            
            if horarios_pico:
                faixa_pico = f"{horarios_pico[0]} às {horarios_pico[-1]}"
            
            if blocos_pico:
                media_pessoas = round(sum(blocos_pico) / len(blocos_pico))

        if max_pessoas > 0 and media_pessoas == 0:
            media_pessoas = max_pessoas

        conn.close()

    except Exception as e:
        print(f"[ERRO] Falha ao consultar banco: {e}")

    atendentes_calc = max(atendentes_ativos, 1)
    tempo_espera_seg = int((pessoas_na_fila * TEMPO_POR_ATENDIMENTO) / atendentes_calc)

    payload = {
        "pessoas_fila": pessoas_na_fila,
        "atendentes_ativos": atendentes_ativos,
        "atendentes_total": 2,
        "espera_estimada_segundos": tempo_espera_seg,
        "fps": fps_display,
        "inferencia_ms": round(tempo_inferencia * 1000, 1),
        "historico": historico,
        "pico": pico,
        "faixa_pico": faixa_pico,
        "media_pessoas": media_pessoas,
        "dia_selecionado": dia_solicitado,
        "dia_hoje": agora.weekday()
    }
    return jsonify(payload)

@app.route('/set_point', methods=['POST'])
def set_point():
    global roi_fila_points, roi_fila_polygon, roi_atend_points, roi_atend_polygon
    data = request.json
    tipo = data.get('tipo')

    if 'norm_x' in data and 'norm_y' in data:
        x = int(round(data['norm_x'] * CAM_WIDTH))
        y = int(round(data['norm_y'] * CAM_HEIGHT))
    else:
        x = int(data['x'])
        y = int(data['y'])

    x = max(0, min(CAM_WIDTH - 1, x))
    y = max(0, min(CAM_HEIGHT - 1, y))

    if tipo == 'fila':
        if len(roi_fila_points) >= 4:
            roi_fila_points = []
            roi_fila_polygon = None
        roi_fila_points.append([x, y])
        if len(roi_fila_points) == 4:
            roi_fila_polygon = Polygon(roi_fila_points)
        msg = f"ROI Fila: {len(roi_fila_points)}/4 pontos ({x}, {y})"
    else:
        if len(roi_atend_points) >= 4:
            roi_atend_points = []
            roi_atend_polygon = None
        roi_atend_points.append([x, y])
        if len(roi_atend_points) == 4:
            roi_atend_polygon = Polygon(roi_atend_points)
        msg = f"ROI Atendimento: {len(roi_atend_points)}/4 pontos ({x}, {y})"

    with open(CONFIG_FILE, "w") as f:
        json.dump({"fila": roi_fila_points, "atendimento": roi_atend_points}, f)

    return jsonify({"message": msg})

@app.route('/reset_rois', methods=['POST'])
def reset_rois():
    global roi_fila_points, roi_fila_polygon, roi_atend_points, roi_atend_polygon
    roi_fila_points = []
    roi_fila_polygon = None
    roi_atend_points = []
    roi_atend_polygon = None
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    return jsonify({"message": "Todas as ROIs foram apagadas com sucesso."})

@app.route('/reset_banco', methods=['POST'])
def reset_banco():
    try:
        data_hoje = datetime.now(FUSO_BR).strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico_fila WHERE data = ?", (data_hoje,))
        conn.commit()
        conn.close()
        return jsonify({"message": "Histórico do dia apagado com sucesso!"})
    except Exception as e:
        return jsonify({"message": f"Erro ao apagar banco: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)