/*
 * Swacch Robot — Arduino Motor Controller
 * ========================================
 * Aligned with the Jetson HMI serial protocol.
 *
 * Protocol: 115200 baud, 8N1, newline-terminated commands
 * Every command gets an ACK:<command> response.
 * Periodic STATUS messages sent every 1 second.
 *
 * Pin Mapping (your actual hardware):
 *   LEFT  MOTOR:  Throttle → Pin 5 (PWM),  Relay → Pin 7
 *   RIGHT MOTOR:  Throttle → Pin 6 (PWM),  Relay → Pin 8
 *
 * Speed Levels 1–9 map to PWM values:
 *   1=28, 2=57, 3=85, 4=113, 5=142, 6=170, 7=198, 8=227, 9=255
 */

// ===== PIN DEFINITIONS =====

int throttlePin1 = 5;   // Left motor PWM
int relayPin1    = 7;   // Left motor direction relay

int throttlePin2 = 6;   // Right motor PWM
int relayPin2    = 8;   // Right motor direction relay

// ===== CONFIGURATION =====

#define SERIAL_BAUD     115200
#define CMD_BUFFER_SIZE 64
#define STATUS_INTERVAL 1000   // ms between status updates

// Speed level to PWM mapping (1–9), minimum PWM = 80
const int SPEED_PWM[10] = {
    0,     // index 0 unused
    80,    // Level 1: Crawl  (~31%)
    102,   // Level 2: Slow   (~40%)
    124,   // Level 3: Gentle (~49%)
    146,   // Level 4: Medium (~57%)
    168,   // Level 5: Normal (~66%)  ← default
    190,   // Level 6: Fast   (~75%)
    212,   // Level 7: Faster (~83%)
    234,   // Level 8: Rush   (~92%)
    255    // Level 9: Max    (100%)
};

// ===== STATE =====

struct SystemState {
    bool vacuum_active;
    bool arm_active;
    bool wiper_active;
    bool uv_active;
    bool autonomous_mode;
    bool emergency_stop;
    bool moving;
    int  speed_level;     // 1–9
    int  current_pwm;     // actual PWM being sent
} state;

String commandBuffer = "";
unsigned long lastStatusUpdate = 0;

// ===== MOTOR FUNCTIONS =====

void stopMotors() {
    analogWrite(throttlePin1, 0);
    analogWrite(throttlePin2, 0);
    state.moving = false;
    state.current_pwm = 0;
}

void applySpeed() {
    if (state.moving) {
        state.current_pwm = SPEED_PWM[state.speed_level];
    } else {
        state.current_pwm = 0;
    }
}

void moveForward() {
    stopMotors();
    delay(50);

    // Both relays HIGH = forward
    digitalWrite(relayPin1, HIGH);
    digitalWrite(relayPin2, HIGH);
    delay(50);

    state.moving = true;
    applySpeed();
    analogWrite(throttlePin1, state.current_pwm);
    analogWrite(throttlePin2, state.current_pwm);
}

void moveBackward() {
    stopMotors();
    delay(50);

    // Both relays LOW = backward
    digitalWrite(relayPin1, LOW);
    digitalWrite(relayPin2, LOW);
    delay(50);

    state.moving = true;
    applySpeed();
    analogWrite(throttlePin1, state.current_pwm);
    analogWrite(throttlePin2, state.current_pwm);
}

void turnLeft() {
    stopMotors();
    delay(50);

    // Tank turn: left backward, right forward
    digitalWrite(relayPin1, LOW);
    digitalWrite(relayPin2, HIGH);
    delay(50);

    state.moving = true;
    applySpeed();
    analogWrite(throttlePin1, state.current_pwm);
    analogWrite(throttlePin2, state.current_pwm);
}

void turnRight() {
    stopMotors();
    delay(50);

    // Tank turn: left forward, right backward
    digitalWrite(relayPin1, HIGH);
    digitalWrite(relayPin2, LOW);
    delay(50);

    state.moving = true;
    applySpeed();
    analogWrite(throttlePin1, state.current_pwm);
    analogWrite(throttlePin2, state.current_pwm);
}

// ===== ACK HELPER =====

void sendAck(const String& command) {
    Serial.print("ACK:");
    Serial.println(command);
}

// ===== COMMAND PROCESSING =====

