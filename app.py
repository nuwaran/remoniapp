# app.py
import eventlet
eventlet.monkey_patch()  # Enable async for SocketIO

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import pandas as pd
from datetime import datetime, timedelta
import os
import threading
import time
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import socketio as client_socketio

# Custom modules (make sure these are in your project)
from nlp_engine import nlp_engine
from utils import df_to_text, filter_raw_df, plot_vital_sign
from request_to_openai import gpt

# -------------------------------
# Flask & SocketIO setup
# -------------------------------
app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# ==================== Raspberry Pi Client Setup ====================
RASPBERRY_PI_URL = 'http://10.127.124.254:5000'  # Update with your Pi's IP
sio_client = client_socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=5)
pi_connected = False

latest_vitals_from_pi = {
    'heart_rate': 0,
    'spo2': 0,
    'blood_pressure': {'systolic': 0, 'diastolic': 0},
    'skin_temperature': 0,
    'timestamp': 0,
    'datetime': 'Never',
    'patient_id': '00001'
}

fall_alerts = []

# -------------------------------
# CSV path for patient
# -------------------------------
PATIENT_CSV = './static/local_data/patient_00001.csv'
PLOT_FOLDER = './static/local_data/show_data/'
os.makedirs(PLOT_FOLDER, exist_ok=True)

# Load or initialize patient CSV
if os.path.exists(PATIENT_CSV):
    patient_df = pd.read_csv(PATIENT_CSV)
else:
    patient_df = pd.DataFrame(columns=[
        "time_stamp", "heart_rate", "steps",
        "accelerometer_x", "accelerometer_y", "accelerometer_z",
        "gyroscope_x", "gyroscope_y", "gyroscope_z",
        "gravity_x", "gravity_y", "gravity_z",
        "linear_accel_x", "linear_accel_y", "linear_accel_z",
        "temperature", "pressure", "light", "proximity",
        "rotation_0", "rotation_1", "rotation_2", "rotation_3", "rotation_4"
    ])
    patient_df.to_csv(PATIENT_CSV, index=False)

latest_watch_data = None

# ==================== Raspberry Pi Event Handlers ====================
@sio_client.event
def connect():
    global pi_connected
    pi_connected = True
    print(f'✓ CONNECTED TO RASPBERRY PI SERVER ({RASPBERRY_PI_URL})')
    socketio.emit('pi_status', {'connected': True})

@sio_client.event
def disconnect():
    global pi_connected
    pi_connected = False
    print('✗ DISCONNECTED FROM RASPBERRY PI SERVER')
    socketio.emit('pi_status', {'connected': False})

@sio_client.event
def connect_error(data):
    print(f'❌ CONNECTION ERROR: {data}')

@sio_client.on('vitals_update')
def on_vitals_update(data):
    global latest_vitals_from_pi
    latest_vitals_from_pi = data
    socketio.emit('vitals_update', data)

@sio_client.on('fall_alert')
def on_fall_alert(data):
    global fall_alerts
    fall_alerts.append(data)
    socketio.emit('fall_alert', data)

def connect_to_raspberry_pi():
    max_retries = 3
    for retry_count in range(max_retries):
        try:
            print(f'🔌 Attempting to connect to Raspberry Pi ({retry_count+1}/{max_retries})...')
            sio_client.connect(RASPBERRY_PI_URL, wait_timeout=10)
            return True
        except Exception as e:
            print(f'❌ Connection failed: {e}')
            time.sleep(3)
    print('⚠️ Could not connect to Raspberry Pi, continuing without it.')
    return False

def reconnect_loop():
    while True:
        time.sleep(30)
        if not pi_connected and not sio_client.connected:
            print('🔄 Reconnection attempt...')
            try:
                connect_to_raspberry_pi()
            except Exception as e:
                print(f'❌ Reconnect failed: {e}')

# ==================== Routes ====================
@app.route("/")
def index():
    return render_template('doctor.html')

@app.route("/api/pi_status", methods=['GET'])
def get_pi_status():
    return jsonify({'connected': pi_connected, 'url': RASPBERRY_PI_URL})

