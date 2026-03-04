/**
 * Swacch Robot HMI — Final Entry Point
 * CLI args: --port <serial_port> --log-dir <path>
 */

#include "gui.hpp"
#include "system_state.hpp"
#include "serial_comm.hpp"
#include "logger.hpp"

#include <gtk/gtk.h>
#include <iostream>
#include <string>
#include <thread>
#include <chrono>

// Global system state
SystemState g_system_state;

static void activate(GtkApplication *app, gpointer user_data) {
    g_logger.jetson(LogLevel::INFO, "GTK application activated — creating HMI interface");
    create_hmi_interface(app);
}

int main(int argc, char *argv[]) {
    const char* serial_port = "/dev/ttyCH341USB0";
    std::string log_dir = "logs";

    // Parse CLI args
    for (int i = 1; i < argc; i++) {
        if (std::string(argv[i]) == "--port" && i + 1 < argc) {
            serial_port = argv[++i];
        } else if (std::string(argv[i]) == "--log-dir" && i + 1 < argc) {
            log_dir = argv[++i];
        }
    }

    // Initialize logger
    g_logger.init(log_dir);
    g_logger.jetson(LogLevel::INFO, "╔══════════════════════════════════════════╗");
    g_logger.jetson(LogLevel::INFO, "║    Swacch Robot HMI — Final Build        ║");
    g_logger.jetson(LogLevel::INFO, "╚══════════════════════════════════════════╝");
    g_logger.jetson(LogLevel::INFO, "Serial port: " + std::string(serial_port));
    g_logger.jetson(LogLevel::INFO, "Log directory: " + log_dir);

    // Connect to Arduino
    if (g_serial.connect(serial_port)) {
        g_logger.jetson(LogLevel::SUCCESS, "Arduino connected — hardware control enabled");

        // Wait for Arduino startup message
        std::this_thread::sleep_for(std::chrono::milliseconds(1500));
        std::string startup = g_serial.read_response(500);
        if (!startup.empty()) {
            g_logger.arduino(LogLevel::INFO, "Startup: " + startup);
        }
    } else {
        g_logger.jetson(LogLevel::ERROR, "Arduino not connected — HMI will run without hardware");
    }

    // Create GTK application (pass only program name, not our custom args)
    g_logger.jetson(LogLevel::INFO, "Creating GTK application");
    GtkApplication *app = gtk_application_new("com.swacch.hmi.final",
                                               G_APPLICATION_FLAGS_NONE);
    g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);

    int gtk_argc = 1;
    int status = g_application_run(G_APPLICATION(app), gtk_argc, argv);

    // Shutdown
    g_logger.jetson(LogLevel::INFO, "HMI shutting down...");
    g_serial.disconnect();
    g_object_unref(app);
    g_logger.jetson(LogLevel::INFO, "Shutdown complete");

    return status;
}
