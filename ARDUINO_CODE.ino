#include <Servo.h>

const int pinMQ7 = A0;   
const int pinMQ6 = A1;   
const int buzzer = 6;    
const int servoPin = 9;  
const int relayPin = 10; 

Servo myServo;

// متغيرات المعايرة
float smoothCO = 0;      // القيمة المنعمة لغاز CO
float smoothLPG = 0;     // القيمة المنعمة لغاز LPG
const float alpha = 0.1; // معامل التنعيم (كلما قل زادت الدقة وقل التأثر بالذبذبات)
const int gasThreshold = 200; 

void setup() {
  Serial.begin(9600);
  pinMode(buzzer, OUTPUT);
  pinMode(relayPin, OUTPUT);
  myServo.attach(servoPin);
  
  // قراءة أولية لتصفير الحساس
  smoothCO = analogRead(pinMQ7);
  smoothLPG = analogRead(pinMQ6);
  
  deactivateEmergency();
  delay(2000); 
}

void loop() {
  // 1. قراءة الحساسات مع تطبيق فتلرة رقمية (Digital Filtering)
  int rawCO = analogRead(pinMQ7);
  int rawLPG = analogRead(pinMQ6);

  // معادلة التنعيم: تجعل القراءة مستقرة ولا تقفز فجأة بسبب الكهرباء
  smoothCO = (alpha * rawCO) + (1.0 - alpha) * smoothCO;
  smoothLPG = (alpha * rawLPG) + (1.0 - alpha) * smoothLPG;

  // 2. إرسال القيمة الأكبر للبايثون
  int currentGasVal = (smoothCO > smoothLPG) ? (int)smoothCO : (int)smoothLPG;
  Serial.println(currentGasVal);

  // 3. استقبال أوامر البايثون
  bool pythonAlert = false;
  if (Serial.available() > 0) {
    char command = Serial.read();
    if (command == '1') pythonAlert = true;
    else if (command == '0') pythonAlert = false;
  }

  // 4. منطق الطوارئ
  if (currentGasVal > gasThreshold || pythonAlert) {
    activateEmergency();
  } else {
    deactivateEmergency();
  }

  delay(50); // سرعة تحديث عالية مع استقرار القراءة
}

void activateEmergency() {
  digitalWrite(buzzer, HIGH);   
  digitalWrite(relayPin, HIGH); 
  myServo.write(90);            
}

void deactivateEmergency() {
  digitalWrite(buzzer, LOW);    
  digitalWrite(relayPin, LOW);  
  myServo.write(0);             
}