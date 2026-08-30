/*
  ===============================================================================
  ESPConfig Advanced Example: WiFi Configurator & Diagnostics
  ===============================================================================
*/

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "ESPConfig.h"

ESPConfig config;

String targetSSID = "";
String targetPassword = "";
int pingAttempts = 3;
bool isScanningWiFi = false;  // State flag for asynchronous Wi-Fi scan

void handleNetworkSelect(String selectedSSID);
void handlePasswordInput(String pass);
void handlePingCountChange(String countVal);
void handleScanNetworks(bool pressed);
void handleConnectWiFi(bool pressed);
void handleTestPing(bool pressed);
void updateWiFiStatusInformation();
void checkWiFiScanResults();

void setup() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  config.begin("admin123", "The password is 'admin123'");

  config.addInformation("WiFi", "mac", "MAC Address", WiFi.macAddress(), "Hardware", "Factory-assigned MAC address");
  config.addInformation("WiFi", "ip", "IP Address", "0.0.0.0", "Network Status", "Currently assigned IPv4 address");
  config.addInformation("WiFi", "state", "Connection State", "DISCONNECTED", "Network Status", "Current status of the station interface");
  config.addInformation("WiFi", "connected_ssid", "Active SSID", "None", "Network Status", "Access point currently connected to");

  config.addChoiceQuestion(
    "WiFi",
    "select_ssid",
    "Credentials",
    "Select Network",
    "None",
    { "None" },
    handleNetworkSelect,
    true  // Protected
  );

  config.addStringQuestion(
    "WiFi",
    "wifi_password",
    "Credentials",
    "Wi-Fi Password",
    "",
    64,
    handlePasswordInput,
    true  // Protected
  );

  config.addIntegerQuestion(
    "WiFi",
    "ping_count",
    "Diagnostics",
    "Ping Retry Attempts",
    3,
    1,
    10,
    handlePingCountChange,
    false);

  config.addButtonCommand(
    "WiFi",
    "scan_wifi",
    "Credentials",
    "Scan Networks",
    handleScanNetworks);

  config.addButtonCommand(
    "WiFi",
    "connect_wifi",
    "Credentials",
    "Connect to WiFi",
    handleConnectWiFi,
    "Attempting to join network. This may take up to 10 seconds.",
    "",
    false,
    true);

  config.addButtonCommand(
    "WiFi",
    "test_ping",
    "Diagnostics",
    "Test Internet Connection",
    handleTestPing);
}

void loop() {
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck > 2000) {
    lastCheck = millis();
    updateWiFiStatusInformation();
  }

  // Poll for background Wi-Fi scan results without blocking execution
  checkWiFiScanResults();
}

// -----------------------------------------------------------------------------
// QUESTION CALLBACKS
// -----------------------------------------------------------------------------

void handleNetworkSelect(String selectedSSID) {
  targetSSID = selectedSSID;
  config.updateQuestion("WiFi", "select_ssid", targetSSID, "[good] [time] Target SSID updated to: " + targetSSID);
}

void handlePasswordInput(String pass) {
  targetPassword = pass;
  config.updateQuestion("WiFi", "wifi_password", "********", "[good] [time] Password set successfully.");
}

void handlePingCountChange(String countVal) {
  pingAttempts = countVal.toInt();
  config.updateQuestion("WiFi", "ping_count", String(pingAttempts), "[good] Set ping retry count to " + String(pingAttempts));
}

// -----------------------------------------------------------------------------
// COMMAND CALLBACKS & ASYNC SCAN LOGIC
// -----------------------------------------------------------------------------

void handleScanNetworks(bool pressed) {
  if (!pressed) return;

  // 1. Instantly output update message to Serial/Host UI
  config.updateCommand("WiFi", "scan_wifi", "[time] Scanning for local networks...");

  // 2. Clear scan cache and launch asynchronous scan (true parameter)
  WiFi.scanDelete();
  WiFi.scanNetworks(true);
  isScanningWiFi = true;
}

