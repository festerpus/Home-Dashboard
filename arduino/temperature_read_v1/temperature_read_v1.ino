#include <math.h>

// ============================================================
// THERMISTOR
// ============================================================

const int THERMISTOR_PIN = A0;

// Your measured fixed resistor
const float R_FIXED = 100000;

// Thermistor characteristics
const float R0 = 100000.0;     // 100kΩ at 25°C
const float BETA = 3950.0;
const float T0 = 25.0 + 273.15;


// ============================================================
// 4-DIGIT 7-SEGMENT DISPLAY
// Common Anode
// ============================================================

// Segments:
// A = D8
// B = D9
// C = D10
// D = D11
// E = D12
// F = D13
// G = D6
// DP = D5

const byte segmentPins[7] = {
  8,   // A
  9,   // B
  10,  // C
  11,  // D
  12,  // E
  13,  // F
  6    // G
};

const byte dpPin = 5;


// Digit common-anode pins:
//
// Digit 1 = D7
// Digit 2 = A1
// Digit 3 = A2
// Digit 4 = A3

const byte digitPins[4] = {
  7,
  A1,
  A2,
  A3
};


// Digit lookup table:
//
// A B C D E F G
const byte digits[10][7] = {
  {1,1,1,1,1,1,0}, // 0
  {0,1,1,0,0,0,0}, // 1
  {1,1,0,1,1,0,1}, // 2
  {1,1,1,1,0,0,1}, // 3
  {0,1,1,0,0,1,1}, // 4
  {1,0,1,1,0,1,1}, // 5
  {1,0,1,1,1,1,1}, // 6
  {1,1,1,0,0,0,0}, // 7
  {1,1,1,1,1,1,1}, // 8
  {1,1,1,1,0,1,1}  // 9
};


// ============================================================
// SENSOR VALUES
// ============================================================

int raw = 0;
float resistance = 0;
float temperatureC = 0;

unsigned long lastMeasurement = 0;


// ============================================================
// SETUP
// ============================================================

void setup() {

  Serial.begin(9600);

  // Segment outputs
  for (int i = 0; i < 7; i++) {
    pinMode(segmentPins[i], OUTPUT);
    digitalWrite(segmentPins[i], HIGH); // OFF - common anode
  }

  pinMode(dpPin, OUTPUT);
  digitalWrite(dpPin, HIGH); // DP off


  // Digit outputs
  for (int i = 0; i < 4; i++) {
    pinMode(digitPins[i], OUTPUT);
    digitalWrite(digitPins[i], LOW); // digit off
  }

  readTemperature();
}


// ============================================================
// MAIN LOOP
// ============================================================

void loop() {

  // Take a fresh temperature measurement every 500ms
  if (millis() - lastMeasurement >= 500) {
    lastMeasurement = millis();
    readTemperature();
  }


  // Continuously refresh display
  displayTemperature(temperatureC);


  // Check whether PC/server has requested data
  if (Serial.available()) {

    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "READ") {

      // Take a fresh reading when requested
      readTemperature();

      sendReading();
    }
  }
}


// ============================================================
// READ THERMISTOR
// ============================================================

void readTemperature() {

  raw = analogRead(THERMISTOR_PIN);

  // Avoid division by zero
  if (raw <= 0) {
    return;
  }


  /*
      Circuit:

      5V
       │
      [THERMISTOR]
       │
       ├──── A0
       │
      [9.2kΩ]
       │
      GND

      Therefore:

      Rtherm = Rfixed * (1023 / ADC - 1)
  */

  resistance = R_FIXED * (1023.0 / raw - 1.0);


  /*
      Beta equation:

      1/T =
          1/T0
          +
          ln(R/R0) / Beta

      Result initially in Kelvin.
  */

  float tempKelvin =
    1.0 /
    (
      (1.0 / T0)
      +
      (log(resistance / R0) / BETA)
    );

  temperatureC = tempKelvin - 273.15;
}


// ============================================================
// SERIAL RESPONSE
// ============================================================

void sendReading() {

  Serial.print("{\"device_id\":\"bench-arduino-01\"");

  Serial.print(",\"temperature_c\":");
  Serial.print(temperatureC, 2);

  Serial.print(",\"thermistor_ohms\":");
  Serial.print(resistance, 2);

  Serial.print(",\"adc\":");
  Serial.print(raw);

  Serial.println("}");
}


// ============================================================
// DISPLAY TEMPERATURE
// ============================================================

void displayTemperature(float temp) {

  // Example:
  //
  // 20.8°C
  //
  // temp * 10 = 208

  int temp10 = round(temp * 10);

  int tens    = (temp10 / 100) % 10;
  int ones    = (temp10 / 10) % 10;
  int decimal = temp10 % 10;


  // Example:
  //
  // [2] [0.] [8] [ ]
  //

  showDigit(0, tens, false);
  showDigit(1, ones, true);
  showDigit(2, decimal, false);

  blankDigit(3);
}


// ============================================================
// SHOW ONE DIGIT
// ============================================================

void showDigit(byte position, byte number, bool decimalPoint) {

  // Turn ALL digits off first
  for (int i = 0; i < 4; i++) {
    digitalWrite(digitPins[i], LOW);
  }


  // Set segments
  for (int segment = 0; segment < 7; segment++) {

    /*
       Lookup table:
         1 = segment should be ON

       But common-anode means:
         LOW  = ON
         HIGH = OFF
    */

    if (digits[number][segment]) {
      digitalWrite(segmentPins[segment], LOW);
    }
    else {
      digitalWrite(segmentPins[segment], HIGH);
    }
  }


  // Decimal point
  digitalWrite(
    dpPin,
    decimalPoint ? LOW : HIGH
  );


  // Enable requested digit
  digitalWrite(digitPins[position], HIGH);

  // Leave it visible briefly
  delay(2);

  // Turn digit off again
  digitalWrite(digitPins[position], LOW);
}


// ============================================================
// BLANK DIGIT
// ============================================================

void blankDigit(byte position) {

  // All digits off
  for (int i = 0; i < 4; i++) {
    digitalWrite(digitPins[i], LOW);
  }

  // All segments off
  for (int i = 0; i < 7; i++) {
    digitalWrite(segmentPins[i], HIGH);
  }

  digitalWrite(dpPin, HIGH);

  delay(2);
}