#include <Wire.h>

#define SDA_PIN 21
#define SCL_PIN 22

void setup() {
    Serial.begin(115200);
    delay(1000);

    Serial.println();
    Serial.println("ESP32 I2C Scanner");
    Serial.println("=================");

    Wire.begin(SDA_PIN, SCL_PIN);
}

void loop() {

    byte error;
    int devicesFound = 0;

    Serial.println("Scanning I2C bus...");

    for (byte address = 1; address < 127; address++) {

        Wire.beginTransmission(address);
        error = Wire.endTransmission();

        if (error == 0) {

            Serial.print("Found device at 0x");

            if (address < 16) {
                Serial.print("0");
            }

            Serial.println(address, HEX);

            devicesFound++;
        }
    }

    if (devicesFound == 0) {
        Serial.println("No I2C devices found.");
    } else {
        Serial.print("Total devices: ");
        Serial.println(devicesFound);
    }

    Serial.println();
    delay(3000);
}