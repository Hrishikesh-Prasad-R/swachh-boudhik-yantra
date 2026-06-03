#include "logger.hpp"
#include <iostream>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <sys/stat.h>
#include <ctime>

// ANSI color codes
#define COLOR_RESET   "\033[0m"
#define COLOR_GREEN   "\033[32m"
#define COLOR_RED     "\033[31m"
#define COLOR_YELLOW  "\033[33m"
#define COLOR_CYAN    "\033[36m"
#define COLOR_MAGENTA "\033[35m"
#define COLOR_BLUE    "\033[34m"
#define COLOR_WHITE   "\033[37m"
#define COLOR_BOLD    "\033[1m"

// Global logger instance
Logger g_logger;

Logger::Logger() {}

Logger::~Logger() {
    if (hmi_file.is_open()) hmi_file.close();
    if (jetson_file.is_open()) jetson_file.close();
    if (arduino_file.is_open()) arduino_file.close();
    if (comm_file.is_open()) comm_file.close();
}

std::string Logger::get_timestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    
    struct tm tm_buf;
    localtime_r(&time_t_now, &tm_buf);
    
    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%H:%M:%S")
        << '.' << std::setfill('0') << std::setw(3) << ms.count();
    return oss.str();
}

std::string Logger::get_date_string() {
    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    
    struct tm tm_buf;
    localtime_r(&time_t_now, &tm_buf);
    
    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y-%m-%d");
    return oss.str();
}

std::string Logger::category_to_string(LogCategory cat) {
    switch (cat) {
        case LogCategory::HMI:     return "HMI    ";
        case LogCategory::JETSON:  return "JETSON ";
        case LogCategory::ARDUINO: return "ARDUINO";
        case LogCategory::COMM:    return "COMM   ";
    }
    return "UNKNOWN";
}

std::string Logger::level_to_string(LogLevel level) {
    switch (level) {
        case LogLevel::INFO:    return "INFO   ";
        case LogLevel::SUCCESS: return "SUCCESS";
        case LogLevel::ERROR:   return "ERROR  ";
    }
    return "UNKNOWN";
}

std::string Logger::level_to_color(LogLevel level) {
    switch (level) {
        case LogLevel::INFO:    return COLOR_CYAN;
        case LogLevel::SUCCESS: return COLOR_GREEN;
        case LogLevel::ERROR:   return COLOR_RED;
    }
    return COLOR_WHITE;
}

std::ofstream& Logger::get_file_stream(LogCategory cat) {
    switch (cat) {
        case LogCategory::HMI:     return hmi_file;
        case LogCategory::JETSON:  return jetson_file;
        case LogCategory::ARDUINO: return arduino_file;
        case LogCategory::COMM:    return comm_file;
    }
    return comm_file; // fallback
}

void Logger::ensure_directories() {
    std::string dirs[] = {
        log_base_dir,
        log_base_dir + "/hmi",
        log_base_dir + "/jetson",
        log_base_dir + "/arduino",
        log_base_dir + "/communication"
    };
    
    for (const auto& dir : dirs) {
        mkdir(dir.c_str(), 0755);
    }
}

void Logger::open_log_files() {
    std::string date = get_date_string();
    
    auto open_file = [&](std::ofstream& stream, const std::string& subdir, const std::string& prefix) {
        if (stream.is_open()) stream.close();
        std::string path = log_base_dir + "/" + subdir + "/" + prefix + "_" + date + ".log";
        stream.open(path, std::ios::app);
        if (!stream.is_open()) {
            std::cerr << "Failed to open log file: " << path << std::endl;
        }
    };
    
    open_file(hmi_file, "hmi", "hmi");
    open_file(jetson_file, "jetson", "jetson");
    open_file(arduino_file, "arduino", "arduino");
    open_file(comm_file, "communication", "comm");
}

void Logger::init(const std::string& base_dir) {
    log_base_dir = base_dir;
    ensure_directories();
    open_log_files();
    
    // Log startup marker
    log(LogCategory::JETSON, LogLevel::INFO, "════════════════════════════════════════════");
    log(LogCategory::JETSON, LogLevel::INFO, "Swacch Robot Logger initialized");
    log(LogCategory::JETSON, LogLevel::INFO, "Log directory: " + log_base_dir);
    log(LogCategory::JETSON, LogLevel::INFO, "════════════════════════════════════════════");
}

void Logger::log(LogCategory category, LogLevel level, const std::string& message) {
    std::lock_guard<std::mutex> lock(log_mutex);
    
    std::string timestamp = get_timestamp();
    std::string cat_str = category_to_string(category);
    std::string lvl_str = level_to_string(level);
    
    // Category color
    std::string cat_color;
    switch (category) {
        case LogCategory::HMI:     cat_color = COLOR_MAGENTA; break;
        case LogCategory::JETSON:  cat_color = COLOR_BLUE;    break;
        case LogCategory::ARDUINO: cat_color = COLOR_YELLOW;  break;
        case LogCategory::COMM:    cat_color = COLOR_CYAN;    break;
    }
    
    // Terminal output (colored)
    std::cout << COLOR_WHITE << "[" << timestamp << "] "
              << cat_color << COLOR_BOLD << "[" << cat_str << "] "
              << level_to_color(level) << "[" << lvl_str << "] "
              << COLOR_RESET << message
              << std::endl;
    
    // File output (plain text, no colors)
    std::ofstream& file = get_file_stream(category);
    if (file.is_open()) {
        file << "[" << timestamp << "] "
             << "[" << lvl_str << "] "
             << message
             << std::endl;
        file.flush();
    }
}

void Logger::hmi(LogLevel level, const std::string& message) {
    log(LogCategory::HMI, level, message);
}

void Logger::jetson(LogLevel level, const std::string& message) {
    log(LogCategory::JETSON, level, message);
}

void Logger::arduino(LogLevel level, const std::string& message) {
    log(LogCategory::ARDUINO, level, message);
}

void Logger::comm(LogLevel level, const std::string& message) {
    log(LogCategory::COMM, level, message);
}
