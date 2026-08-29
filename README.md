# ESP-Config

This library allows you to send configuration settings and commands to an ESP32 (and it to send information back) from your computer. The structure is open-ended, allowing the same software to work with any ESP32 project, and for configuration options to be created dynamically based on the project's needs.

All information is passed back-and-forth in JSON payloads, with all information for the question to be presented to the end-user being included inside the schema. 

## Device to Software Payload

A JSON payload from device to software generally has 4 top-level keys:
* questions: Contains structured question content prompting the user for information that changes how the system operates.
* commands: Contains available commands that can be sent to the system, for the system to take an action.
* information: Diagnostics, statistical, etc. data that can be displayed to the user 
* metadata: Information related to this communication itself (requesting questions again, a checksum hash, etc.)

### Questions

Questions are meant for the user to give some information to a device that changes how it operates. Questions are meant to be answered, and then have a batch "submit" button to send in all answers. A question is contained within an object, that is within the "questions" top-level array. 

All keys are optional, if not included it is intended to be treated as if it is not pertinent. Keys can be sent again and should be treated as an immediate update of the content if different. 

* "id" - Identify the question by a unique name, to refer to when answers are returned or when otherwise communicating regarding the question.
* "source" - what device in an ACS deployment generated the question. "Core" for anything from the core, but other devices in a deployment that are communication-capable can send questions to the Core to present to the end-user for more advanced configuration. Source is also used with "id" to identify a question, in case multiple devices on the deployment accidentally use the same "id" for their questions.
* "category" - allows questions to be organized into categories by the user-facing software, for more logical flow.
*  "type" - determines how the question can be answered:
  * "choice" - multiple choice questions (i.e. one of the X options must be chosen, only one option can be chosen)
  * "selection" - any number of the options (including none) can be selected
  * "integer" - accepts only whole-number values
  * "string" - accepts plaintext submission
* Depending on the "type" sent, different limits can be sent as well. While the device will do input checking, the software can implement these limitations to skip the need to communicate with the device and/or to display the limitation graphically;
  * "max-length" - for "string" type questions, any input longer than this should not be accepted. 
  * "upper-limit" - for "integer" type questions, the maximum value that can be accepted.
  * "lower-limit" - for "integer" type questions, the minimum value that can be accepted.
* "prompt" - the actual question being sent to prompt the user.
* "options" - for "choice" or "selection" type questions, this array contains the allowable options.
* "current" - the current value of the question, if applicable. If the question type is "selection", it is an array (even if only 1 or no choices currently).
* "message" - a message to display in regards to this question. How this is used is up to the device. For instance, it can be used to give generic information about the question, or to send a confirmation/denial about the submitted answer.
* "protected" - boolean, if true, requires a password to be attached with the response payload for it to be accepted. See "metadata" for more info.

Example Question: 

```
{
	"id":"wifi-ssid",
	"source":"Core",
	"category":"Network",
	"type":"string",
	"max-length":"32",
	"prompt":"Wi-Fi SSID:",
	"current":"RIT-WiFi",
	"message":"",
	"protected":true
}
```

### Commands

Commands are meant for the user to make the device do something, rather than configuring it to act in a way (what questions are for). Commands are meant to be actioned immediately.

Many of the standard keys from "questions" are re-used here: "id", "source", "category", "prompt", "options", "protected".

Command-specific keys:
* "type" - determines how this is presented to the user:
  * "button" - a single button to press to execute an action. The software also reports when the user stops pressing the button, allowing for "press and hold" logic, if the device desires.
  * "latch" - a single button to press to execute an action. Once pressed, the button remains in the pressed "position" until the user presses it again. 
  * "string" - an arbitrary plaintext entry (can have the same "max-length" limitation as the "string" question)
* "imply-end" - boolean, if true it implies that sending this command will cause the device to restart, so we should expect an end to this session.
* "title" - What to call the command function
* "message" - displays a message for the user, can be used by the device to send confirmations, additional information, etc.
* "pop-up" - Once a command is submitted, this text can be displayed in a pop-up to confirm the intended action, with the options to "Proceed" (execute) or "Cancel" (go back).


