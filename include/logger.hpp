#ifndef LOGGER_HPP
#define LOGGER_HPP

#include <string>
#include <fstream>
#include <mutex>

// Log categories — each writes to its own subdirectory
enum class LogCategory {
    HMI,            // User interactions (button presses)
    JETSON,         // Command processing on Jetson
    ARDUINO,        // Arduino execution confirmations
    COMM            // Serial TX/RX communication
};

// Log severity levels
enum class LogLevel {
    INFO,
    SUCCESS,
    ERROR
};

class Logger {
private:
    std::string log_base_dir;
    std::mutex log_mutex;
    
    // One file stream per category
    std::ofstream hmi_file;
    std::ofstream jetson_file;
    std::ofstream arduino_file;
    std::ofstream comm_file;
    
    // Helpers
    std::string get_timestamp();
    std::string get_date_string();
    std::string category_to_string(LogCategory cat);
    std::string level_to_string(LogLevel level);
    std::string level_to_color(LogLevel level);
    std::ofstream& get_file_stream(LogCategory cat);
    void ensure_directories();
    void open_log_files();
    
public:
    Logger();
    ~Logger();
    
    // Initialize with base directory for log files
    void init(const std::string& base_dir = "logs");
    
    // Main logging function
    void log(LogCategory category, LogLevel level, const std::string& message);
    
    // Convenience methods
    void hmi(LogLevel level, const std::string& message);
    void jetson(LogLevel level, const std::string& message);
    void arduino(LogLevel level, const std::string& message);
    void comm(LogLevel level, const std::string& message);
};

// Global logger instance
extern Logger g_logger;

#endif // LOGGER_HPP
