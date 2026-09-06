#include <WiFi.h>
#include <WebServer.h>
#include <LedControl.h>

// ESP32 pins:
//
// DIN → GPIO 23
// CLK → GPIO 18
// CS  → GPIO 17
//
// Four MAX7219 chips on the 32x8 board

// --------------------------------------------------
// FONT
// 5 columns × 7 pixels
// --------------------------------------------------

const byte FONT[][5] = {

  {B01111110, B00010001, B00010001, B00010001, B01111110}, // A
  {B01111111, B01001001, B01001001, B01001001, B00110110}, // B
  {B00111110, B01000001, B01000001, B01000001, B00100010}, // C
  {B01111111, B01000001, B01000001, B00100010, B00011100}, // D
  {B01111111, B01001001, B01001001, B01001001, B01000001}, // E
  {B01111111, B00001001, B00001001, B00001001, B00000001}, // F
  {B00111110, B01000001, B01001001, B01001001, B01111010}, // G
  {B01111111, B00001000, B00001000, B00001000, B01111111}, // H
  {B00000000, B01000001, B01111111, B01000001, B00000000}, // I
  {B00100000, B01000000, B01000001, B00111111, B00000001}, // J
  {B01111111, B00001000, B00010100, B00100010, B01000001}, // K
  {B01111111, B01000000, B01000000, B01000000, B01000000}, // L
  {B01111111, B00000010, B00000100, B00000010, B01111111}, // M
  {B01111111, B00000100, B00001000, B00010000, B01111111}, // N
  {B00111110, B01000001, B01000001, B01000001, B00111110}, // O
  {B01111111, B00001001, B00001001, B00001001, B00000110}, // P
  {B00111110, B01000001, B01010001, B00100001, B01011110}, // Q
  {B01111111, B00001001, B00011001, B00101001, B01000110}, // R
  {B01000110, B01001001, B01001001, B01001001, B00110001}, // S
  {B00000001, B00000001, B01111111, B00000001, B00000001}, // T
  {B00111111, B01000000, B01000000, B01000000, B00111111}, // U
  {B00011111, B00100000, B01000000, B00100000, B00011111}, // V
  {B01111111, B00100000, B00010000, B00100000, B01111111}, // W
  {B01100011, B00010100, B00001000, B00010100, B01100011}, // X
  {B00000111, B00001000, B01110000, B00001000, B00000111}, // Y
  {B01100001, B01010001, B01001001, B01000101, B01000011}  // Z
};

// initialise matrix
LedControl matrix = LedControl(23, 18, 5, 4);

// --------------------------------------------------
// Set brightness across all four MAX7219s
// --------------------------------------------------

void setBrightness(int level) {

  level = constrain(level, 0, 15);

  for (int i = 0; i < 4; i++) {
    matrix.setIntensity(i, level);
  }
}


// --------------------------------------------------
// Write a complete vertical column
// --------------------------------------------------

void setDisplayColumn(int x, byte data) {

  if (x < 0 || x >= 32) {
    return;
  }

  int device = x / 8;

  // Your particular module is horizontally reversed
  int col = 7 - (x % 8);

  matrix.setColumn(device, col, data);
}


// --------------------------------------------------
// Scroll text
// --------------------------------------------------

void scrollMessage(const char* message) {

  int length = strlen(message);

  // 5 pixels for character + 1 blank
  int messageWidth = length * 6;


  // Start message just beyond right edge
  for (int offset = 32; offset > -messageWidth; offset--) {

    for (int x = 0; x < 32; x++) {

      byte displayColumn = 0;

      int messageX = x - offset;


      // Are we currently inside the message?
      if (messageX >= 0 && messageX < messageWidth) {

        int charIndex = messageX / 6;
        int charColumn = messageX % 6;


        // Sixth column is character spacing
        if (charColumn < 5) {

          char c = message[charIndex];


          // lowercase → uppercase
          if (c >= 'a' && c <= 'z') {
            c -= 32;
          }


          // A-Z only for now
          if (c >= 'A' && c <= 'Z') {

            int fontIndex = c - 'A';

            displayColumn =
              FONT[fontIndex][charColumn];
          }
        }
      }


      setDisplayColumn(x, displayColumn);
    }


    // Scroll speed
    delay(40);
  }
}


// --------------------------------------------------
// SETUP
// --------------------------------------------------

const char* ssid = "emmlyn";
const char* password = "hop634473";

WebServer server(80);

// initialise var to hold message
String readOut = "";

void setup() {

  // Opening serial port for write
  Serial.begin(115200); // 115200 is default for ESP32

  // Resetting each quadrant of the matrix display
  for (int i = 0; i < 4; i++) {
    // Wake quadrant & clear display
    matrix.shutdown(i, false);
    matrix.clearDisplay(i);
  }

  // 0-15 - 1 is fine, 15 is aids
  setBrightness(1); // Brightnes of matrix screen

  // Connecting wifi
  WiFi.begin(ssid, password);

  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("Connected!");
  Serial.print("Device IP: ");
  Serial.println(WiFi.localIP());

}


// --------------------------------------------------
// LOOP
// --------------------------------------------------

void loop() {

  // Check whether PC/server has sent a messaage
  if (Serial.available()) {
    // if it has parse message and assign to readOut
    String message = Serial.readStringUntil('\n');
    message.trim();

    Serial.print("RECEIVED: ");
    Serial.println(message);

    readOut = message;
  }

  // Scroll readOut on matrix screen then wait 500ms
  scrollMessage(readOut.c_str());
  delay(500);
}