void processCommand(String cmd) {
    cmd.trim();
    cmd.toUpperCase();

    if (cmd.length() == 0) return;

    // Emergency stop — highest priority
    if (cmd == "ESTOP") {
        state.emergency_stop = true;
        stopMotors();
        state.vacuum_active = false;
        state.arm_active = false;
        state.wiper_active = false;
        state.uv_active = false;
        state.autonomous_mode = false;
        sendAck(cmd);
        return;
    }

    // Reset from emergency stop
    if (cmd == "RESET") {
        state.emergency_stop = false;
        stopMotors();
        sendAck(cmd);
        return;
    }

    // Block commands during emergency stop
    if (state.emergency_stop) {
        Serial.println("ERR:EMERGENCY_STOP_ACTIVE");
        return;
    }

    // Movement commands
    if (cmd == "MOVE:FORWARD") {
        moveForward();
        sendAck(cmd);
    }
    else if (cmd == "MOVE:BACKWARD") {
        moveBackward();
        sendAck(cmd);
    }
    else if (cmd == "MOVE:LEFT") {
        turnLeft();
        sendAck(cmd);
    }
    else if (cmd == "MOVE:RIGHT") {
        turnRight();
        sendAck(cmd);
    }
    else if (cmd == "MOVE:STOP") {
        stopMotors();
        sendAck(cmd);
    }

    // Speed control
    else if (cmd.startsWith("SPEED:")) {
        int level = cmd.substring(6).toInt();
        if (level >= 1 && level <= 9) {
            state.speed_level = level;
            // If motors are running, update speed immediately
            if (state.moving) {
                applySpeed();
                analogWrite(throttlePin1, state.current_pwm);
                analogWrite(throttlePin2, state.current_pwm);
            }
        }
        sendAck(cmd);
    }

    // Peripheral commands (no dedicated pins — just track state for HMI)
    else if (cmd == "VACUUM:ON")  { state.vacuum_active = true;  sendAck(cmd); }
    else if (cmd == "VACUUM:OFF") { state.vacuum_active = false; sendAck(cmd); }
    else if (cmd == "ARM:ON")     { state.arm_active = true;     sendAck(cmd); }
    else if (cmd == "ARM:OFF")    { state.arm_active = false;    sendAck(cmd); }
    else if (cmd == "WIPER:ON")   { state.wiper_active = true;   sendAck(cmd); }
    else if (cmd == "WIPER:OFF")  { state.wiper_active = false;  sendAck(cmd); }
    else if (cmd == "UV:ON")      { state.uv_active = true;      sendAck(cmd); }
    else if (cmd == "UV:OFF")     { state.uv_active = false;     sendAck(cmd); }

    // Auto mode
    else if (cmd == "AUTO:ON") {
        state.autonomous_mode = true;
        sendAck(cmd);
    }
    else if (cmd == "AUTO:OFF") {
        state.autonomous_mode = false;
        stopMotors();
        sendAck(cmd);
    }
    else if (cmd == "AI:ON" || cmd == "AI:OFF") {
        sendAck(cmd);
    }

    // Unknown command
    else {
        Serial.print("ERR:UNKNOWN_CMD:");
        Serial.println(cmd);
    }
}

// ===== STATUS REPORTING =====

void sendStatusUpdate() {
    Serial.print("STATUS:");
    Serial.print("VAC=");  Serial.print(state.vacuum_active ? "1" : "0");
    Serial.print(",ARM="); Serial.print(state.arm_active ? "1" : "0");
    Serial.print(",WPR="); Serial.print(state.wiper_active ? "1" : "0");
    Serial.print(",UV=");  Serial.print(state.uv_active ? "1" : "0");
    Serial.print(",AUTO=");Serial.print(state.autonomous_mode ? "1" : "0");
    Serial.print(",ESTOP=");Serial.print(state.emergency_stop ? "1" : "0");
    Serial.print(",MOVE=");Serial.print(state.moving ? "1" : "0");
    Serial.print(",SPD="); Serial.print(state.speed_level);
    Serial.print(",PWM="); Serial.println(state.current_pwm);
}

// ===== SETUP & LOOP =====

void setup() {
    pinMode(throttlePin1, OUTPUT);
    pinMode(relayPin1, OUTPUT);
    pinMode(throttlePin2, OUTPUT);
    pinMode(relayPin2, OUTPUT);

    // Safe initial state
    stopMotors();

    // Initialize state
    state.vacuum_active = false;
    state.arm_active = false;
    state.wiper_active = false;
    state.uv_active = false;
    state.autonomous_mode = false;
    state.emergency_stop = false;
    state.moving = false;
    state.speed_level = 5;     // Default: level 5 (Normal)
    state.current_pwm = 0;

    Serial.begin(SERIAL_BAUD);
    while (!Serial) { ; }

    Serial.println("SWACCH:READY");

    lastStatusUpdate = millis();
}

void loop() {
    // Read serial commands
    while (Serial.available() > 0) {
        char c = Serial.read();

        if (c == '\n' || c == '\r') {
            if (commandBuffer.length() > 0) {
                processCommand(commandBuffer);
                commandBuffer = "";
            }
        } else if (commandBuffer.length() < CMD_BUFFER_SIZE) {
            commandBuffer += c;
        } else {
            commandBuffer = "";
            Serial.println("ERR:CMD_TOO_LONG");
        }
    }

    // Periodic status update
    if (millis() - lastStatusUpdate > STATUS_INTERVAL) {
        sendStatusUpdate();
        lastStatusUpdate = millis();
    }
}