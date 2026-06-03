#ifndef SERIAL_COMM_HPP
#define SERIAL_COMM_HPP

#include <string>

class SerialComm {
private:
    int serial_port;
    bool connected;

public:
    SerialComm();
    ~SerialComm();

    bool connect(const char* port);
    bool send_command(const std::string& command);
    std::string read_response(int timeout_ms = 500);
    std::string read_nonblocking();   // Non-blocking read for status polling
    bool is_connected() const;
    void disconnect();
};

extern SerialComm g_serial;

#endif // SERIAL_COMM_HPP