Example Command:
 
```
{
	"id":"restart",
	"source":"Core",
	"category":"Device",
	"type":"button",
	"imply-end":true,
	"title":"Restart Device",
	"pop-up":"Are you sure? This will immediately restart the device"
}
```

### Information

Information is meant to display useful information about the system to the end-user, that may be useful for diagnostics or similar.

Information re-uses the following keys from "questions" section: "id", "source", "category"

Information-specific keys:
* "title" - the title to use to label the information
* "value" - the value of the information
* "explanation" - a further explanation of the information that can somehow be displayed to the user.

Example Information:

```
{
	"id":"wifi-mac",
	"source":"Core",
	"title":"Wi-Fi MAC Address",
	"value":"f2:63:f7:46:02:5e",
	"explanation":"The MAC address the device uses to identify itself when connecting via Wi-Fi. Different from the ethernet MAC!"
}
```

### Metadata

The metadata section contains information that can be used for the device and the software to communicate. Examples include:
* "hash" - If included, this is a SHA-256 hash of the entire message (with "hash":"0" in this key). This can be used to verify that the entire payload has been delivered as expected.
* "password-correct" - Indicates that a provided password is correct (if boolean true). It is not on the software to password-protect information, the device will take care of that.
* "hint" - An optional hint to display to the user about the password.
* "max-length" - Similar to questions, the password can have a max accepted length.
* "version" - integer representing the version of the API that is used, so both the device and software know they are on the same API formatting and expected keys. 
* "message-number" - increments by 1 for each time a message is sent, from 0. Used to catch missed messages, confirm message receipt, and/or request re-send messages.

Example Metadata:

```
{
	"hash":"a1b2c3d4",
	"password-correct":true,
	"hint":"Password is the Device ID found on the "Devices" page.",
	"version":1,
	"message-number":123,
}
```

## Software to Device Payload

The payload from the software to the device has 3 main categories:
* answers: responses to the questions
* commands: software telling the device to execute a command
* metadata: Information related to this communication itself (requesting questions again, a checksum hash, etc.)

### Answers

* "id" & "source" - same as the question, to identify what is being answered.
* "answer" - the response to the question. 
  * For "string" and "choice" questions, it is a string.
  * For "choice" questions, it is an array of strings.
  * For "integer" questions, it is an integer.
  * For "boolean" questions, it is a boolean. 

Example Answer:

```
{
	"id":"wifi-ssid",
	"source":"Core",
	"answer":"RIT-WiFi"
}
```

 ### Commands

* "id" & "source" - same as the command, to identify the origin.
* "input" - the input given by the user
  * For "button" and "latch" type commands, this a boolean, it is true when pressed, false when un-pressed
  * For "string" type commands this is the string as-entered.

Example Command:

```
{
	"id":"restart",
	"source":"Core",
	"input":true
}
```

### Metadata

Software-to-device communication uses the same hash verification method, message numbering, and version info as the device-to-software communication.

Other key:
* "password" - String of the password that was entered by a user.

## Operation Functions

Outside of the 2 major data messages, there is a 3rd "operation" function. This is used to initialize the communication. Communication is always initialized by the software, and an acknowledgement comes from the device to indicate it is the intended device before continuing. 

Operation is simply: 

```
{
	"operation":"start",
	"last":0,
	"max":1024
}
```

Values for "operation" are:
* "start" - sent by the software to the device to start the communication
* "check" - sent by either side to check if the other is still there.
* "ack" - sent in response to a "start" or "check". If not received within 1 second, try again. If it fails twice, assume end.
* "end" - sent by either side to end the communication.
* "cts" - sent by either side once it has finished ingesting a payload.

"last" contains the number of the last message, allowing for the catch of missed messages on the normal check-ack. It is not expected to be included in the start-ack or end messages.

"max" can be sent with the first "ack" from the device, to set a maximum JSON payload size. Anything more than that, and the computer should chunk it and send each part independently.

## Error Functions

If there is an error with a sent message (it is missed, the hash does not check out, etc.) then either side can report that  with;

```
{"error":[number]}
```

