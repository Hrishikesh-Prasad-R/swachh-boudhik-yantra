#include "serial_comm.hpp"
#include "logger.hpp"
#include <iostream>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <cstring>
#include <chrono>
#include <thread>
#include <cerrno>

SerialComm g_serial;

SerialComm::SerialComm() : serial_port(-1), connected(false) {}

SerialComm::~SerialComm() {
    disconnect();
}

bool SerialComm::connect(const char* port) {
    g_logger.comm(LogLevel::INFO, std::string("Opening serial port: ") + port);

    serial_port = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);

    if (serial_port < 0) {
        g_logger.comm(LogLevel::ERROR, std::string("Failed to open: ") + port + " (" + strerror(errno) + ")");
        return false;
    }

    struct termios tty;
    memset(&tty, 0, sizeof(tty));

    if (tcgetattr(serial_port, &tty) != 0) {
        g_logger.comm(LogLevel::ERROR, "Failed to get serial attributes: " + std::string(strerror(errno)));
        return false;
    }

    cfsetospeed(&tty, B115200);
    cfsetispeed(&tty, B115200);

    tty.c_cflag &= ~PARENB;
    tty.c_cflag &= ~CSTOPB;
    tty.c_cflag &= ~CSIZE;
    tty.c_cflag |= CS8;
    tty.c_cflag &= ~CRTSCTS;
    tty.c_cflag |= CREAD | CLOCAL;

    tty.c_lflag &= ~ICANON;
    tty.c_lflag &= ~ECHO;
    tty.c_lflag &= ~ISIG;

    tty.c_iflag &= ~(IXON | IXOFF | IXANY);
    tty.c_iflag &= ~(IGNBRK|BRKINT|PARMRK|ISTRIP|INLCR|IGNCR|ICRNL);

    tty.c_oflag &= ~OPOST;
    tty.c_oflag &= ~ONLCR;

    tty.c_cc[VTIME] = 1;
    tty.c_cc[VMIN] = 0;

    if (tcsetattr(serial_port, TCSANOW, &tty) != 0) {
        g_logger.comm(LogLevel::ERROR, "Failed to set serial attributes: " + std::string(strerror(errno)));
        return false;
    }

    tcflush(serial_port, TCIOFLUSH);

    connected = true;
    g_logger.comm(LogLevel::SUCCESS, std::string("Connected to ") + port + " (115200 baud, 8N1)");
    return true;
}

bool SerialComm::send_command(const std::string& command) {
    if (!connected || serial_port < 0) {
        g_logger.comm(LogLevel::ERROR, "Cannot send '" + command + "': not connected");
        return false;
    }

    g_logger.comm(LogLevel::INFO, "TX → " + command);

    std::string cmd = command + "\n";
    ssize_t bytes_written = write(serial_port, cmd.c_str(), cmd.length());

    if (bytes_written < 0) {
        g_logger.comm(LogLevel::ERROR, "Write failed: " + std::string(strerror(errno)));
        return false;
    }

    tcdrain(serial_port);
    g_logger.comm(LogLevel::SUCCESS, "Sent " + std::to_string(bytes_written) + " bytes");

    // Read ACK
    std::string response = read_response(500);
    if (!response.empty()) {
        if (response.find("ACK:") == 0) {
            g_logger.arduino(LogLevel::SUCCESS, "ACK ← " + response);
        } else if (response.find("ERR:") == 0) {
            g_logger.arduino(LogLevel::ERROR, "ERR ← " + response);
        } else if (response.find("STATUS:") == 0) {
            // Status message, not an ACK — log but don't treat as error
            g_logger.arduino(LogLevel::INFO, "STATUS ← " + response);
        } else {
            g_logger.arduino(LogLevel::INFO, "RX ← " + response);
        }
    } else {
        g_logger.arduino(LogLevel::ERROR, "No response (timeout 500ms)");
    }

    return true;
}

std::string SerialComm::read_response(int timeout_ms) {
    if (!connected || serial_port < 0) return "";

    std::string line;
    auto start = std::chrono::steady_clock::now();

    while (true) {
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start).count();
        if (elapsed >= timeout_ms) break;

        char c;
        ssize_t n = read(serial_port, &c, 1);
        if (n > 0) {
            if (c == '\n' || c == '\r') {
                if (!line.empty()) return line;
            } else {
                line += c;
            }
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
    }
    return line;
}

std::string SerialComm::read_nonblocking() {
    if (!connected || serial_port < 0) return "";

    std::string line;
    while (true) {
        char c;
        ssize_t n = read(serial_port, &c, 1);
        if (n > 0) {
            if (c == '\n' || c == '\r') {
                if (!line.empty()) return line;
            } else {
                line += c;
            }
        } else {
            break;  // No more data available
        }
    }
    return line;
}

bool SerialComm::is_connected() const {
    return connected;
}

void SerialComm::disconnect() {
    if (serial_port >= 0) {
        g_logger.comm(LogLevel::INFO, "Disconnecting serial port");
        close(serial_port);
        serial_port = -1;
        connected = false;
        g_logger.comm(LogLevel::SUCCESS, "Disconnected");
    }
}
