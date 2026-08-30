#ifndef CUSTOM_ARDUINO_LIBRARY_ESP_CONFIG_H
#define CUSTOM_ARDUINO_LIBRARY_ESP_CONFIG_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <vector>
#include <functional>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

typedef std::function<void(String answer)> AnswerCallback;
typedef std::function<void(bool pressed)> ButtonCommandCallback;
typedef std::function<void(String input)> StringCommandCallback;

struct ConfigQuestion {
    String source;
    String id;
    String category;
    String type; // "choice", "selection", "integer", "string"
    String prompt;
    String currentValue;
    String message;
    std::vector<String> options;
    int lowerLimit = 0;
    int upperLimit = 0;
    bool hasLimits = false;
    int maxLength = 0;
    bool protectedVal = false;
    bool unavailable = false;
    bool needsSync = false;
    AnswerCallback callback = nullptr;
};

struct ConfigCommand {
    String source;
    String id;
    String category;
    String type; // "button", "latch", "string"
    String title;
    String popup;
    String message;
    bool implyEnd = false;
    bool protectedVal = false;
    bool unavailable = false;
    int maxLength = 0;
    bool needsSync = false;
    ButtonCommandCallback buttonCallback = nullptr;
    StringCommandCallback stringCallback = nullptr;
};

struct ConfigInformation {
    String source;
    String id;
    String category;
    String title;
    String value;
    String explanation;
    bool needsSync = false;
};

class ESPConfig {
public:
    ESPConfig();
    ~ESPConfig();

    void begin(String password = "", String hint = "");
    
    bool isAuthenticated() const;
    void resetAuthentication();

    // Question Builders & Updaters
    void addChoiceQuestion(String source, String id, String category, String prompt,
                           String defaultValue, std::vector<String> options,
                           AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addSelectionQuestion(String source, String id, String category, String prompt,
                             String defaultValue, std::vector<String> options,
                             AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addSelectionQuestion(String source, String id, String category, String prompt,
                             std::vector<String> defaultValues, std::vector<String> options,
                             AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addIntegerQuestion(String source, String id, String category, String prompt,
                            int defaultValue, int lowerLimit, int upperLimit,
                            AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addStringQuestion(String source, String id, String category, String prompt,
                           String defaultValue = "", int maxLength = 0,
                           AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void setQuestion(const ConfigQuestion& q);
    void updateQuestion(String source, String id, String value, String message = "");
    void updateQuestion(String source, String id, std::vector<String> values, String message = "");
    void updateQuestionOptions(String source, String id, std::vector<String> options, String currentValue = "");
    void updateQuestionAvailability(String source, String id, bool unavailable);

    // Command Builders & Updaters
    void addButtonCommand(String source, String id, String category, String title,
                          ButtonCommandCallback callback = nullptr, String popup = "",
                          String message = "", bool implyEnd = false, bool protectedVal = false, bool unavailable = false);

    void addLatchCommand(String source, String id, String category, String title,
                         ButtonCommandCallback callback = nullptr, String popup = "",
                         String message = "", bool implyEnd = false, bool protectedVal = false, bool unavailable = false);

    void addStringCommand(String source, String id, String category, String title,
                          StringCommandCallback callback = nullptr, int maxLength = 0, String popup = "",
                          String message = "", bool implyEnd = false, bool protectedVal = false, bool unavailable = false);

    void setCommand(const ConfigCommand& cmd);
    void updateCommand(String source, String id, String message);
    void updateCommandAvailability(String source, String id, bool unavailable);

    // Information Management
    void addInformation(String source, String id, String title, String value, String category = "", String explanation = "");
    void updateInformation(String source, String id, String value, String explanation = "");

    void update();

private:
    std::vector<ConfigQuestion> questions;
    std::vector<ConfigCommand> commands;
    std::vector<ConfigInformation> informationList;

    String systemPassword = "";
    String passwordHint = "";
    bool isPasswordAuthenticated = true;
    bool lastPasswordResult = false;
    bool sendPasswordResultSync = false;
    uint32_t messageNumber = 0;

    SemaphoreHandle_t dataMutex;
    TaskHandle_t serialTaskHandle = nullptr;

    static void serialTask(void* parameter);
    
    void processIncomingJson(JsonDocument& doc);
    void sendInitialState();
    void sendConfigPayload(JsonDocument& doc);
    void sendAck();
};

#endif // CUSTOM_ARDUINO_LIBRARY_ESP_CONFIG_H