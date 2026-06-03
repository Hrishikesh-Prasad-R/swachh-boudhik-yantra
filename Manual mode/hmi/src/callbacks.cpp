#include "callbacks.hpp"
#include "system_state.hpp"
#include "serial_comm.hpp"
#include "logger.hpp"
#include "gui.hpp"

#include <string>
#include <cstring>

// Movement direction state
MoveDir g_move_dir = DIR_NONE;

// Speed level names (matching gui_teleop_node.cpp)
// NUM_SPEED_LEVELS defined in gui.hpp

// ---- Movement state machine ----

void stop_movement() {
    g_move_dir = DIR_NONE;
    g_logger.hmi(LogLevel::INFO, "Movement released");
    g_logger.jetson(LogLevel::INFO, "Processing: MOVE:STOP");
    g_serial.send_command("MOVE:STOP");
    g_system_state.status = "Stopped";
    g_system_state.moving = false;
    update_status();
}

void on_move_pressed(GtkGestureClick*, int, double, double, gpointer data) {
    if (g_system_state.emergency_stop) {
        g_logger.hmi(LogLevel::ERROR, "Move blocked — emergency stop active");
        return;
    }
    if (g_system_state.autonomous_mode) {
        g_logger.hmi(LogLevel::ERROR, "Move blocked — autonomous mode active");
        return;
    }

    MoveDir dir = static_cast<MoveDir>(GPOINTER_TO_INT(data));
    g_move_dir = dir;

    const char* names[] = {"", "Forward", "Backward", "Left", "Right"};
    const char* cmds[]  = {"", "MOVE:FORWARD", "MOVE:BACKWARD", "MOVE:LEFT", "MOVE:RIGHT"};

    g_logger.hmi(LogLevel::INFO, std::string("User pressed: ") + names[dir]);
    g_logger.jetson(LogLevel::INFO, std::string("Processing: ") + cmds[dir]);
    g_serial.send_command(cmds[dir]);

    g_system_state.status = std::string("Moving ") + names[dir];
    g_system_state.moving = true;
    g_logger.jetson(LogLevel::SUCCESS, std::string(names[dir]) + " — command processed");
    update_status();
}

void on_move_released(GtkGestureClick*, int, double, double, gpointer) {
    stop_movement();
}

void on_move_cancelled(GtkGestureClick*, gpointer) {
    stop_movement();
}

void on_stop(GtkWidget*, gpointer) {
    if (g_system_state.emergency_stop) return;
    g_logger.hmi(LogLevel::INFO, "User pressed: Stop");
    stop_movement();
}

// ---- Emergency stop ----

void on_estop(GtkWidget*, gpointer) {
    g_logger.hmi(LogLevel::INFO, "User pressed: EMERGENCY STOP");
    g_logger.jetson(LogLevel::INFO, "Processing EMERGENCY STOP — disabling all systems");

    g_system_state.emergency_stop = true;
    g_system_state.vacuum_active = false;
    g_system_state.arm_active = false;
    g_system_state.wiper_active = false;
    g_system_state.uv_active = false;
    g_system_state.autonomous_mode = false;
    g_system_state.moving = false;
    g_move_dir = DIR_NONE;
    g_system_state.status = "EMERGENCY STOP";

    g_serial.send_command("ESTOP");

    gtk_button_set_label(GTK_BUTTON(g_widgets.vacuum_btn), "Vacuum");
    gtk_button_set_label(GTK_BUTTON(g_widgets.arm_btn), "Arm");
    gtk_button_set_label(GTK_BUTTON(g_widgets.wiper_btn), "Wiper");
    gtk_button_set_label(GTK_BUTTON(g_widgets.uv_btn), "UV");
    gtk_button_set_label(GTK_BUTTON(g_widgets.auto_btn), "Auto");

    g_logger.jetson(LogLevel::SUCCESS, "Emergency stop applied — all systems disabled");
    update_status();
}

void on_reset(GtkWidget*, gpointer) {
    g_logger.hmi(LogLevel::INFO, "User pressed: Reset");
    g_logger.jetson(LogLevel::INFO, "Processing RESET");

    g_system_state.emergency_stop = false;
    g_system_state.status = "System Ready";

    g_serial.send_command("RESET");

    g_logger.jetson(LogLevel::SUCCESS, "Emergency stop cleared");
    update_status();
}

// ---- Component toggles ----

void on_vacuum(GtkWidget *w, gpointer) {
    if (g_system_state.emergency_stop) {
        g_logger.hmi(LogLevel::ERROR, "Vacuum blocked — emergency stop active");
        return;
    }
    g_system_state.vacuum_active = !g_system_state.vacuum_active;
    std::string state = g_system_state.vacuum_active ? "ON" : "OFF";

    g_logger.hmi(LogLevel::INFO, "User pressed: Vacuum → " + state);
    g_logger.jetson(LogLevel::INFO, "Processing: VACUUM:" + state);

    gtk_button_set_label(GTK_BUTTON(w),
        g_system_state.vacuum_active ? "Vacuum [ON]" : "Vacuum");
    g_serial.send_command("VACUUM:" + state);
    g_system_state.status = "Vacuum " + state;
    g_logger.jetson(LogLevel::SUCCESS, "Vacuum " + state + " — command processed");
    update_status();
}

