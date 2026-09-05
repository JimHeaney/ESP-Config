This document defines the JSON serial protocol used for communication between an ESP32 running `ESPConfig` and a host application over standard 115200 8N1 serial.



Messages sent from the device are prefixed with `\[config]`:

```text

\[config] {"metadata":{"version":1},"questions":\[...]}

```



\---



\*\*Device-to-Host Payload\*\*



The root payload transmitted by the device can contain up to four top-level arrays/objects:



\### 1. `questions`



Defines dynamic user inputs.



| Field | Type | Description |

| :--- | :--- | :--- |

| `id` | String | Identifier unique to the source. |

| `source` | String | Originating subsystem or device. |

| `category` | String | UI grouping category. |

| `type` | String | `"choice"`, `"selection"`, `"integer"`, or `"string"`. |

| `prompt` | String | Label/question text presented to user. |

| `current` | String/Array | Current stored value. |

| `options` | Array | Option strings for `"choice"` or `"selection"` types. |

| `lower-limit`| Integer | Minimum value for `"integer"` type. |

| `upper-limit`| Integer | Maximum value for `"integer"` type. |

| `max-length` | Integer | Max characters allowed for `"string"` type. |

| `message` | String | Feedback text associated with the question. |

| `protected` | Boolean | `true` if password authentication is required. |

| `unavailable`| Boolean | `true` if element should be greyed out/disabled in host UI. |



\---



\### 2. `commands`



Defines executable actions.



| Field | Type | Description |

| :--- | :--- | :--- |

| `id` | String | Unique action identifier. |

| `source` | String | Subsystem origin. |

| `category` | String | UI grouping category. |

| `type` | String | `"button"`, `"latch"`, or `"string"`. |

| `title` | String | Button/control label text. |

| `pop-up` | String | Confirmation dialog text shown prior to execution. |

| `message` | String | Status message string. |

| `imply-end` | Boolean | `true` if action causes device restart or disconnection. |

| `protected` | Boolean | Requires password authentication. |

| `unavailable`| Boolean | `true` if element should be greyed out/disabled. |



\---



\### 3. `information`



Read-only diagnostic metrics.



| Field | Type | Description |

| :--- | :--- | :--- |

| `id` | String | Unique item identifier. |

| `source` | String | Subsystem origin. |

| `category` | String | UI grouping category. |

| `title` | String | UI display label. |

| `value` | String | Read-only value string. |

| `explanation`| String | Detailed tooltip or subtext. |



\---



\### 4. `metadata`



Protocol state and auth verification.



| Field | Type | Description |

| :--- | :--- | :--- |

| `version` | Integer | Protocol schema version. |

| `message-number` | Integer | Incremental counter for frame tracking. |

| `password-correct` | Boolean | Auth state verification. |

| `hint` | String | Optional hint text for password authentication. |



\---



\*\*Host-to-Device Payload\*\*



Sent by the host application to update answers, execute commands, or send credentials.



```json

{

&#x20; "answers": \[

&#x20;   {

&#x20;     "source": "WiFi",

&#x20;     "id": "wifi\_password",

&#x20;     "answer": "SecretPass123"

&#x20;   }

&#x20; ],

&#x20; "commands": \[

&#x20;   {

&#x20;     "source": "WiFi",

&#x20;     "id": "connect\_wifi",

&#x20;     "input": true

&#x20;   }

&#x20; ],

&#x20; "metadata": {

&#x20;   "password": "admin123"

&#x20; }

}

```



\---



\*\*Operation Handshakes\*\*



Session initiation and heartbeat checks:



\* \*\*Session Start (Host → Device)\*\*: `{"operation":"start"}`

\* \*\*Heartbeat Ping (Host → Device)\*\*: `{"operation":"check"}`

\* \*\*Acknowledgment (Device → Host)\*\*: `{"operation":"ack","metadata":{...}}`

