/*
  ===============================================================================
  ESPConfig Library Example: Dynamic Blink Controller
  ===============================================================================
  Demonstrates tailored builder methods for dynamic configuration:
  1. Choice Question   -> config.addChoiceQuestion()
  2. Integer Question  -> config.addIntegerQuestion()
  3. Button Command    -> config.addButtonCommand()
  ===============================================================================
*/

#include <Arduino.h>
#include "ESPConfig.h"

#ifndef LED_BUILTIN
#define LED_BUILTIN 2
#endif

ESPConfig config;

// Local Application State
String currentMode = "Auto";
int blinksPerSecond = 1;
bool manualLedState = false;
unsigned long lastBlinkTime = 0;
bool autoLedState = false;

// Callback Declarations
void handleModeChange(String newMode);
void handleBlinkRateChange(String newRate);
void handleLedToggle(bool pressed);

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);

  // Initialize serial communication and background thread
  //Since we didn't set a password here, the software won't ask for one.
  config.begin();

  // -------------------------------------------------------------------------
  // QUESTION 1: Mode Select (Choice Type)
  // Signature: source, id, category, prompt, defaultValue, options, callback
  // -------------------------------------------------------------------------
  config.addChoiceQuestion(
    "system",
    "mode",
    "LED Mode",
    "Select Operation Mode",
    "Auto",
    { "Auto", "Manual" },
    handleModeChange);

  // -------------------------------------------------------------------------
  // QUESTION 2: Blink Rate (Integer Type)
  // Signature: source, id, category, prompt, defaultValue, lowerLimit, upperLimit, callback
  // -------------------------------------------------------------------------
  config.addIntegerQuestion(
    "system",
    "blink_rate",
    "Auto Controls",
    "Blinks Per Second",
    1,  // Default value (int)
    1,  // Lower limit (int)
    5,  // Upper limit (int)
    handleBlinkRateChange);

  // -------------------------------------------------------------------------
  // COMMAND 1: Manual LED Button (Button Type)
  // Signature: source, id, category, title, callback, popup, message, implyEnd, protected, unavailable
  // -------------------------------------------------------------------------
  config.addButtonCommand(
    "system",
    "led_toggle",
    "Manual Controls",
    "Hold to Light LED",
    handleLedToggle,
    "",     // No pop-up needed
    "",     // No default message
    false,  // implyEnd
    false,  // protectedVal
    true    // Start unavailable/greyed-out (since default mode is Auto)
  );
}

void loop() {
  // Drive LED blinking in Auto mode
  if (currentMode == "Auto") {
    unsigned long currentMillis = millis();
    unsigned long interval = 1000 / (blinksPerSecond * 2);

    if (currentMillis - lastBlinkTime >= interval) {
      lastBlinkTime = currentMillis;
      autoLedState = !autoLedState;
      digitalWrite(LED_BUILTIN, autoLedState ? HIGH : LOW);
    }
  }
}

// -----------------------------------------------------------------------------
// CALLBACK HANDLERS
// -----------------------------------------------------------------------------

void handleModeChange(String newMode) {
  currentMode = newMode;

  if (currentMode.equalsIgnoreCase("Auto")) {
    // Enable rate integer box, disable manual button
    config.updateQuestionAvailability("system", "blink_rate", false);
    config.updateCommandAvailability("system", "led_toggle", true);
  } else if (currentMode.equalsIgnoreCase("Manual")) {
    // Disable rate integer box, enable manual button
    config.updateQuestionAvailability("system", "blink_rate", true);
    config.updateCommandAvailability("system", "led_toggle", false);

    digitalWrite(LED_BUILTIN, LOW);
    autoLedState = false;
  }
}

void handleBlinkRateChange(String newRate) {
  int parsedRate = newRate.toInt();

  // Application-side logic verification
  if (parsedRate >= 1 && parsedRate <= 5) {
    blinksPerSecond = parsedRate;
    config.updateQuestion("system", "blink_rate", String(blinksPerSecond), "Rate updated successfully!");
  } else {
    config.updateQuestion("system", "blink_rate", String(blinksPerSecond), "Value out of bounds (1-5)!");
  }
}

void handleLedToggle(bool pressed) {
  if (currentMode == "Manual") {
    manualLedState = pressed;
    digitalWrite(LED_BUILTIN, manualLedState ? HIGH : LOW);
  }
}