@app.route("/api/latest_vitals_from_pi", methods=['GET'])
def get_latest_vitals_from_pi():
    return jsonify(latest_vitals_from_pi)

@app.route("/api/fall_alerts", methods=['GET'])
def get_fall_alerts():
    return jsonify({'total': len(fall_alerts), 'alerts': fall_alerts[-10:]})

@app.route("/sensor_data", methods=['POST'])
def receive_watch_sensor_data():
    global patient_df, latest_watch_data
    try:
        data = request.get_json()
        latest_watch_data = data.get('sensors', {})
        row = {'time_stamp': datetime.now()}
        row.update(latest_watch_data)
        patient_df = pd.concat([patient_df, pd.DataFrame([row])], ignore_index=True)
        patient_df.to_csv(PATIENT_CSV, index=False)
        print(f"📱 Watch data saved: HR={latest_watch_data.get('heart_rate')}, Steps={latest_watch_data.get('steps')}")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== Helper Functions ====================
def filter_df_by_time_range(df, minutes=10):
    if df.empty:
        return df
    df['time_stamp'] = pd.to_datetime(df['time_stamp'])
    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    return df[df['time_stamp'] >= cutoff_time].copy()

def create_plot(df, vital_sign, time_range_minutes=None):
    if df.empty or vital_sign not in df.columns:
        return None
    df['time_stamp'] = pd.to_datetime(df['time_stamp'])
    df_clean = df[df[vital_sign].notna()].sort_values('time_stamp')
    if df_clean.empty: return None
    plt.figure(figsize=(10,6))
    plt.plot(df_clean['time_stamp'], df_clean[vital_sign], marker='o', linestyle='-', linewidth=2, markersize=6)
    title = vital_sign.replace('_',' ').title()
    if time_range_minutes: title += f" - Last {time_range_minutes} Minutes"
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('Time', fontsize=12)
    ylabel = vital_sign.replace('_',' ').title()
    if vital_sign=='heart_rate': ylabel+=' (BPM)'
    elif vital_sign=='temperature': ylabel+=' (°C)'
    elif vital_sign=='pressure': ylabel+=' (hPa)'
    elif vital_sign=='steps': ylabel+=' (count)'
    plt.ylabel(ylabel, fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plot_filename = f'plot_{vital_sign}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
    plot_path = os.path.join(PLOT_FOLDER, plot_filename)
    plt.savefig(plot_path, dpi=100, bbox_inches='tight')
    plt.close()
    return f'/static/local_data/show_data/{plot_filename}'

# ==================== Chat Endpoint ====================
@app.route("/chat", methods=['POST'])
def chat():
    question = request.get_json().get("message", "")
    question_lower = question.lower()

    # Check for current vitals queries
    vitals_keywords = ['latest', 'current', 'recent', 'vitals', 'blood pressure', 'spo2', 'oxygen']
    if any(word in question_lower for word in vitals_keywords):
        try:
            resp = requests.get(f"{RASPBERRY_PI_URL}/get_current_vitals", timeout=5)
            if resp.status_code == 200:
                vitals_data = resp.json().get("current_vitals", {})
                bp = vitals_data.get("blood_pressure", {})
                vitals_text = (
                    f"• Heart Rate: {vitals_data.get('heart_rate', 0)} BPM\n"
                    f"• SpO2: {vitals_data.get('spo2', 0)}%\n"
                    f"• Blood Pressure: {bp.get('systolic',0)}/{bp.get('diastolic',0)} mmHg\n"
                    f"• Skin Temp: {vitals_data.get('skin_temperature',0)}°C\n"
                    f"• Last Updated: {vitals_data.get('datetime','N/A')}"
                )
                prompt = f"User question: {question}\n\n{vitals_text}\n\nProvide professional response."
                gpt_reply = gpt(text=prompt, model_name="gpt-3.5-turbo", system_prompt="You are a medical assistant.")
                return jsonify({"answer": gpt_reply})
            else:
                return jsonify({"answer": "Could not fetch current vitals from server."})
        except Exception as e:
            return jsonify({"answer": f"Error fetching current vitals: {e}"})

    # NLP and plotting logic
    agent = nlp_engine()
    agent.patient_id = '00001'
    agent.intent_detection(question)
    vital_signs_requested = agent.intent_dict.get('vital_sign', [])
    is_plot = agent.intent_dict.get('is_plot', False)

    # Time range detection
    import re
    time_range_minutes = None
    match_min = re.search(r'(\d+)\s*minute', question_lower)
    match_hr = re.search(r'(\d+)\s*hour', question_lower)
    if match_min: time_range_minutes = int(match_min.group(1))
    if match_hr: time_range_minutes = int(match_hr.group(1)) * 60

    # Fallback keywords mapping
    if not vital_signs_requested:
        keyword_mapping = {
            'heart rate': ['heart_rate'], 'heartrate': ['heart_rate'], 'hr': ['heart_rate'],
            'pulse': ['heart_rate'], 'bpm': ['heart_rate'], 'steps': ['steps'],
            'accelerometer': ['accelerometer_x','accelerometer_y','accelerometer_z'],
            'gyroscope': ['gyroscope_x','gyroscope_y','gyroscope_z'],
            'temperature': ['temperature'], 'temp':['temperature'],
            'pressure': ['pressure'], 'light': ['light'], 'proximity':['proximity']
        }
        for keyword, columns in keyword_mapping.items():
            if keyword in question_lower:
                vital_signs_requested = columns
                break

    if not is_plot:
        plot_keywords = ['plot','graph','chart','visualize','show','trend','history','variation']
        is_plot = any(k in question_lower for k in plot_keywords)

    # Plotting
    if is_plot and vital_signs_requested:
        df = pd.read_csv(PATIENT_CSV)
        if df.empty: return jsonify({"answer":"No data to plot."})
        if time_range_minutes: df = filter_df_by_time_range(df, time_range_minutes)
        plot_paths = [create_plot(df, v, time_range_minutes) for v in vital_signs_requested if create_plot(df,v,time_range_minutes)]
        if not plot_paths: return jsonify({"answer":"Could not generate plots."})
        return jsonify({"answer": f"Plot for {', '.join(vital_signs_requested)}", "plots": plot_paths})

    # Sensor data response
    elif vital_signs_requested:
        df = pd.read_csv(PATIENT_CSV)
        if df.empty: return jsonify({"answer":"No sensor data available."})
        if time_range_minutes: df = filter_df_by_time_range(df, time_range_minutes)
        sensor_data_text = ""
        for vital in vital_signs_requested:
            if vital in df.columns:
                values = df[vital].dropna()
                if len(values)>0: sensor_data_text += f"- {vital.replace('_',' ').title()}: {values.iloc[-1]}\n"
        prompt = f"User question: {question}\n\n{sensor_data_text}\n\nProvide clear response."
        gpt_reply = gpt(text=prompt, model_name="gpt-3.5-turbo", system_prompt="You are a medical assistant.")
        return jsonify({"answer": gpt_reply})

    # General conversation
    else:
        gpt_reply = gpt(text=question, model_name="gpt-3.5-turbo", system_prompt="You are a helpful medical assistant.")
        return jsonify({"answer": gpt_reply})

# ==================== Debug endpoint ====================
@app.route("/debug_data", methods=['GET'])
def debug_data():
    try:
        df = pd.read_csv(PATIENT_CSV)
        latest = df.iloc[-1].to_dict() if not df.empty else {}
        return jsonify({
            "columns": list(df.columns),
            "latest_row": latest,
            "total_rows": len(df),
            "pi_connected": pi_connected,
            "latest_vitals_from_pi": latest_vitals_from_pi,
            "fall_alerts_count": len(fall_alerts)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# ==================== WSGI Entry (Railway / Gunicorn) ====================
wsgi_app = app

# ==================== Local Testing ====================
if __name__ == '__main__':
    threading.Thread(target=connect_to_raspberry_pi, daemon=True).start()
    threading.Thread(target=reconnect_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
