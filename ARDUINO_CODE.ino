#include <Servo.h>

// Pin definitions
const int pinMQ7 = A0;    // MQ-7 Carbon Monoxide (CO) sensor
const int pinMQ6 = A1;    // MQ-6 LPG / Gas sensor
const int buzzer = 6;     // Buzzer for audio alert
const int servoPin = 9;   // Servo motor for visual indicator
const int relayPin = 10;  // Relay controlling the DC ventilation fan

Servo myServo;

// Smoothing filter variables (Exponential Moving Average)
float smoothCO = 0;       // Smoothed CO sensor reading
float smoothLPG = 0;      // Smoothed LPG sensor reading
const float alpha = 0.1;  // Smoothing factor — lower = more stable, slower response
const int gasThreshold = 200;  // Analog threshold to trigger emergency

void setup() {
  Serial.begin(9600);
  pinMode(buzzer, OUTPUT);
  pinMode(relayPin, OUTPUT);
  myServo.attach(servoPin);

  // Initial sensor readings to seed the smoothing filter
  smoothCO = analogRead(pinMQ7);
  smoothLPG = analogRead(pinMQ6);

  deactivateEmergency();
  delay(2000);  // Warm-up time for gas sensors
}

void loop() {
  // 1. Read raw sensor values and apply Exponential Moving Average filter
  int rawCO = analogRead(pinMQ7);
  int rawLPG = analogRead(pinMQ6);

  // Smoothing formula: reduces noise and prevents sudden spikes from electrical interference
  smoothCO  = (alpha * rawCO)  + (1.0 - alpha) * smoothCO;
  smoothLPG = (alpha * rawLPG) + (1.0 - alpha) * smoothLPG;

  // 2. Send the higher of the two readings to Python via Serial
  int currentGasVal = (smoothCO > smoothLPG) ? (int)smoothCO : (int)smoothLPG;
  Serial.println(currentGasVal);

  // 3. Receive commands from Python
  bool pythonAlert = false;
  if (Serial.available() > 0) {
    char command = Serial.read();
    if (command == '1') pythonAlert = true;   // Python detected critical condition
    else if (command == '0') pythonAlert = false;  // Python cleared the alert
  }

  // 4. Emergency logic — triggered by gas threshold OR Python command
  if (currentGasVal > gasThreshold || pythonAlert) {
    activateEmergency();
  } else {
    deactivateEmergency();
  }

  delay(50);  // 20Hz update rate — fast enough for real-time response
}

void activateEmergency() {
  digitalWrite(buzzer, HIGH);    // Sound the alarm
  digitalWrite(relayPin, HIGH);  // Turn on ventilation fan via relay
  myServo.write(90);             // Rotate servo to alert position
}

void deactivateEmergency() {
  digitalWrite(buzzer, LOW);     // Silence the alarm
  digitalWrite(relayPin, LOW);   // Turn off ventilation fan
  myServo.write(0);              // Return servo to resting position
}
