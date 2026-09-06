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

void ESPConfig::begin(const String& password, const String& hint) {
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

void ESPConfig::reserve(size_t questionsCount, size_t commandsCount, size_t infoCount) {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);
    if (questionsCount > 0) questions.reserve(questionsCount);
    if (commandsCount > 0) commands.reserve(commandsCount);
    if (infoCount > 0) informationList.reserve(infoCount);
    xSemaphoreGiveRecursive(dataMutex);
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

void ESPConfig::addChoiceQuestion(const String& source, const String& id, const String& category, const String& prompt,
                                  const String& defaultValue, const std::vector<String>& options,
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

void ESPConfig::addSelectionQuestion(const String& source, const String& id, const String& category, const String& prompt,
                                     const String& defaultValue, const std::vector<String>& options,
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

void ESPConfig::addSelectionQuestion(const String& source, const String& id, const String& category, const String& prompt,
                                     const std::vector<String>& defaultValues, const std::vector<String>& options,
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

void ESPConfig::addIntegerQuestion(const String& source, const String& id, const String& category, const String& prompt,
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

void ESPConfig::addStringQuestion(const String& source, const String& id, const String& category, const String& prompt,
                                 const String& defaultValue, int maxLength,
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

void ESPConfig::updateQuestion(const String& source, const String& id, const String& value, const String& message) {
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

void ESPConfig::updateQuestion(const String& source, const String& id, const std::vector<String>& values, const String& message) {
    JsonDocument doc;
    JsonArray arr = doc.to<JsonArray>();
    for (const auto& val : values) {
        arr.add(val);
    }
    String serializedVal;
    serializeJson(arr, serializedVal);
    updateQuestion(source, id, serializedVal, message);
}

void ESPConfig::updateQuestionOptions(const String& source, const String& id, const std::vector<String>& options, const String& currentValue) {
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

void ESPConfig::updateQuestionAvailability(const String& source, const String& id, bool unavailable) {
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

void ESPConfig::addButtonCommand(const String& source, const String& id, const String& category, const String& title,
                                 ButtonCommandCallback callback, const String& popup,
                                 const String& message, bool implyEnd, bool protectedVal, bool unavailable) {
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

void ESPConfig::addLatchCommand(const String& source, const String& id, const String& category, const String& title,
                                ButtonCommandCallback callback, const String& popup,
                                const String& message, bool implyEnd, bool protectedVal, bool unavailable) {
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

void ESPConfig::addStringCommand(const String& source, const String& id, const String& category, const String& title,
                                 StringCommandCallback callback, int maxLength, const String& popup,
                                 const String& message, bool implyEnd, bool protectedVal, bool unavailable) {
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

void ESPConfig::updateCommand(const String& source, const String& id, const String& message) {
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

void ESPConfig::updateCommandAvailability(const String& source, const String& id, bool unavailable) {
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

void ESPConfig::addInformation(const String& source, const String& id, const String& category, const String& title, const String& value, const String& explanation) {
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

void ESPConfig::updateInformation(const String& source, const String& id, const String& value, const String& explanation) {
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
// JSON HELPERS
// -----------------------------------------------------------------------------

void ESPConfig::populateMetadata(JsonDocument& doc, bool includePasswordResult) {
    JsonObject meta = doc["metadata"].to<JsonObject>();
    meta["version"] = 1;
    meta["message-number"] = messageNumber++;

    if (includePasswordResult) {
        meta["password-correct"] = lastPasswordResult;
    } else if (systemPassword.length() == 0 || isPasswordAuthenticated) {
        meta["password-correct"] = true;
    }

    if (passwordHint.length() > 0) {
        meta["hint"] = passwordHint;
    }
}

JsonArray ESPConfig::getOrCreateArray(JsonDocument& doc, const char* key) {
    if (doc[key].is<JsonArray>()) {
        return doc[key].as<JsonArray>();
    }
    return doc[key].to<JsonArray>();
}

void ESPConfig::buildQuestionJson(const ConfigQuestion& q, JsonObject& obj, bool fullState) {
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

    if (fullState && q.hasLimits) {
        obj["lower-limit"] = q.lowerLimit;
        obj["upper-limit"] = q.upperLimit;
    }

    if (q.message.length() > 0) obj["message"] = q.message;

    if (fullState && q.maxLength > 0) {
        obj["max-length"] = q.maxLength;
    }

    if (q.protectedVal) obj["protected"] = true;

    bool effectiveUnavailable = q.unavailable || (q.protectedVal && systemPassword.length() > 0 && !isPasswordAuthenticated);
    obj["unavailable"] = effectiveUnavailable;
}

void ESPConfig::buildCommandJson(const ConfigCommand& c, JsonObject& obj, bool fullState) {
    obj["source"] = c.source;
    obj["id"] = c.id;

    if (fullState) {
        obj["category"] = c.category;
        obj["type"] = c.type;
        obj["title"] = c.title;

        if (c.popup.length() > 0) obj["pop-up"] = c.popup;
        if (c.message.length() > 0) obj["message"] = c.message;
        if (c.maxLength > 0) obj["max-length"] = c.maxLength;
        if (c.implyEnd) obj["imply-end"] = true;
        if (c.protectedVal) obj["protected"] = true;
    } else {
        if (c.message.length() > 0) obj["message"] = c.message;
    }

    bool effectiveUnavailable = c.unavailable || (c.protectedVal && systemPassword.length() > 0 && !isPasswordAuthenticated);
    obj["unavailable"] = effectiveUnavailable;
}

void ESPConfig::buildInformationJson(const ConfigInformation& i, JsonObject& obj, bool fullState) {
    obj["source"] = i.source;
    obj["id"] = i.id;

    if (fullState) {
        if (i.category.length() > 0) obj["category"] = i.category;
        obj["title"] = i.title;
    }

    obj["value"] = i.value;
    if (i.explanation.length() > 0) obj["explanation"] = i.explanation;
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
            isStarted = true;
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
    for (auto& q : questions) q.needsSync = false;
    for (auto& c : commands) c.needsSync = false;
    for (auto& i : informationList) i.needsSync = false;
    sendPasswordResultSync = false;

    JsonDocument doc;
    JsonDocument tempDoc;
    populateMetadata(doc);

    auto flushIfNeeded = [&](size_t itemSize) {
        if (doc.containsKey("questions") || doc.containsKey("commands") || doc.containsKey("information")) {
            if (measureJson(doc) + itemSize + 15 > MAX_PAYLOAD_SIZE) {
                sendConfigPayload(doc);
                doc.clear();
                populateMetadata(doc);
            }
        }
    };

    // Questions
    for (const auto& q : questions) {
        tempDoc.clear();
        JsonObject tempObj = tempDoc.to<JsonObject>();
        buildQuestionJson(q, tempObj, true);

        flushIfNeeded(measureJson(tempDoc));

        JsonArray qArray = getOrCreateArray(doc, "questions");
        JsonObject obj = qArray.add<JsonObject>();
        buildQuestionJson(q, obj, true);
    }

    // Commands
    for (const auto& c : commands) {
        tempDoc.clear();
        JsonObject tempObj = tempDoc.to<JsonObject>();
        buildCommandJson(c, tempObj, true);

        flushIfNeeded(measureJson(tempDoc));

        JsonArray cArray = getOrCreateArray(doc, "commands");
        JsonObject obj = cArray.add<JsonObject>();
        buildCommandJson(c, obj, true);
    }

    // Information
    for (const auto& i : informationList) {
        tempDoc.clear();
        JsonObject tempObj = tempDoc.to<JsonObject>();
        buildInformationJson(i, tempObj, true);

        flushIfNeeded(measureJson(tempDoc));

        JsonArray iArray = getOrCreateArray(doc, "information");
        JsonObject obj = iArray.add<JsonObject>();
        buildInformationJson(i, obj, true);
    }

    sendConfigPayload(doc);
}

void ESPConfig::sendAck() {
    JsonDocument doc;
    doc["operation"] = "ack";
    populateMetadata(doc);
    sendConfigPayload(doc);
}

void ESPConfig::sendConfigPayload(JsonDocument& doc) {
    // Write directly to Serial output stream without allocating an intermediate String buffer
    Serial.print("[config] ");
    serializeJson(doc, Serial);
    Serial.println();
}

void ESPConfig::update() {
    xSemaphoreTakeRecursive(dataMutex, portMAX_DELAY);

    if (!isStarted) {
        xSemaphoreGiveRecursive(dataMutex);
        return;
    }

    bool hasUpdates = sendPasswordResultSync;
    if (!hasUpdates) {
        for (const auto& q : questions) {
            if (q.needsSync) { hasUpdates = true; break; }
        }
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
        JsonDocument tempDoc;
        bool passSync = sendPasswordResultSync;
        populateMetadata(doc, passSync);
        sendPasswordResultSync = false;

        auto flushIfNeeded = [&](size_t itemSize) {
            if (doc.containsKey("questions") || doc.containsKey("commands") || doc.containsKey("information")) {
                if (measureJson(doc) + itemSize + 15 > MAX_PAYLOAD_SIZE) {
                    sendConfigPayload(doc);
                    doc.clear();
                    populateMetadata(doc, false);
                }
            }
        };

        for (auto& q : questions) {
            if (q.needsSync) {
                tempDoc.clear();
                JsonObject tempObj = tempDoc.to<JsonObject>();
                buildQuestionJson(q, tempObj, false);

                flushIfNeeded(measureJson(tempDoc));

                JsonArray qArray = getOrCreateArray(doc, "questions");
                JsonObject obj = qArray.add<JsonObject>();
                buildQuestionJson(q, obj, false);

                q.needsSync = false;
            }
        }

        for (auto& c : commands) {
            if (c.needsSync) {
                tempDoc.clear();
                JsonObject tempObj = tempDoc.to<JsonObject>();
                buildCommandJson(c, tempObj, false);

                flushIfNeeded(measureJson(tempDoc));

                JsonArray cArray = getOrCreateArray(doc, "commands");
                JsonObject obj = cArray.add<JsonObject>();
                buildCommandJson(c, obj, false);

                c.needsSync = false;
            }
        }

        for (auto& i : informationList) {
            if (i.needsSync) {
                tempDoc.clear();
                JsonObject tempObj = tempDoc.to<JsonObject>();
                buildInformationJson(i, tempObj, false);

                flushIfNeeded(measureJson(tempDoc));

                JsonArray iArray = getOrCreateArray(doc, "information");
                JsonObject obj = iArray.add<JsonObject>();
                buildInformationJson(i, obj, false);

                i.needsSync = false;
            }
        }

        if (doc.containsKey("questions") || doc.containsKey("commands") || doc.containsKey("information") || passSync) {
            sendConfigPayload(doc);
        }
    }

    xSemaphoreGiveRecursive(dataMutex);
}