void checkWiFiScanResults() {
  if (!isScanningWiFi) return;

  int numNetworks = WiFi.scanComplete();

  // If scan is still in progress, return and let loop() run
  if (numNetworks == WIFI_SCAN_RUNNING) {
    return;
  }

  isScanningWiFi = false;

  if (numNetworks <= 0) {
    config.updateCommand("WiFi", "scan_wifi", "[bad] [time] No networks found during scan.");
    WiFi.scanDelete();
    return;
  }

  std::vector<String> ssidList;
  for (int i = 0; i < numNetworks; ++i) {
    String ssid = WiFi.SSID(i);
    ssid.trim();

    if (ssid.length() > 0) {
      // Deduplicate SSIDs (handles dual-band 2.4GHz/5GHz routers)
      bool duplicate = false;
      for (const auto& existing : ssidList) {
        if (existing == ssid) {
          duplicate = true;
          break;
        }
      }
      if (!duplicate) {
        ssidList.push_back(ssid);
      }
    }
  }

  WiFi.scanDelete();

  if (ssidList.empty()) {
    config.updateCommand("WiFi", "scan_wifi", "[bad] [time] No valid networks discovered.");
    return;
  }

  if (targetSSID.length() == 0 || targetSSID == "None") {
    targetSSID = ssidList[0];
  }

  // Update dynamic options payload for choice question
  config.updateQuestionOptions("WiFi", "select_ssid", ssidList, targetSSID);

  // Send final message update
  config.updateCommand("WiFi", "scan_wifi", "[good] [time] Scan complete! Found " + String(ssidList.size()) + " unique networks.");
  Serial.println();
  Serial.println("==========");
  Serial.println("There's even a built-in serial terminal!");
}

void handleConnectWiFi(bool pressed) {
  if (!pressed) return;

  if (targetSSID.length() == 0 || targetSSID == "None") {
    config.updateCommand("WiFi", "connect_wifi", "[bad] [time] Please select a valid SSID first!");
    return;
  }

  config.updateCommand("WiFi", "connect_wifi", "[time] Connecting to " + targetSSID + "...");
  config.updateInformation("WiFi", "state", "CONNECTING", "Attempting AP association");

  WiFi.begin(targetSSID.c_str(), targetPassword.c_str());

  int timeout = 20;
  while (WiFi.status() != WL_CONNECTED && timeout > 0) {
    delay(500);
    timeout--;
  }

  if (WiFi.status() == WL_CONNECTED) {
    config.updateCommand("WiFi", "connect_wifi", "[good] [time] Successfully connected to " + targetSSID);
    updateWiFiStatusInformation();
  } else {
    config.updateCommand("WiFi", "connect_wifi", "[bad] [time] Failed to connect to " + targetSSID + ". Check password.");
    updateWiFiStatusInformation();
  }
}

void handleTestPing(bool pressed) {
  if (!pressed) return;

  if (WiFi.status() != WL_CONNECTED) {
    config.updateCommand("WiFi", "test_ping", "[bad] [time] Cannot ping: Wi-Fi is disconnected!");
    return;
  }

  config.updateCommand("WiFi", "test_ping", "[time] Ping test started...");

  bool success = false;
  for (int i = 0; i < pingAttempts; i++) {
    HTTPClient http;
    http.begin("http://google.com");
    http.setTimeout(2000);
    int httpCode = http.GET();
    http.end();

    if (httpCode > 0) {
      success = true;
      break;
    }
    delay(250);
  }

  if (success) {
    config.updateCommand("WiFi", "test_ping", "[good] [time] Internet Check Passed! Reached google.com successfully.");
  } else {
    config.updateCommand("WiFi", "test_ping", "[bad] [time] Internet Check Failed! Host google.com unreachable.");
  }
}

// -----------------------------------------------------------------------------
// HELPER FUNCTIONS
// -----------------------------------------------------------------------------

void updateWiFiStatusInformation() {
  wl_status_t status = WiFi.status();
  String stateStr = "DISCONNECTED";

  switch (status) {
    case WL_CONNECTED:
      stateStr = "CONNECTED";
      config.updateInformation("WiFi", "ip", WiFi.localIP().toString(), "Currently assigned IPv4 address");
      config.updateInformation("WiFi", "connected_ssid", WiFi.SSID(), "Access point currently connected to");
      break;
    case WL_DISCONNECTED:
      stateStr = "DISCONNECTED";
      config.updateInformation("WiFi", "ip", "0.0.0.0");
      config.updateInformation("WiFi", "connected_ssid", "None");
      break;
    case WL_IDLE_STATUS:
      stateStr = "IDLE";
      break;
    default:
      stateStr = "FAILED";
      break;
  }

  config.updateInformation("WiFi", "state", stateStr);
}