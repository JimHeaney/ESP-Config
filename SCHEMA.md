This document defines the JSON serial protocol used for communication between an ESP32 running `ESPConfig` and a host application over standard 115200 8N1 serial\[cite: 3].



Messages sent from the device are prefixed with `\[config]`\[cite: 3, 5]:

```text

\[config] {"metadata":{"version":1},"questions":\[...]}

```



\---



\*\*Device-to-Host Payload\*\*



The root payload transmitted by the device can contain up to four top-level arrays/objects\[cite: 3]:



\### 1. `questions`



Defines dynamic user inputs\[cite: 3].



| Field | Type | Description |

| :--- | :--- | :--- |

| `id` | String | Identifier unique to the source\[cite: 3]. |

| `source` | String | Originating subsystem or device\[cite: 3]. |

| `category` | String | UI grouping category\[cite: 3]. |

| `type` | String | `"choice"`, `"selection"`, `"integer"`, or `"string"`\[cite: 3]. |

| `prompt` | String | Label/question text presented to user\[cite: 3]. |

| `current` | String/Array | Current stored value\[cite: 3]. |

| `options` | Array | Option strings for `"choice"` or `"selection"` types\[cite: 3]. |

| `lower-limit`| Integer | Minimum value for `"integer"` type\[cite: 3]. |

| `upper-limit`| Integer | Maximum value for `"integer"` type\[cite: 3]. |

| `max-length` | Integer | Max characters allowed for `"string"` type\[cite: 3]. |

| `message` | String | Feedback text associated with the question\[cite: 3]. |

| `protected` | Boolean | `true` if password authentication is required\[cite: 3]. |

| `unavailable`| Boolean | `true` if element should be greyed out/disabled in host UI\[cite: 5]. |



\---



\### 2. `commands`



Defines executable actions\[cite: 3].



| Field | Type | Description |

| :--- | :--- | :--- |

| `id` | String | Unique action identifier\[cite: 3]. |

| `source` | String | Subsystem origin\[cite: 3]. |

| `category` | String | UI grouping category\[cite: 3]. |

| `type` | String | `"button"`, `"latch"`, or `"string"`\[cite: 3]. |

| `title` | String | Button/control label text\[cite: 3]. |

| `pop-up` | String | Confirmation dialog text shown prior to execution\[cite: 3]. |

| `message` | String | Status message string\[cite: 3]. |

| `imply-end` | Boolean | `true` if action causes device restart or disconnection\[cite: 3]. |

| `protected` | Boolean | Requires password authentication\[cite: 3]. |

| `unavailable`| Boolean | `true` if element should be greyed out/disabled\[cite: 5]. |



\---



\### 3. `information`



Read-only diagnostic metrics\[cite: 3].



| Field | Type | Description |

| :--- | :--- | :--- |

| `id` | String | Unique item identifier\[cite: 3]. |

| `source` | String | Subsystem origin\[cite: 3]. |

| `category` | String | UI grouping category\[cite: 3, 5]. |

| `title` | String | UI display label\[cite: 3]. |

| `value` | String | Read-only value string\[cite: 3]. |

| `explanation`| String | Detailed tooltip or subtext\[cite: 3]. |



\---



\### 4. `metadata`



Protocol state and auth verification\[cite: 3].



| Field | Type | Description |

| :--- | :--- | :--- |

| `version` | Integer | Protocol schema version\[cite: 3]. |

| `message-number` | Integer | Incremental counter for frame tracking\[cite: 3]. |

| `password-correct` | Boolean | Auth state verification\[cite: 3]. |

| `hint` | String | Optional hint text for password authentication\[cite: 3]. |



\---



\*\*Host-to-Device Payload\*\*



Sent by the host application to update answers, execute commands, or send credentials\[cite: 3].



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



Session initiation and heartbeat checks\[cite: 3]:



\* \*\*Session Start (Host → Device)\*\*: `{"operation":"start"}`\[cite: 3]

\* \*\*Heartbeat Ping (Host → Device)\*\*: `{"operation":"check"}`\[cite: 3]

\* \*\*Acknowledgment (Device → Host)\*\*: `{"operation":"ack","metadata":{...}}`\[cite: 3, 5]

