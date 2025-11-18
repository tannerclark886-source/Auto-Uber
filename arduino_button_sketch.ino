// Auto Uber API - Grove Alcohol Sensor sketch with LCD display
// Reads analog values from a Grove Alcohol Sensor (A0), estimates a crude BAC
// value (demo only), prints standardized lines to serial ("BAC:<value>") and
// displays the current BAC on a Grove RGB LCD. When BAC crosses the threshold
// it also emits a "START" line and lights an LED for 7 seconds so the PC
// listener can trigger the API and the user sees a visual indication.

#include <Wire.h>
#include "rgb_lcd.h"

const int GROVE_ALCOHOL_PIN = A0;        // analog input (Grove Alcohol Sensor)
const int LED_PIN = 4;         // LED to indicate high BAC
const float BAC_THRESHOLD = 0.08; // threshold to signal START

const unsigned long SAMPLE_INTERVAL_MS = 1000;
const unsigned long LED_DURATION_MS = 7000; // light LED for 7 seconds

rgb_lcd lcd;

const int colorR = 255;
const int colorG = 0;
const int colorB = 0;

bool was_above = false;            // track rising edge to send START once
unsigned long led_on_until = 0;    // millis() timestamp when LED should turn off

void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Initialize the Grove RGB LCD (16x2)
  // Add a small delay before initializing I2C devices
  delay(500);
  
  lcd.begin(16, 2);
  delay(100);
  
  // Set backlight color (R, G, B)
  lcd.setRGB(0, 128, 255);  // Light blue
  delay(100);
  
  lcd.clear();
  delay(50);
  
  lcd.setCursor(0, 0);
  lcd.print("Grove Alcohol");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");
  
  delay(2000);  // Show initialization message for 2 seconds
  lcd.clear();

  Serial.println("Grove Alcohol monitor ready");
}

// crude mapping from analog value to BAC for demo purposes only.
// The Grove Alcohol Sensor behaves differently from the MQ-3; use the
// `bac_calibration.json` file (with `scale` and `offset`) to provide a
// proper conversion for accurate readings. The default mapping below is
// legacy/demo-only and may not reflect real BAC values.
float estimate_bac(int analogValue) {
  // Default legacy mapping: map analog 0..1023 to 0..0.5 (demo only)
  float mapped = (float)analogValue * (0.5 / 1023.0);
  return mapped;
}

void show_on_lcd(float bac, int analogValue) {
  // Clear the entire display once per update
  lcd.clear();
  
  // First row: BAC value (format: "BAC:0.082")
  lcd.setCursor(0, 0);
  lcd.print("BAC:");
  if (bac < 0.1) lcd.print("0");  // padding for single digit
  lcd.print(bac, 3);

  // Second row: countdown timer or analog reading
  lcd.setCursor(0, 1);
  if (millis() < led_on_until) {
    // Show countdown during active window
    unsigned long time_remaining_ms = led_on_until - millis();
    unsigned long seconds_remaining = (time_remaining_ms + 999) / 1000; // round up
    if (seconds_remaining > 9) seconds_remaining = 9;  // cap at 9 for display
    lcd.print("Blow: ");
    lcd.print(seconds_remaining);
    lcd.print("s");
  } else {
    // Show analog value when not in countdown
    lcd.print("A:");
    if (analogValue < 100) lcd.print(" ");  // padding
    if (analogValue < 10) lcd.print(" ");
    lcd.print(analogValue);
  }
}

void loop() {
  int sensorValue = analogRead(GROVE_ALCOHOL_PIN);
  float bac = estimate_bac(sensorValue);

  // Print a machine-friendly line: "BAC:0.082"
  Serial.print("BAC:");
  Serial.println(bac, 3);

  // Print human friendly info (not required by listener)
  Serial.print("Analog:"); Serial.print(sensorValue);
  Serial.print("  Voltage:"); Serial.print(sensorValue * (5.0 / 1023.0), 2);
  Serial.print(" V  Estimated BAC:"); Serial.print(bac, 3);
  Serial.println();

  // Display on LCD
  show_on_lcd(bac, sensorValue);

  // Handle threshold crossing: send START on rising edge and light LED for 7s
  if (bac >= BAC_THRESHOLD) {
    if (!was_above) {
      // rising edge
      Serial.println("START");
      was_above = true;
      led_on_until = millis() + LED_DURATION_MS;
    }
    
    // LED blink pattern during countdown (on for 500ms, off for 500ms)
    if (millis() < led_on_until) {
      unsigned long phase = (millis() % 1000) / 500; // 0 or 1 (500ms each)
      digitalWrite(LED_PIN, phase == 0 ? HIGH : LOW);
    }
  } else {
    was_above = false;
  }

  // Turn off LED when duration elapsed
  if (millis() >= led_on_until) {
    digitalWrite(LED_PIN, LOW);
  }

  delay(SAMPLE_INTERVAL_MS);
}
