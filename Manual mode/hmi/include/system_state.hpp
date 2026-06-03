#ifndef SYSTEM_STATE_HPP
#define SYSTEM_STATE_HPP

#include <string>

struct SystemState {
    bool vacuum_active = false;
    bool arm_active = false;
    bool wiper_active = false;
    bool uv_active = false;
    bool autonomous_mode = false;
    bool emergency_stop = false;
    bool ai_detection = true;
    bool moving = false;
    int battery_level = 100;
    int speed_level = 5;           // 1-9 speed level
    std::string status = "System Ready";
};

extern SystemState g_system_state;

#endif // SYSTEM_STATE_HPP
