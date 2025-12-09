import eventlet
eventlet.monkey_patch()  # Enable async for SocketIO

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
from nlp_engine import nlp_engine
import pandas as pd
from datetime import datetime, timedelta
import os
from utils import df_to_text, filter_raw_df, plot_vital_sign
from request_to_openai import gpt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import requests
import socketio as client_socketio
import threading
import time

# -------------------------------
# Flask & SocketIO setup
# -------------------------------
app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# ==================== Raspberry Pi Client Setup ====================
RASPBERRY_PI_URL = 'http://10.127.124.254:5000'  # UPDATE WITH YOUR PI'S IP
sio_client = client_socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=5)
pi_connected = False

# Storage for vitals from Pi (every 2 minutes)
latest_vitals_from_pi = {
    'heart_rate': 0,
    'spo2': 0,
    'blood_pressure': {'systolic': 0, 'diastolic': 0},
    'skin_temperature': 0,
    'timestamp': 0,
    'datetime': 'Never',
    'patient_id': '00001'
}

# Storage for fall alerts
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
    print('\n' + '=' * 70)
    print('✓ CONNECTED TO RASPBERRY PI SERVER')
    print('=' * 70)
    print(f'   URL: {RASPBERRY_PI_URL}')
    print(f'   Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70 + '\n')
    socketio.emit('pi_status', {'connected': True})

@sio_client.event
def disconnect():
    global pi_connected
    pi_connected = False
    print('\n' + '=' * 70)
    print('✗ DISCONNECTED FROM RASPBERRY PI SERVER')
    print('=' * 70)
    print(f'   Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70 + '\n')
    socketio.emit('pi_status', {'connected': False})

@sio_client.event
def connect_error(data):
    print(f'\n❌ CONNECTION ERROR: {data}\n')

@sio_client.on('vitals_update')
def on_vitals_update(data):
    global latest_vitals_from_pi
    print(f"\n[RECEIVED VITALS UPDATE] {data}")
    latest_vitals_from_pi = data
    socketio.emit('vitals_update', data)
    # Chat message for vitals
    bp = data.get('blood_pressure', {})
    vitals_message = (
        f"📊 Latest Vitals Update:\n"
        f"• Heart Rate: {data.get('heart_rate', 0)} BPM\n"
        f"• SpO2: {data.get('spo2', 0)}%\n"
        f"• Blood Pressure: {bp.get('systolic', 0)}/{bp.get('diastolic', 0)} mmHg\n"
        f"• Skin Temperature: {data.get('skin_temperature', 0)}°C\n"
        f"Time: {data.get('datetime', 'N/A')}"
    )
    socketio.emit('chat_message', {
        'type': 'vitals',
        'message': vitals_message,
        'timestamp': data.get('datetime', 'N/A')
    })

@sio_client.on('fall_alert')
def on_fall_alert(data):
    global fall_alerts
    print(f"\n[FALL ALERT] {data}")
    fall_alerts.append(data)
    socketio.emit('fall_alert', data)
    emergency_msg = (
        f"🚨 EMERGENCY ALERT!\n\n"
        f"Fall detected for Patient {data.get('patient_id', 'N/A')}\n"
        f"Confidence: {data.get('confidence', 0)}%\n"
        f"Time: {data.get('datetime', 'N/A')}\n\n"
        f"⚠️ IMMEDIATE ATTENTION REQUIRED"
    )
    socketio.emit('chat_message', {
        'type': 'emergency',
        'message': emergency_msg,
        'timestamp': data.get('datetime', 'N/A')
    })

def connect_to_raspberry_pi():
    global pi_connected
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            print(f'\n🔌 Attempting to connect to Raspberry Pi ({retry_count+1}/{max_retries})...')
            sio_client.connect(RASPBERRY_PI_URL, wait_timeout=10)
            return True
        except Exception as e:
            retry_count += 1
            print(f'   ❌ Connection failed: {e}')
            time.sleep(3)
    print('⚠️  Could not connect to Raspberry Pi, continuing without it.')
    return False

def reconnect_loop():
    global pi_connected
    while True:
        time.sleep(30)
        if not pi_connected and not sio_client.connected:
            print('\n🔄 Reconnection attempt...')
            try:
                connect_to_raspberry_pi()
            except Exception as e:
                print(f'   ❌ Reconnect failed: {e}')

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

# -------------------------------
# Helper Functions
# -------------------------------
def filter_df_by_time_range(df, minutes=10):
    if df.empty:
        return df
    df['time_stamp'] = pd.to_datetime(df['time_stamp'])
    cutoff_time = datetime.now() - timedelta(minutes=minutes)
    return df[df['time_stamp'] >= cutoff_time].copy()

def create_plot(df, vital_sign, time_range_minutes=None):
    if df.empty:
        return None
    df['time_stamp'] = pd.to_datetime(df['time_stamp'])
    df = df.sort_values('time_stamp')
    df_clean = df[df[vital_sign].notna()].copy()
    if df_clean.empty:
        return None
    plt.figure(figsize=(10,6))
    plt.plot(df_clean['time_stamp'], df_clean[vital_sign], marker='o', linestyle='-', linewidth=2, markersize=6)
    title = f"{vital_sign.replace('_',' ').title()}"
    if time_range_minutes:
        title += f" - Last {time_range_minutes} Minutes"
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('Time', fontsize=12)
    ylabel = vital_sign.replace('_',' ').title()
    if vital_sign=='heart_rate': ylabel+=' (bpm)'
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

# -------------------------------
# Chat Endpoint (UPDATED to fetch current vitals from Python server)
# -------------------------------
@app.route("/chat", methods=['POST'])
def chat():
    question = request.get_json().get("message", "")
    question_lower = question.lower()

    # Check for queries about current vitals
    vitals_keywords = ['latest', 'current', 'recent', 'vitals', 'blood pressure', 'spo2', 'oxygen']
    if any(word in question_lower for word in vitals_keywords):
        try:
            # Fetch current vitals from Python server
            resp = requests.get("http://10.127.124.254:5000/get_current_vitals", timeout=5)
            if resp.status_code == 200:
                vitals_data = resp.json().get("current_vitals", {})
                bp = vitals_data.get("blood_pressure", {})
                vitals_text = f"""
Current Vital Signs:
• Heart Rate: {vitals_data.get('heart_rate', 0)} BPM
• SpO2: {vitals_data.get('spo2', 0)}%
• Blood Pressure: {bp.get('systolic', 0)}/{bp.get('diastolic', 0)} mmHg
• Skin Temperature: {vitals_data.get('skin_temperature', 0)}°C
• Last Updated: {vitals_data.get('datetime', 'N/A')}
"""
                system_prompt = """You are a medical assistant. Analyze these vital signs and provide insights."""
                prompt = f"User question: {question}\n\n{vitals_text}\n\nProvide a clear, professional response."
                gpt_reply = gpt(text=prompt, model_name="gpt-3.5-turbo", system_prompt=system_prompt)
                return jsonify({"answer": gpt_reply})
            else:
                return jsonify({"answer": "Could not fetch current vitals from health server."})
        except Exception as e:
            return jsonify({"answer": f"Error fetching current vitals: {e}"})

    # -------------------------------
    # Existing NLP & plotting logic
    # -------------------------------
    agent = nlp_engine()
    agent.patient_id = '00001'
    agent.intent_detection(question)
    vital_signs_requested = agent.intent_dict.get('vital_sign', [])
    is_plot = agent.intent_dict.get('is_plot', False)

    # Time range detection
    time_range_minutes = None
    import re
    match_min = re.search(r'(\d+)\s*minute', question_lower)
    match_hr = re.search(r'(\d+)\s*hour', question_lower)
    if match_min: time_range_minutes = int(match_min.group(1))
    if match_hr: time_range_minutes = int(match_hr.group(1)) * 60

    # Fallback keywords
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

    # Case: Plot requested
    if is_plot and vital_signs_requested:
        try:
            df = pd.read_csv(PATIENT_CSV)
            if df.empty:
                return jsonify({"answer":"No data available to plot."})
            if time_range_minutes:
                df = filter_df_by_time_range(df, time_range_minutes)
                if df.empty:
                    return jsonify({"answer": f"No data found in last {time_range_minutes} minutes."})
            plot_paths = []
            for vital in vital_signs_requested:
                if vital in df.columns:
                    plot_path = create_plot(df, vital, time_range_minutes)
                    if plot_path: plot_paths.append(plot_path)
            if not plot_paths: return jsonify({"answer":"Could not generate plots."})
            time_info = f"last {time_range_minutes} minutes" if time_range_minutes else "all available data"
            response = f"I've created a plot showing {', '.join([v.replace('_',' ') for v in vital_signs_requested])} for the {time_info}."
            return jsonify({"answer": response, "plots": plot_paths})
        except Exception as e:
            return jsonify({"answer": f"Error creating plot: {str(e)}"})

    # Case: Specific sensor data
    elif vital_signs_requested:
        try:
            df = pd.read_csv(PATIENT_CSV)
            if df.empty: return jsonify({"answer":"No sensor data available yet."})
            if time_range_minutes: df = filter_df_by_time_range(df, time_range_minutes)
            sensor_data_text = ""
            for vital in vital_signs_requested:
                if vital in df.columns:
                    values = df[vital].dropna()
                    if len(values)>0:
                        sensor_data_text += f"- {vital.replace('_',' ').title()}: {values.iloc[-1]}\n"
            system_prompt = "You are a medical assistant. Present sensor data clearly and professionally."
            prompt = f"User question: {question}\n\n{sensor_data_text}\n\nProvide a clear response."
            gpt_reply = gpt(text=prompt, model_name="gpt-3.5-turbo", system_prompt=system_prompt)
            return jsonify({"answer": gpt_reply})
        except Exception as e:
            return jsonify({"answer": f"Error: {str(e)}"})

    # Case: General conversation
    else:
        system_prompt = "You are a helpful medical assistant for a patient monitoring system."
        gpt_reply = gpt(text=question, model_name="gpt-3.5-turbo", system_prompt=system_prompt)
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

# ==================== Run Server ====================
if __name__ == '__main__':
    print("="*70)
    print("REMONI WEB APPLICATION SERVER")
    print("="*70)
    print(f"Raspberry Pi URL: {RASPBERRY_PI_URL}")
    print("="*70 + "\n")

    # Connect to Raspberry Pi
    threading.Thread(target=connect_to_raspberry_pi, daemon=True).start()
    threading.Thread(target=reconnect_loop, daemon=True).start()

    print("✓ Starting web server on http://0.0.0.0:5001")
    print("✓ Connecting to Raspberry Pi in background...\n")
    socketio.run(app, host='0.0.0.0', port=5001, debug=True)
