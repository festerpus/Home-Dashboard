#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <time.h>
#include "secrets.h"


// ============================================================
// CONFIG
// ============================================================

const char* DEVICE_ID = "bench-esp32-01";

String SERVER_BASE_URL = String("http://") + SERVER_IP + ":" + SERVER_PORT;

String REGISTER_URL = SERVER_BASE_URL + "/sensors/register-local/";

String INGEST_URL = SERVER_BASE_URL + "/sensors/local-ingest/";


// BME280 I2C pins
const int SDA_PIN = 21;
const int SCL_PIN = 22;


// How often to take a reading
const unsigned long SAMPLE_INTERVAL_MS = 5000;

// How often to retry registration if Django is unavailable
const unsigned long REGISTER_RETRY_MS = 30000;


// ============================================================
// BME280
// ============================================================

Adafruit_BME280 bme;


// ============================================================
// READING BUFFER
// ============================================================

struct SensorReading {
    unsigned long capturedAtMillis;

    float temperature;
    float humidity;
    float pressure;
};


// Maximum number of readings held in RAM.
//
// At 30-second intervals:
// 120 readings = 1 hour.
const int BUFFER_SIZE = 120;

SensorReading readingBuffer[BUFFER_SIZE];

int bufferHead = 0;
int bufferTail = 0;
int bufferCount = 0;


// ============================================================
// STATE
// ============================================================

bool deviceRegistered = false;

unsigned long lastSampleTime = 0;
unsigned long lastRegisterAttempt = 0;


// ============================================================
// WIFI
// ============================================================

void connectWiFi() {

    if (WiFi.status() == WL_CONNECTED) {
        return;
    }

    Serial.print("Connecting to WiFi");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();

    // Don't block forever.
    while (
        WiFi.status() != WL_CONNECTED &&
        millis() - start < 10000
    ) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {

        Serial.println("WiFi connected");

        Serial.print("IP address: ");
        Serial.println(WiFi.localIP());

    } else {

        Serial.println("WiFi connection failed");
    }
}


// ============================================================
// TIME
// ============================================================

void configureTime() {

    /*
        Keep the ESP32 internally on UTC.

        timezone offset = 0
        DST offset      = 0
    */

    configTime(
        0,
        0,
        "pool.ntp.org",
        "time.cloudflare.com"
    );

    Serial.print("Waiting for NTP");

    unsigned long start = millis();

    while (
        time(nullptr) < 1000000000 &&
        millis() - start < 10000
    ) {
        delay(500);
        Serial.print(".");
    }

    Serial.println();

    if (time(nullptr) >= 1000000000) {
        Serial.println("Time synchronised");
    } else {
        Serial.println("NTP unavailable - readings will remain buffered");
    }
}


// ============================================================
// TIMESTAMP
// ============================================================

bool createTimestamp(
    unsigned long capturedAtMillis,
    char* output,
    size_t outputSize
) {

    time_t now = time(nullptr);

    // Assume anything before this is an unsynchronised clock.
    if (now < 1000000000) {
        return false;
    }

    /*
        The reading may have been captured while Django was offline.

        Work backwards from the current real UTC time using millis()
        to determine when the measurement was actually taken.
    */

    unsigned long elapsedMs =
        millis() - capturedAtMillis;

    time_t observedAt =
        now - (elapsedMs / 1000);

    struct tm timeInfo;

    gmtime_r(
        &observedAt,
        &timeInfo
    );

    strftime(
        output,
        outputSize,
        "%Y-%m-%dT%H:%M:%SZ",
        &timeInfo
    );

    return true;
}


// ============================================================
// BUFFER
// ============================================================

void bufferReading(SensorReading reading) {

    /*
        If the buffer fills completely, discard the oldest
        reading rather than stopping sensor collection.
    */

    if (bufferCount == BUFFER_SIZE) {

        Serial.println(
            "Buffer full - discarding oldest reading"
        );

        bufferTail =
            (bufferTail + 1) % BUFFER_SIZE;

        bufferCount--;
    }

    readingBuffer[bufferHead] = reading;

    bufferHead =
        (bufferHead + 1) % BUFFER_SIZE;

    bufferCount++;

    Serial.print("Buffered readings: ");
    Serial.println(bufferCount);
}


