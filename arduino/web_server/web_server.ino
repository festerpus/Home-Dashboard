#include <WiFi.h>
#include <WebServer.h>


const char* ssid = "emmlyn";
const char* password = "hop634473";

WebServer server(80);


void setup() {

  Serial.begin(115200);


  // Connect to WiFi
  WiFi.begin(ssid, password);

  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }


  Serial.println();
  Serial.println("Connected!");

  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());


  // GET /
  server.on("/", HTTP_GET, []() {

    server.send(
      200,
      "text/plain",
      "Hello from the ESP32!"
    );

  });


  // Start HTTP server
  server.begin();

  Serial.println("Web server started");
}


void loop() {

  // Check for incoming HTTP requests
  server.handleClient();

}