To tell the other side to retry sending.


## Serial Configuration

Communication will take place at 115200 buad rate, standard 8N1 serial. 

To help organize debug information, messages sent from the device must start with "[config] {..." to seperate them from other debug serial outputs coming from elsewhere in code.

## Example Exchange

This exchange demonstrates:
* Establish a connection
* Ask questions about the WiFi settings
* Send responses to the WiFi questions along with the password
* Command test the WiFi
* Keep the connection alive while we wait for a confirmation
* End the session

Software starts the connection:

```
{
    "operation":"start"
}
```

Device responds:

```
{
    "operation":"ack"
}
```

Device sends its questions, commands, and metadata:

```
{
    "questions": [
        {
            "id":"wifi-ssid",
            "category":"Network",
            "type":"string",
            "max-length":32,
            "prompt":"Enter the Wi-Fi SSID",
            "current":"Outdated-SSID",
            "protected":true
        },
        {
            "id":"wifi-password",
            "category":"Network",
            "type":"string",
            "max-length":32,
            "prompt":"Enter the Wi-Fi Password",
            "current":"(Not displayed for security reasons)",
            "protected":true
        }
    ],
    "commands": [
        {
            "id":"test-wifi",
            "category":"Network",
            "type":"button",
            "title":"Test Network Connection".
            "pop-up":"This may take several seconds as we attempt to ping google.com."
        }
    ],
    "information": [
        {
            "id":wifi-mac",
            "title":"Wi-Fi MAC Address",
            "value":"f2:63:f7:46:02:5e",
        },
        {
            "id":"network-status",
            "title":"Network Connection Status",
            "value":"DISCONNECTED",
            "explanation":"The network is not connected with error code -99, likely cannot find AP?"
        }
    ],
    "metadata": {
        "hash":"a1b2c3",
        "hint":"The password is the 'Device ID' printed on the sticker on the USB port",
        "version":1,
        "message-number":0
    }
}

```

While the user is entering their info, the software is constantly sending "check" messages to make sure the device is still there.

```
{
	"operation":"check",
	"last":0
}
```

And the device is responding regularly with:

```
{
	"operation":"ack",
	"last":0
}
```

After the user enters the Wi-Fi info and the password, the software sends back:

```
{
    "answers": [
        {
            "id":"wifi-ssid",
            "answer":"New-SSID"
        },
        {
            "id":"wifi-password",
            "answer":"The-New-Password"
        }
    ],
    "metadata":{
        "hash":"123ABC",
        "password":"Correct-Config-Password",
        "version":1,
        "message-number":0
    }
}

```

Once the settings are ingested and the password is matched, the device responds with messages affirming the settings:

```
{
    "questions": [
        {
            "id":"wifi-ssid",
            "message":"New Wi-Fi SSID saved.",
            "current":"New-SSID"
        },
        {
            "id":"wifi-password",
            "message":"New Wi-Fi password saved."
        }
    ],
    "metadata": {
        "hash":"4567",
        "password-correct":true,
        "version":1,
        "message-number:1
    }
}
```

The user then presses the "Test Network Connection" button:

```
{
    "commands": [
        {
            "id":test-wifi",
            "input":true
        }
    ],
    "metadata": {
        "hash":"1234",
        "version":1,
        "message-number:2
    }
}
```

Since the user immediately un-pressed the button, the software sends an un-press payload too:

```
{
    "commands": [
        {
            "id":test-wifi",
            "input":false
        }
    ],
    "metadata": {
        "hash":"1235",
        "version":1,
        "message-number:3
    }
}
```

Eventually, the device connects to the network. It sends a message to the command, but also updates the information.

```
{
    "commands": [
        {
            "id":"test-wifi",
            "message":"Test completed successfully! Pinged google.com with a latency of 100mS."
        }
    ],
    "information": [
        {
            "id":"network-status",
            "value":"CONNECTED",
            "explanation":""
        }
    ],
    "metadata": {
        "hash":"1256",
        "version":1,
        "message-number":2
    }
}
```

The user is happy with the result, so they shut down the software: 

```
{
    "operation":"end"
}
```