SensorReading* getOldestReading() {

    if (bufferCount == 0) {
        return nullptr;
    }

    return &readingBuffer[bufferTail];
}


void removeOldestReading() {

    if (bufferCount == 0) {
        return;
    }

    bufferTail =
        (bufferTail + 1) % BUFFER_SIZE;

    bufferCount--;
}


// ============================================================
// HTTP POST
// ============================================================

bool postJson(
    const char* url,
    const String& json
) {

    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }

    HTTPClient http;

    http.setTimeout(5000);

    if (!http.begin(url)) {
        Serial.println("Could not initialise HTTP request");
        return false;
    }

    http.addHeader(
        "Content-Type",
        "application/json"
    );

    http.addHeader(
        "X-API-Key",
        API_KEY
    );

    int responseCode =
        http.POST(json);

    String responseBody =
        http.getString();

    Serial.print("POST ");
    Serial.println(url);

    Serial.print("HTTP status: ");
    Serial.println(responseCode);

    Serial.print("Response: ");
    Serial.println(responseBody);

    http.end();

    return (
        responseCode >= 200 &&
        responseCode < 300
    );
}


// ============================================================
// DEVICE REGISTRATION
// ============================================================

bool registerDevice() {

    String payload;

    payload.reserve(512);

    payload += "{";

    payload += "\"device_id\":\"";
    payload += DEVICE_ID;
    payload += "\",";

    payload += "\"metrics\":{";

    payload += "\"temperature\":{";
    payload += "\"name\":\"Temperature\",";
    payload += "\"unit\":\"C\",";
    payload += "\"decimals\":2";
    payload += "},";

    payload += "\"humidity\":{";
    payload += "\"name\":\"Humidity\",";
    payload += "\"unit\":\"%\",";
    payload += "\"decimals\":2";
    payload += "},";

    payload += "\"pressure\":{";
    payload += "\"name\":\"Pressure\",";
    payload += "\"unit\":\"hPa\",";
    payload += "\"decimals\":2";
    payload += "}";

    payload += "},";

    payload += "\"metadata\":{";
    payload += "\"sensor\":\"BME280\",";
    payload += "\"connection\":\"I2C\",";
    payload += "\"firmware\":\"1.0\"";
    payload += "}";

    payload += "}";


    Serial.println("Registering device...");
    Serial.println(payload);

    bool success =
        postJson(
            REGISTER_URL,
            payload
        );

    if (success) {

        Serial.println(
            "Device registration successful"
        );

        deviceRegistered = true;

    } else {

        Serial.println(
            "Device registration failed"
        );
    }

    return success;
}


// ============================================================
// SENSOR SAMPLING
// ============================================================

void takeReading() {

    SensorReading reading;

    reading.capturedAtMillis =
        millis();

    reading.temperature =
        bme.readTemperature();

    reading.humidity =
        bme.readHumidity();

    /*
        Adafruit returns pressure in Pascals.

        Divide by 100 for hPa.
    */

    reading.pressure =
        bme.readPressure() / 100.0F;


    Serial.println();
    Serial.println("BME280 reading:");

    Serial.print("Temperature: ");
    Serial.print(reading.temperature);
    Serial.println(" C");

    Serial.print("Humidity: ");
    Serial.print(reading.humidity);
    Serial.println(" %");

    Serial.print("Pressure: ");
    Serial.print(reading.pressure);
    Serial.println(" hPa");


    bufferReading(reading);
}


// ============================================================
// INGEST
// ============================================================

