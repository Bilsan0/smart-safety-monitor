import urllib.request
import numpy as np
import requests
import serial
import time
import urllib3
from dotenv import load_dotenv

# Suppress SSL warnings for Telegram API requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
ARDUINO_PORT = os.getenv('ARDUINO_PORT', 'COM4')
GAS_THRESHOLD = int(os.getenv('GAS_THRESHOLD', 200))

MODEL_FILE = "face_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

if not os.path.exists(MODEL_FILE):
    print("Downloading MediaPipe face landmarker model...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_FILE)

# --- 2. Helper Functions ---
def send_telegram(message):
    """Send an emergency alert message via Telegram bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload, verify=False, timeout=5)
        print("Alert sent via Telegram.")
    except:
        print("Failed to connect to Telegram.")

def get_ear(landmarks, eye_points, w, h):
    """
    Calculate the Eye Aspect Ratio (EAR) for a given eye.
    EAR = vertical distance / horizontal distance between eye landmarks.
    A low EAR value indicates the eye is closed.
    """
    coords = [np.array([landmarks[p].x * w, landmarks[p].y * h]) for p in eye_points]
    v_dist = np.linalg.norm(coords[2] - coords[3])
    h_dist = np.linalg.norm(coords[0] - coords[1])
    return v_dist / h_dist

# --- 3. Hardware Initialization ---
try:
    arduino = serial.Serial(ARDUINO_PORT, 9600, timeout=0.01)
    time.sleep(2)  # Wait for Arduino to reset after serial connection
    print(f"Arduino connected on {ARDUINO_PORT}")
except:
    print(f"Warning: Could not connect to Arduino on {ARDUINO_PORT}. Running in camera-only mode.")
    arduino = None

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_FILE),
    running_mode=VisionRunningMode.VIDEO,
    num_faces=1
)

# --- 4. Main Processing Loop ---
cap = cv2.VideoCapture(0)
last_alert_time = 0
current_gas_val = 0

with FaceLandmarker.create_from_options(options) as landmarker:
    print("System running. Press Q to quit.")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        img_h, img_w, _ = frame.shape
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        timestamp_ms = int(cv2.getTickCount() / cv2.getTickFrequency() * 1000)
        result = landmarker.detect_for_video(mp_image, timestamp_ms)

        # A) Read gas sensor data from Arduino via Serial
        if arduino and arduino.in_waiting > 0:
            try:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    current_gas_val = float(line)
            except:
                pass

        # B) Analyze eye state using Eye Aspect Ratio (EAR)
        eyes_closed = False
        if result.face_landmarks:
            face_landmarks = result.face_landmarks[0]
            # Left eye landmark indices: outer, inner, top, bottom
            ear_l = get_ear(face_landmarks, [33, 133, 159, 145], img_w, img_h)
            # Right eye landmark indices: outer, inner, top, bottom
            ear_r = get_ear(face_landmarks, [362, 263, 386, 374], img_w, img_h)
            if (ear_l + ear_r) / 2 < 0.21:
                eyes_closed = True

        # C) Alert logic and Arduino control
        status_text = "Safe"
        color = (0, 255, 0)  # Green

        # Critical condition: high gas AND closed eyes (possible unconsciousness)
        if current_gas_val > GAS_THRESHOLD and eyes_closed:
            status_text = "CRITICAL: GAS + CLOSED EYES"
            color = (0, 0, 255)  # Red

            # Send emergency command to Arduino (activates buzzer + fan + servo)
            if arduino:
                arduino.write(b'1')

            # Send Telegram alert with 20-second cooldown to avoid spam
            if (time.time() - last_alert_time > 20):
                msg = (f"*EMERGENCY ALERT*\n\n"
                       f"Gas Level: `{current_gas_val}`\n"
                       f"Status: Eyes closed — possible unconsciousness detected")
                send_telegram(msg)
                last_alert_time = time.time()

        else:
            # Safe or partial warning: send stop command to Arduino
            if arduino:
                arduino.write(b'0')

            if current_gas_val > GAS_THRESHOLD:
                status_text = "Warning: Gas Detected"
                color = (0, 165, 255)  # Orange
            else:
                status_text = "System Normal"
                color = (0, 255, 0)  # Green

        # D) Display status overlay on camera feed
        cv2.putText(frame, f"Status: {status_text}", (20, 50), 1, 1.5, color, 2)
        cv2.putText(frame, f"Gas: {current_gas_val}", (20, 100), 1, 1.2, color, 2)

        cv2.imshow('Safety Monitoring System', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

# Cleanup: send stop command and release resources
if arduino:
    arduino.write(b'0')
    arduino.close()
cap.release()
cv2.destroyAllWindows()
