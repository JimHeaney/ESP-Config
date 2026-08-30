/*
  ==============================================================================
  ESPConfig Minimal Example: Basic Wi-Fi Credentials & Connection
  ==============================================================================
*/

#include <Arduino.h>
#include <WiFi.h>
#include "ESPConfig.h"

ESPConfig config;

String targetSSID = "";
String targetPassword = "";

void handleSSIDInput(String ssid);
void handlePasswordInput(String pass);
void handleConnect(bool pressed);

void setup() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  // Initialize without a system password for simplified access
  config.begin();

  // Status & Information displays
  config.addInformation("WiFi", "status", "Connection Status", "DISCONNECTED", "Network");
  config.addInformation("WiFi", "ip", "IP Address", "0.0.0.0", "Network");

  // Credential input questions
  config.addStringQuestion(
    "WiFi",
    "ssid",
    "Credentials",
    "Network Name (SSID)",
    "",
    32,
    handleSSIDInput);

  config.addStringQuestion(
    "WiFi",
    "password",
    "Credentials",
    "Wi-Fi Password",
    "",
    64,
    handlePasswordInput);

  // Connect command button
  config.addButtonCommand(
    "WiFi",
    "connect",
    "Actions",
    "Connect to Network",
    handleConnect);
}

void loop() {
  // ESPConfig manages synchronization asynchronously in its FreeRTOS background task.
}

// -----------------------------------------------------------------------------
// CALLBACK HANDLERS
// -----------------------------------------------------------------------------

void handleSSIDInput(String ssid) {
  targetSSID = ssid;
  config.updateQuestion("WiFi", "ssid", targetSSID, "[good] SSID updated.");
}

void handlePasswordInput(String pass) {
  targetPassword = pass;
  config.updateQuestion("WiFi", "password", "********", "[good] Password saved.");
}

void handleConnect(bool pressed) {
  if (!pressed) return;

  if (targetSSID.length() == 0) {
    config.updateCommand("WiFi", "connect", "[bad] Please enter an SSID before connecting.");
    return;
  }

  // Update status UI to connecting state
  config.updateCommand("WiFi", "connect", "[time] Connecting to " + targetSSID + "...");
  config.updateInformation("WiFi", "status", "CONNECTING");
  config.updateInformation("WiFi", "ip", "0.0.0.0");

  WiFi.begin(targetSSID.c_str(), targetPassword.c_str());

  int timeout = 20;  // 10-second timeout window
  while (WiFi.status() != WL_CONNECTED && timeout > 0) {
    delay(500);
    timeout--;
  }

  if (WiFi.status() == WL_CONNECTED) {
    config.updateCommand("WiFi", "connect", "[good] Connected to " + targetSSID);
    config.updateInformation("WiFi", "status", "CONNECTED");
    config.updateInformation("WiFi", "ip", WiFi.localIP().toString());
  } else {
    config.updateCommand("WiFi", "connect", "[bad] Failed to connect to " + targetSSID);
    config.updateInformation("WiFi", "status", "DISCONNECTED");
    config.updateInformation("WiFi", "ip", "0.0.0.0");
  }
}