bool sendReading(
    SensorReading& reading
) {

    char timestamp[25];

    if (
        !createTimestamp(
            reading.capturedAtMillis,
            timestamp,
            sizeof(timestamp)
        )
    ) {

        Serial.println(
            "Cannot send reading - UTC time unavailable"
        );

        return false;
    }


    String payload;

    payload.reserve(256);

    payload += "{";

    payload += "\"device_id\":\"";
    payload += DEVICE_ID;
    payload += "\",";

    payload += "\"timestamp\":\"";
    payload += timestamp;
    payload += "\",";

    payload += "\"readings\":{";

    payload += "\"temperature\":";
    payload += String(
        reading.temperature,
        2
    );
    payload += ",";

    payload += "\"humidity\":";
    payload += String(
        reading.humidity,
        2
    );
    payload += ",";

    payload += "\"pressure\":";
    payload += String(
        reading.pressure,
        2
    );

    payload += "}";

    payload += "}";


    Serial.println("Sending reading:");
    Serial.println(payload);


    return postJson(
        INGEST_URL,
        payload
    );
}


// ============================================================
// FLUSH BUFFER
// ============================================================

void flushBuffer() {

    if (!deviceRegistered) {
        return;
    }

    if (WiFi.status() != WL_CONNECTED) {
        return;
    }

    /*
        Send oldest readings first.

        This preserves chronological order when recovering from
        an outage.
    */

    while (bufferCount > 0) {

        SensorReading* reading =
            getOldestReading();

        if (reading == nullptr) {
            return;
        }

        if (sendReading(*reading)) {

            removeOldestReading();

            Serial.print(
                "Reading accepted. Remaining: "
            );

            Serial.println(bufferCount);

        } else {

            /*
                Stop here.

                Don't discard the reading, and don't hammer
                Django repeatedly if the server is unavailable.
            */

            Serial.println(
                "Upload failed - keeping reading in buffer"
            );

            return;
        }
    }
}


// ============================================================
// SETUP
// ============================================================

void setup() {

    Serial.begin(115200);

    delay(1000);

    Serial.println();
    Serial.println("==========================");
    Serial.println("ESP32 BME280 SENSOR");
    Serial.println("==========================");


    // --------------------------------------------------------
    // I2C
    // --------------------------------------------------------

    Wire.begin(
        SDA_PIN,
        SCL_PIN
    );


    // --------------------------------------------------------
    // BME280
    // --------------------------------------------------------

    if (!bme.begin(0x76)) {

        Serial.println(
            "BME280 not found at 0x76, trying 0x77..."
        );

        if (!bme.begin(0x77)) {

            Serial.println(
                "BME280 NOT FOUND"
            );

            while (true) {
                delay(1000);
            }
        }
    }

    Serial.println(
        "BME280 detected"
    );


    // --------------------------------------------------------
    // NETWORK
    // --------------------------------------------------------

    connectWiFi();

    if (WiFi.status() == WL_CONNECTED) {

        configureTime();

        registerDevice();
    }


    /*
        Take a reading immediately rather than waiting
        SAMPLE_INTERVAL_MS after boot.
    */

    takeReading();

    lastSampleTime =
        millis();
}


// ============================================================
// LOOP
// ============================================================

void loop() {

    // --------------------------------------------------------
    // Keep WiFi alive
    // --------------------------------------------------------

    if (WiFi.status() != WL_CONNECTED) {

        connectWiFi();

        if (WiFi.status() == WL_CONNECTED) {

            /*
                Calling configTime again is harmless and gives us
                an opportunity to acquire UTC after an outage.
            */

            configureTime();
        }
    }


    // --------------------------------------------------------
    // Device registration
    // --------------------------------------------------------

    if (
        !deviceRegistered &&
        millis() - lastRegisterAttempt >= REGISTER_RETRY_MS
    ) {

        lastRegisterAttempt =
            millis();

        registerDevice();
    }


    // --------------------------------------------------------
    // Sensor sampling
    // --------------------------------------------------------

    if (
        millis() - lastSampleTime >= SAMPLE_INTERVAL_MS
    ) {

        lastSampleTime =
            millis();

        takeReading();
    }


    // --------------------------------------------------------
    // Upload anything waiting
    // --------------------------------------------------------

    flushBuffer();


    /*
        There's no reason to spin thousands of times per second.
    */

    delay(100);
}