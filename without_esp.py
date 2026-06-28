import cv2
import mediapipe as mp
import os
import urllib.request
import numpy as np
import requests
import serial
import time
import urllib3
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. الإعدادات الأساسية (من ملف .env) ---
BOT_TOKEN     = os.getenv('BOT_TOKEN')
CHAT_ID       = os.getenv('CHAT_ID')
ARDUINO_PORT  = os.getenv('ARDUINO_PORT', 'COM5')
GAS_THRESHOLD = int(os.getenv('GAS_THRESHOLD', '300'))
EAR_THRESHOLD = 0.21
ALERT_INTERVAL = 20

MODEL_FILE = "face_landmarker.task"
MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

if not os.path.exists(MODEL_FILE):
    print("⏳ Downloading AI model...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_FILE)
    print("✅ Model downloaded successfully")

# --- 2. الدوال المساعدة ---
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload, verify=False, timeout=5)
        print("📢 Telegram alert sent")
    except:
        print("❌ Failed to send Telegram alert")

def get_ear(landmarks, eye_points, w, h):
    coords = [np.array([landmarks[p].x * w, landmarks[p].y * h]) for p in eye_points]
    v_dist = np.linalg.norm(coords[2] - coords[3])
    h_dist = np.linalg.norm(coords[0] - coords[1])
    return v_dist / h_dist

# --- 3. تهيئة الأردوينو ---
try:
    arduino = serial.Serial(ARDUINO_PORT, 9600, timeout=0.01)
    time.sleep(2)
    print(f"✅ Arduino connected on {ARDUINO_PORT}")
except Exception as e:
    print(f"⚠️ Arduino connection failed on {ARDUINO_PORT}: {e}")
    arduino = None

# --- 4. تهيئة MediaPipe ---
BaseOptions           = mp.tasks.BaseOptions
FaceLandmarker        = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode     = mp.tasks.vision.RunningMode

options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_FILE),
    running_mode=VisionRunningMode.VIDEO,
    num_faces=1
)

# --- 5. الحلقة الرئيسية ---
cap = cv2.VideoCapture(0)
last_alert_time = 0
current_gas_val = 0

with FaceLandmarker.create_from_options(options) as landmarker:
    print("🚀 System running... Press Q to quit")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        img_h, img_w, _ = frame.shape
        mp_image     = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
        result       = landmarker.detect_for_video(mp_image, timestamp_ms)

        # أ) قراءة الغاز
        if arduino and arduino.in_waiting > 0:
            try:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    current_gas_val = float(line)
            except:
                pass

        # ب) تحليل العين
        eyes_closed = False
        if result.face_landmarks:
            face_lm = result.face_landmarks[0]
            ear_l   = get_ear(face_lm, [33, 133, 159, 145], img_w, img_h)
            ear_r   = get_ear(face_lm, [362, 263, 386, 374], img_w, img_h)
            if (ear_l + ear_r) / 2 < EAR_THRESHOLD:
                eyes_closed = True

        # ج) منطق التنبيه
        status_text = "System Normal"
        color       = (0, 255, 0)

        if current_gas_val > GAS_THRESHOLD and eyes_closed:
            status_text = "CRITICAL: GAS + CLOSED EYES"
            color       = (0, 0, 255)
            if arduino:
                arduino.write(b'1')
            if time.time() - last_alert_time > ALERT_INTERVAL:
                send_telegram(
                    f"🚨 *EMERGENCY ALERT*\n\n"
                    f"📊 Gas Level: `{current_gas_val}`\n"
                    f"⚠️ Status: Eyes closed (suspected unconsciousness)"
                )
                last_alert_time = time.time()

        elif current_gas_val > GAS_THRESHOLD:
            status_text = "WARNING: Gas Detected"
            color       = (0, 165, 255)
            if arduino:
                arduino.write(b'0')

        elif eyes_closed:
            status_text = "WARNING: Eyes Closed"
            color       = (0, 200, 255)
            if arduino:
                arduino.write(b'0')

        else:
            if arduino:
                arduino.write(b'0')

        # د) العرض على الشاشة
        cv2.putText(frame, f"Status : {status_text}",       (20, 50),  1, 1.4, color, 2)
        cv2.putText(frame, f"Gas    : {int(current_gas_val)}",(20, 90),  1, 1.2, color, 2)
        cv2.putText(frame, f"Eyes   : {'CLOSED' if eyes_closed else 'Open'}", (20, 130), 1, 1.2, color, 2)
        cv2.putText(frame, f"Threshold: {GAS_THRESHOLD}",   (20, 170), 1, 1.0, (200,200,200), 1)

        cv2.imshow('Smart Safety Monitor', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# --- إغلاق نظيف ---
if arduino:
    arduino.write(b'0')
    arduino.close()
cap.release()
cv2.destroyAllWindows()
print("✅ System closed safely")
