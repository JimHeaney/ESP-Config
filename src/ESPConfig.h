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
    String type;
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
    String type;
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
    static const size_t MAX_PAYLOAD_SIZE = 512;

    ESPConfig();
    ~ESPConfig();

    void begin(const String& password = "", const String& hint = "");
    void reserve(size_t questionsCount, size_t commandsCount, size_t infoCount);
    
    bool isAuthenticated() const;
    void resetAuthentication();

    // Question Builders & Updaters
    void addChoiceQuestion(const String& source, const String& id, const String& category, const String& prompt,
                           const String& defaultValue, const std::vector<String>& options,
                           AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addSelectionQuestion(const String& source, const String& id, const String& category, const String& prompt,
                             const String& defaultValue, const std::vector<String>& options,
                             AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addSelectionQuestion(const String& source, const String& id, const String& category, const String& prompt,
                             const std::vector<String>& defaultValues, const std::vector<String>& options,
                             AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addIntegerQuestion(const String& source, const String& id, const String& category, const String& prompt,
                            int defaultValue, int lowerLimit, int upperLimit,
                            AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void addStringQuestion(const String& source, const String& id, const String& category, const String& prompt,
                           const String& defaultValue = "", int maxLength = 0,
                           AnswerCallback callback = nullptr, bool protectedVal = false, bool unavailable = false);

    void setQuestion(const ConfigQuestion& q);
    void updateQuestion(const String& source, const String& id, const String& value, const String& message = "");
    void updateQuestion(const String& source, const String& id, const std::vector<String>& values, const String& message = "");
    void updateQuestionOptions(const String& source, const String& id, const std::vector<String>& options, const String& currentValue = "");
    void updateQuestionAvailability(const String& source, const String& id, bool unavailable);

    // Command Builders & Updaters
    void addButtonCommand(const String& source, const String& id, const String& category, const String& title,
                          ButtonCommandCallback callback = nullptr, const String& popup = "",
                          const String& message = "", bool implyEnd = false, bool protectedVal = false, bool unavailable = false);

    void addLatchCommand(const String& source, const String& id, const String& category, const String& title,
                         ButtonCommandCallback callback = nullptr, const String& popup = "",
                         const String& message = "", bool implyEnd = false, bool protectedVal = false, bool unavailable = false);

    void addStringCommand(const String& source, const String& id, const String& category, const String& title,
                          StringCommandCallback callback = nullptr, int maxLength = 0, const String& popup = "",
                          const String& message = "", bool implyEnd = false, bool protectedVal = false, bool unavailable = false);

    void setCommand(const ConfigCommand& cmd);
    void updateCommand(const String& source, const String& id, const String& message);
    void updateCommandAvailability(const String& source, const String& id, bool unavailable);

    // Information Management
    void addInformation(const String& source, const String& id, const String& category, const String& title, const String& value, const String& explanation = "");
    void updateInformation(const String& source, const String& id, const String& value, const String& explanation = "");

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
    bool isStarted = false;
    uint32_t messageNumber = 0;

    SemaphoreHandle_t dataMutex;
    TaskHandle_t serialTaskHandle = nullptr;

    static void serialTask(void* parameter);
    
    void processIncomingJson(JsonDocument& doc);
    void sendInitialState();
    void sendConfigPayload(JsonDocument& doc);
    void sendAck();

    // Protocol Helpers
    void populateMetadata(JsonDocument& doc, bool includePasswordResult = false);
    void buildQuestionJson(const ConfigQuestion& q, JsonObject& obj, bool fullState);
    void buildCommandJson(const ConfigCommand& c, JsonObject& obj, bool fullState);
    void buildInformationJson(const ConfigInformation& i, JsonObject& obj, bool fullState);
    JsonArray getOrCreateArray(JsonDocument& doc, const char* key);
};

#endif // CUSTOM_ARDUINO_LIBRARY_ESP_CONFIG_H