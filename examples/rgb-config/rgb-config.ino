#include "ESPConfig.h"

ESPConfig config;

int currentBrightness = 64;
String activeChannels = "Red";

void updateLED() {
  uint8_t r = (activeChannels.indexOf("Red") != -1) ? currentBrightness : 0;
  uint8_t g = (activeChannels.indexOf("Green") != -1) ? currentBrightness : 0;
  uint8_t b = (activeChannels.indexOf("Blue") != -1) ? currentBrightness : 0;

  neopixelWrite(RGB_BUILTIN, r, g, b);
}

// Callback for multi-select color channels
void handleRGBSelection(String selectedColors) {
  activeChannels = selectedColors;
  updateLED();

  config.updateQuestion("LED", "rgb_color", selectedColors, "[good] Active channels updated.");
}

// Callback for integer brightness input
void handleBrightness(String brightnessStr) {
  currentBrightness = brightnessStr.toInt();
  updateLED();

  config.updateQuestion("LED", "rgb_brightness", brightnessStr, "[good] Brightness set to " + brightnessStr);
}

void setup() {
  config.begin();

  std::vector<String> colorOptions = { "Red", "Green", "Blue" };

  config.addSelectionQuestion(
    "LED",
    "rgb_color",
    "Lighting",
    "Active RGB Channels",
    "[\"Red\"]",  // Initial array format
    colorOptions,
    handleRGBSelection);

  config.addIntegerQuestion(
    "LED",
    "rgb_brightness",
    "Lighting",
    "Brightness (0-255)",
    64,
    0,
    255,
    handleBrightness);

  updateLED();
}

void loop() {
  // FreeRTOS background task handles communication automatically
}