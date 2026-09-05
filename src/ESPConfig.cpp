#include "ESPConfig.h"

ESPConfig::ESPConfig() {
    dataMutex = xSemaphoreCreateRecursiveMutex();
}

ESPConfig::~ESPConfig() {
    if (serialTaskHandle != nullptr) {
        vTaskDelete(serialTaskHandle);
    }
    if (dataMutex != nullptr) {
        vSemaphoreDelete(dataMutex);
    }
}

void ESPConfig::begin(String password, String hint) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    systemPassword = password;
    passwordHint = hint;
    isPasswordAuthenticated = (systemPassword.length() == 0);
    xSemaphoreGiveRecursive(dataMutex);

    Serial.begin(115200);
    xTaskCreate(
        serialTask,
        "ESPConfigSerialTask",
        4096,
        this,
        1,
        &serialTaskHandle
    );
}

bool ESPConfig::isAuthenticated() const {
    return isPasswordAuthenticated;
}

void ESPConfig::resetAuthentication() {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    bool wasAuthenticated = isPasswordAuthenticated;
    isPasswordAuthenticated = (systemPassword.length() == 0);

    if (wasAuthenticated != isPasswordAuthenticated) {
        for (auto& q : questions) {
            if (q.protectedVal) q.needsSync = true;
        }
        for (auto& c : commands) {
            if (c.protectedVal) c.needsSync = true;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

// -----------------------------------------------------------------------------
// QUESTION METHODS
// -----------------------------------------------------------------------------

void ESPConfig::addChoiceQuestion(String source, String id, String category, String prompt,
                                  String defaultValue, std::vector<String> options,
                                  AnswerCallback callback, bool protectedVal, bool unavailable) {
    ConfigQuestion q;
    q.source = source;
    q.id = id;
    q.category = category;
    q.type = "choice";
    q.prompt = prompt;
    q.currentValue = defaultValue;
    q.options = options;
    q.callback = callback;
    q.protectedVal = protectedVal;
    q.unavailable = unavailable;
    setQuestion(q);
}

void ESPConfig::addSelectionQuestion(String source, String id, String category, String prompt,
                                     String defaultValue, std::vector<String> options,
                                     AnswerCallback callback, bool protectedVal, bool unavailable) {
    ConfigQuestion q;
    q.source = source;
    q.id = id;
    q.category = category;
    q.type = "selection";
    q.prompt = prompt;
    q.currentValue = defaultValue;
    q.options = options;
    q.callback = callback;
    q.protectedVal = protectedVal;
    q.unavailable = unavailable;
    setQuestion(q);
}

void ESPConfig::addSelectionQuestion(String source, String id, String category, String prompt,
                                     std::vector<String> defaultValues, std::vector<String> options,
                                     AnswerCallback callback, bool protectedVal, bool unavailable) {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();
    for (const auto& val : defaultValues) {
        arr.add(val);
    }
    String serializedVal;
    serializeJson(arr, serializedVal);
    addSelectionQuestion(source, id, category, prompt, serializedVal, options, callback, protectedVal, unavailable);
}

void ESPConfig::addIntegerQuestion(String source, String id, String category, String prompt,
                                   int defaultValue, int lowerLimit, int upperLimit,
                                   AnswerCallback callback, bool protectedVal, bool unavailable) {
    ConfigQuestion q;
    q.source = source;
    q.id = id;
    q.category = category;
    q.type = "integer";
    q.prompt = prompt;
    q.currentValue = String(defaultValue);
    q.lowerLimit = lowerLimit;
    q.upperLimit = upperLimit;
    q.hasLimits = true;
    q.callback = callback;
    q.protectedVal = protectedVal;
    q.unavailable = unavailable;
    setQuestion(q);
}

void ESPConfig::addStringQuestion(String source, String id, String category, String prompt,
                                 String defaultValue, int maxLength,
                                 AnswerCallback callback, bool protectedVal, bool unavailable) {
    ConfigQuestion q;
    q.source = source;
    q.id = id;
    q.category = category;
    q.type = "string";
    q.prompt = prompt;
    q.currentValue = defaultValue;
    q.maxLength = maxLength;
    q.callback = callback;
    q.protectedVal = protectedVal;
    q.unavailable = unavailable;
    setQuestion(q);
}

void ESPConfig::setQuestion(const ConfigQuestion& q) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& item : questions) {
        if (item.source == q.source && item.id == q.id) {
            item = q;
            item.needsSync = true;
            xSemaphoreGiveRecursive(dataMutex);
            return;
        }
    }
    questions.push_back(q);
    questions.back().needsSync = true;
    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::updateQuestion(String source, String id, String value, String message) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& q : questions) {
        if (q.source == source && q.id == id) {
            q.currentValue = value;
            if (message.length() > 0) q.message = message;
            q.needsSync = true;
            break;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::updateQuestion(String source, String id, std::vector<String> values, String message) {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();
    for (const auto& val : values) {
        arr.add(val);
    }
    String serializedVal;
    serializeJson(arr, serializedVal);
    updateQuestion(source, id, serializedVal, message);
}

void ESPConfig::updateQuestionOptions(String source, String id, std::vector<String> options, String currentValue) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& q : questions) {
        if (q.source == source && q.id == id) {
            q.options = options;
            if (currentValue.length() > 0) {
                q.currentValue = currentValue;
            }
            q.needsSync = true;
            break;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::updateQuestionAvailability(String source, String id, bool unavailable) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& q : questions) {
        if (q.source == source && q.id == id) {
            q.unavailable = unavailable;
            q.needsSync = true;
            break;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

// -----------------------------------------------------------------------------
// COMMAND METHODS
// -----------------------------------------------------------------------------

void ESPConfig::addButtonCommand(String source, String id, String category, String title,
                                 ButtonCommandCallback callback, String popup,
                                 String message, bool implyEnd, bool protectedVal, bool unavailable) {
    ConfigCommand cmd;
    cmd.source = source;
    cmd.id = id;
    cmd.category = category;
    cmd.type = "button";
    cmd.title = title;
    cmd.buttonCallback = callback;
    cmd.popup = popup;
    cmd.message = message;
    cmd.implyEnd = implyEnd;
    cmd.protectedVal = protectedVal;
    cmd.unavailable = unavailable;
    setCommand(cmd);
}

void ESPConfig::addLatchCommand(String source, String id, String category, String title,
                                ButtonCommandCallback callback, String popup,
                                String message, bool implyEnd, bool protectedVal, bool unavailable) {
    ConfigCommand cmd;
    cmd.source = source;
    cmd.id = id;
    cmd.category = category;
    cmd.type = "latch";
    cmd.title = title;
    cmd.buttonCallback = callback;
    cmd.popup = popup;
    cmd.message = message;
    cmd.implyEnd = implyEnd;
    cmd.protectedVal = protectedVal;
    cmd.unavailable = unavailable;
    setCommand(cmd);
}

void ESPConfig::addStringCommand(String source, String id, String category, String title,
                                 StringCommandCallback callback, int maxLength, String popup,
                                 String message, bool implyEnd, bool protectedVal, bool unavailable) {
    ConfigCommand cmd;
    cmd.source = source;
    cmd.id = id;
    cmd.category = category;
    cmd.type = "string";
    cmd.title = title;
    cmd.stringCallback = callback;
    cmd.maxLength = maxLength;
    cmd.popup = popup;
    cmd.message = message;
    cmd.implyEnd = implyEnd;
    cmd.protectedVal = protectedVal;
    cmd.unavailable = unavailable;
    setCommand(cmd);
}

void ESPConfig::setCommand(const ConfigCommand& cmd) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& item : commands) {
        if (item.source == cmd.source && item.id == cmd.id) {
            item = cmd;
            item.needsSync = true;
            xSemaphoreGiveRecursive(dataMutex);
            return;
        }
    }
    commands.push_back(cmd);
    commands.back().needsSync = true;
    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::updateCommand(String source, String id, String message) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& cmd : commands) {
        if (cmd.source == source && cmd.id == id) {
            cmd.message = message;
            cmd.needsSync = true;
            break;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::updateCommandAvailability(String source, String id, bool unavailable) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& cmd : commands) {
        if (cmd.source == source && cmd.id == id) {
            cmd.unavailable = unavailable;
            cmd.needsSync = true;
            break;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

// -----------------------------------------------------------------------------
// INFORMATION METHODS
// -----------------------------------------------------------------------------

void ESPConfig::addInformation(String source, String id, String category, String title, String value, String explanation) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    ConfigInformation info;
    info.source = source;
    info.id = id;
    info.title = title;
    info.value = value;
    info.category = category;
    info.explanation = explanation;
    info.needsSync = true;

    for (auto& item : informationList) {
        if (item.source == source && item.id == id) {
            item = info;
            xSemaphoreGiveRecursive(dataMutex);
            return;
        }
    }
    informationList.push_back(info);
    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::updateInformation(String source, String id, String value, String explanation) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    for (auto& info : informationList) {
        if (info.source == source && info.id == id) {
            info.value = value;
            if (explanation.length() > 0) info.explanation = explanation;
            info.needsSync = true;
            break;
        }
    }
    xSemaphoreGiveRecursive(dataMutex);
}

// -----------------------------------------------------------------------------
// CORE LOGIC & SERIAL PROTOCOL
// -----------------------------------------------------------------------------

void ESPConfig::serialTask(void* parameter) {
    ESPConfig* instance = static_cast<ESPConfig*>(parameter);
    String inputBuffer = "";

    while (true) {
        while (Serial.available()) {
            char c = Serial.read();
            if (c == '\n') {
                inputBuffer.trim();
                if (inputBuffer.startsWith("[config]") || inputBuffer.startsWith("{")) {
                    int jsonStart = inputBuffer.indexOf('{');
                    if (jsonStart != -1) {
                        String rawJson = inputBuffer.substring(jsonStart);
                        JsonDocument doc;
                        DeserializationError err = deserializeJson(doc, rawJson);
                        if (!err) {
                            instance->processIncomingJson(doc);
                        }
                    }
                }
                inputBuffer = "";
            } else {
                inputBuffer += c;
            }
        }
        instance->update();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void ESPConfig::processIncomingJson(JsonDocument& doc) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);

    if (doc.containsKey("metadata")) {
        JsonObject meta = doc["metadata"];
        if (meta.containsKey("password")) {
            String pass = meta["password"].as<String>();
            bool wasAuthenticated = isPasswordAuthenticated;

            if (systemPassword.length() == 0 || pass == systemPassword) {
                isPasswordAuthenticated = true;
                lastPasswordResult = true;
            } else {
                isPasswordAuthenticated = false;
                lastPasswordResult = false;
            }
            sendPasswordResultSync = true;

            if (wasAuthenticated != isPasswordAuthenticated) {
                for (auto& q : questions) {
                    if (q.protectedVal) q.needsSync = true;
                }
                for (auto& c : commands) {
                    if (c.protectedVal) c.needsSync = true;
                }
            }
        }
    }

    if (doc.containsKey("operation")) {
        String op = doc["operation"].as<String>();
        if (op == "start") {
            sendInitialState();
            xSemaphoreGiveRecursive(dataMutex);
            return;
        } else if (op == "check") {
            sendAck();
        }
    }

    if (doc.containsKey("answers")) {
        JsonArray answers = doc["answers"].as<JsonArray>();
        for (JsonObject ans : answers) {
            String src = ans["source"] | "Core";
            String id = ans["id"] | "";
            
            for (auto& q : questions) {
                if (q.source == src && q.id == id) {
                    bool canExecute = !q.protectedVal || systemPassword.length() == 0 || isPasswordAuthenticated;
                    if (canExecute) {
                        String ansVal = "";
                        if (ans["answer"].is<JsonArray>()) {
                            serializeJson(ans["answer"], ansVal);
                        } else {
                            ansVal = ans["answer"].as<String>();
                        }
                        q.currentValue = ansVal;
                        if (q.callback) {
                            q.callback(ansVal);
                        }
                    }
                    break;
                }
            }
        }
    }

    if (doc.containsKey("commands")) {
        JsonArray cmds = doc["commands"].as<JsonArray>();
        for (JsonObject cmd : cmds) {
            String src = cmd["source"] | "Core";
            String id = cmd["id"] | "";

            for (auto& c : commands) {
                if (c.source == src && c.id == id) {
                    bool canExecute = !c.protectedVal || systemPassword.length() == 0 || isPasswordAuthenticated;
                    if (canExecute) {
                        if (c.type == "string" && c.stringCallback) {
                            String strInput = cmd["input"].as<String>();
                            c.stringCallback(strInput);
                        } else if ((c.type == "button" || c.type == "latch") && c.buttonCallback) {
                            bool boolInput = cmd["input"].as<bool>();
                            c.buttonCallback(boolInput);
                        }
                    }
                    break;
                }
            }
        }
    }

    xSemaphoreGiveRecursive(dataMutex);
}

void ESPConfig::sendInitialState() {
    JsonDocument doc;

    JsonArray qArray = doc["questions"].to<JsonArray>();
    for (const auto& q : questions) {
        JsonObject obj = qArray.add<JsonObject>();
        obj["source"] = q.source;
        obj["id"] = q.id;
        obj["category"] = q.category;
        obj["type"] = q.type;
        obj["prompt"] = q.prompt;

        if (q.currentValue.startsWith("[")) {
            obj["current"] = serialized(q.currentValue);
        } else {
            obj["current"] = q.currentValue;
        }

        if (!q.options.empty()) {
            JsonArray opts = obj["options"].to<JsonArray>();
            for (const auto& opt : q.options) {
                opts.add(opt);
            }
        }

        if (q.hasLimits) {
            obj["lower-limit"] = q.lowerLimit;
            obj["upper-limit"] = q.upperLimit;
        }

        if (q.message.length() > 0) obj["message"] = q.message;
        if (q.maxLength > 0) obj["max-length"] = q.maxLength;
        if (q.protectedVal) obj["protected"] = true;

        bool effectiveUnavailable = q.unavailable || (q.protectedVal && systemPassword.length() > 0 && !isPasswordAuthenticated);
        obj["unavailable"] = effectiveUnavailable;
    }

    JsonArray cArray = doc["commands"].to<JsonArray>();
    for (const auto& c : commands) {
        JsonObject obj = cArray.add<JsonObject>();
        obj["source"] = c.source;
        obj["id"] = c.id;
        obj["category"] = c.category;
        obj["type"] = c.type;
        obj["title"] = c.title;

        if (c.popup.length() > 0) obj["pop-up"] = c.popup;
        if (c.message.length() > 0) obj["message"] = c.message;
        if (c.maxLength > 0) obj["max-length"] = c.maxLength;
        if (c.implyEnd) obj["imply-end"] = true;
        if (c.protectedVal) obj["protected"] = true;

        bool effectiveUnavailable = c.unavailable || (c.protectedVal && systemPassword.length() > 0 && !isPasswordAuthenticated);
        obj["unavailable"] = effectiveUnavailable;
    }

    JsonArray iArray = doc["information"].to<JsonArray>();
    for (const auto& i : informationList) {
        JsonObject obj = iArray.add<JsonObject>();
        obj["source"] = i.source;
        obj["id"] = i.id;
        if (i.category.length() > 0) obj["category"] = i.category;
        obj["title"] = i.title;
        obj["value"] = i.value;
        if (i.explanation.length() > 0) obj["explanation"] = i.explanation;
    }

    JsonObject meta = doc["metadata"].to<JsonObject>();
    meta["version"] = 1;
    meta["message-number"] = messageNumber++;

    if (systemPassword.length() == 0 || isPasswordAuthenticated) {
        meta["password-correct"] = true;
    }

    if (passwordHint.length() > 0) {
        meta["hint"] = passwordHint;
    }

    sendConfigPayload(doc);
}

void ESPConfig::sendAck() {
    JsonDocument doc;
    doc["operation"] = "ack";
    JsonObject meta = doc["metadata"].to<JsonObject>();
    meta["version"] = 1;
    meta["message-number"] = messageNumber++;

    if (systemPassword.length() == 0 || isPasswordAuthenticated) {
        meta["password-correct"] = true;
    }

    if (passwordHint.length() > 0) {
        meta["hint"] = passwordHint;
    }

    sendConfigPayload(doc);
}

void ESPConfig::sendConfigPayload(JsonDocument& doc) {
    String output;
    serializeJson(doc, output);
    Serial.print("[config] ");
    Serial.println(output);
}

void ESPConfig::update() {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);

    bool hasUpdates = sendPasswordResultSync;

    for (const auto& q : questions) {
        if (q.needsSync) { hasUpdates = true; break; }
    }
    if (!hasUpdates) {
        for (const auto& c : commands) {
            if (c.needsSync) { hasUpdates = true; break; }
        }
    }
    if (!hasUpdates) {
        for (const auto& i : informationList) {
            if (i.needsSync) { hasUpdates = true; break; }
        }
    }

    if (hasUpdates) {
        JsonDocument doc;

        bool hasQuestionUpdates = false;
        JsonArray qArray = doc["questions"].to<JsonArray>();
        for (auto& q : questions) {
            if (q.needsSync) {
                JsonObject obj = qArray.add<JsonObject>();
                obj["source"] = q.source;
                obj["id"] = q.id;
                obj["category"] = q.category;
                obj["type"] = q.type;
                obj["prompt"] = q.prompt;

                if (q.currentValue.startsWith("[")) {
                    obj["current"] = serialized(q.currentValue);
                } else {
                    obj["current"] = q.currentValue;
                }

                if (!q.options.empty()) {
                    JsonArray opts = obj["options"].to<JsonArray>();
                    for (const auto& opt : q.options) {
                        opts.add(opt);
                    }
                }

                if (q.message.length() > 0) obj["message"] = q.message;
                if (q.protectedVal) obj["protected"] = true;
                
                bool effectiveUnavailable = q.unavailable || (q.protectedVal && systemPassword.length() > 0 && !isPasswordAuthenticated);
                obj["unavailable"] = effectiveUnavailable;

                q.needsSync = false;
                hasQuestionUpdates = true;
            }
        }
        if (!hasQuestionUpdates) doc.remove("questions");

        bool hasCommandUpdates = false;
        JsonArray cArray = doc["commands"].to<JsonArray>();
        for (auto& c : commands) {
            if (c.needsSync) {
                JsonObject obj = cArray.add<JsonObject>();
                obj["source"] = c.source;
                obj["id"] = c.id;
                if (c.message.length() > 0) obj["message"] = c.message;

                bool effectiveUnavailable = c.unavailable || (c.protectedVal && systemPassword.length() > 0 && !isPasswordAuthenticated);
                obj["unavailable"] = effectiveUnavailable;

                c.needsSync = false;
                hasCommandUpdates = true;
            }
        }
        if (!hasCommandUpdates) doc.remove("commands");

        bool hasInfoUpdates = false;
        JsonArray iArray = doc["information"].to<JsonArray>();
        for (auto& i : informationList) {
            if (i.needsSync) {
                JsonObject obj = iArray.add<JsonObject>();
                obj["source"] = i.source;
                obj["id"] = i.id;
                obj["value"] = i.value;
                if (i.explanation.length() > 0) obj["explanation"] = i.explanation;

                i.needsSync = false;
                hasInfoUpdates = true;
            }
        }
        if (!hasInfoUpdates) doc.remove("information");

        JsonObject meta = doc["metadata"].to<JsonObject>();
        meta["version"] = 1;
        meta["message-number"] = messageNumber++;

        if (sendPasswordResultSync) {
            meta["password-correct"] = lastPasswordResult;
            sendPasswordResultSync = false;
        } else if (systemPassword.length() == 0 || isPasswordAuthenticated) {
            meta["password-correct"] = true;
        }

        if (passwordHint.length() > 0) {
            meta["hint"] = passwordHint;
        }

        sendConfigPayload(doc);
    }

    xSemaphoreGiveRecursive(dataMutex);
}