void on_arm(GtkWidget *w, gpointer) {
    if (g_system_state.emergency_stop) {
        g_logger.hmi(LogLevel::ERROR, "Arm blocked — emergency stop active");
        return;
    }
    g_system_state.arm_active = !g_system_state.arm_active;
    std::string state = g_system_state.arm_active ? "ON" : "OFF";

    g_logger.hmi(LogLevel::INFO, "User pressed: Arm → " + state);
    g_logger.jetson(LogLevel::INFO, "Processing: ARM:" + state);

    gtk_button_set_label(GTK_BUTTON(w),
        g_system_state.arm_active ? "Arm [ON]" : "Arm");
    g_serial.send_command("ARM:" + state);
    g_system_state.status = "Arm " + state;
    g_logger.jetson(LogLevel::SUCCESS, "Arm " + state + " — command processed");
    update_status();
}

void on_wiper(GtkWidget *w, gpointer) {
    if (g_system_state.emergency_stop) {
        g_logger.hmi(LogLevel::ERROR, "Wiper blocked — emergency stop active");
        return;
    }
    g_system_state.wiper_active = !g_system_state.wiper_active;
    std::string state = g_system_state.wiper_active ? "ON" : "OFF";

    g_logger.hmi(LogLevel::INFO, "User pressed: Wiper → " + state);
    g_logger.jetson(LogLevel::INFO, "Processing: WIPER:" + state);

    gtk_button_set_label(GTK_BUTTON(w),
        g_system_state.wiper_active ? "Wiper [ON]" : "Wiper");
    g_serial.send_command("WIPER:" + state);
    g_system_state.status = "Wiper " + state;
    g_logger.jetson(LogLevel::SUCCESS, "Wiper " + state + " — command processed");
    update_status();
}

void on_uv(GtkWidget *w, gpointer) {
    if (g_system_state.emergency_stop) {
        g_logger.hmi(LogLevel::ERROR, "UV blocked — emergency stop active");
        return;
    }
    g_system_state.uv_active = !g_system_state.uv_active;
    std::string state = g_system_state.uv_active ? "ON" : "OFF";

    g_logger.hmi(LogLevel::INFO, "User pressed: UV → " + state);
    g_logger.jetson(LogLevel::INFO, "Processing: UV:" + state);

    gtk_button_set_label(GTK_BUTTON(w),
        g_system_state.uv_active ? "UV [ON]" : "UV");
    g_serial.send_command("UV:" + state);
    g_system_state.status = "UV " + state;
    g_logger.jetson(LogLevel::SUCCESS, "UV " + state + " — command processed");
    update_status();
}

void on_auto_toggle(GtkWidget *w, gpointer) {
    if (g_system_state.emergency_stop) {
        g_logger.hmi(LogLevel::ERROR, "Auto blocked — emergency stop active");
        return;
    }
    g_system_state.autonomous_mode = !g_system_state.autonomous_mode;
    std::string state = g_system_state.autonomous_mode ? "ON" : "OFF";

    g_logger.hmi(LogLevel::INFO, "User pressed: Auto → " + state);
    g_logger.jetson(LogLevel::INFO, "Processing: AUTO:" + state);

    gtk_button_set_label(GTK_BUTTON(w),
        g_system_state.autonomous_mode ? "Auto [ON]" : "Auto");
    g_serial.send_command("AUTO:" + state);

    if (g_system_state.autonomous_mode) {
        g_system_state.status = "Autonomous Mode";
    } else {
        g_system_state.status = "Manual Mode";
    }
    g_logger.jetson(LogLevel::SUCCESS, "Auto " + state + " — command processed");
    update_status();
}

// ---- Speed level ----

void on_speed_select(GtkWidget*, gpointer data) {
    int level = GPOINTER_TO_INT(data);
    g_system_state.speed_level = level + 1;  // 0-indexed to 1-indexed

    g_logger.hmi(LogLevel::INFO, "User selected: Speed level " + std::to_string(level + 1));
    g_serial.send_command("SPEED:" + std::to_string(level + 1));

    update_speed_buttons();
}

// ---- Serial polling timer (20Hz) ----

static void parse_status(const std::string& msg) {
    // Parse: STATUS:VAC=1,ARM=0,WPR=0,UV=0,AUTO=0,ESTOP=0,MOVE=1,SPD=5
    // (Arduino sends this every 1s — we just update the display)
    // We don't override local HMI state, just log it
    g_logger.arduino(LogLevel::INFO, "STATUS ← " + msg);
}

gboolean serial_poll_tick(gpointer) {
    if (!g_serial.is_connected()) return TRUE;

    // Non-blocking read any pending Arduino messages
    std::string line = g_serial.read_nonblocking();
    while (!line.empty()) {
        if (line.find("STATUS:") == 0) {
            parse_status(line);
        } else if (line.find("ACK:") == 0) {
            g_logger.arduino(LogLevel::SUCCESS, "ACK ← " + line);
        } else if (line.find("ERR:") == 0) {
            g_logger.arduino(LogLevel::ERROR, "ERR ← " + line);
        } else if (line.find("SWACCH:") == 0) {
            g_logger.arduino(LogLevel::INFO, "Arduino: " + line);
        } else {
            g_logger.arduino(LogLevel::INFO, "RX ← " + line);
        }
        line = g_serial.read_nonblocking();
    }

    // Update telemetry display
    update_telemetry();

    return TRUE;
}

// ---- Battery simulation timer ----

gboolean battery_tick(gpointer) {
    if (g_system_state.battery_level > 0) {
        if (g_system_state.vacuum_active || g_system_state.arm_active ||
            g_system_state.wiper_active || g_system_state.uv_active) {
            g_system_state.battery_level--;
        }
    }
    update_status();
    return TRUE;
}
