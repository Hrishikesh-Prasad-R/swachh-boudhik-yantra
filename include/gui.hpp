#ifndef GUI_HPP
#define GUI_HPP

#include <gtk/gtk.h>

#define NUM_SPEED_LEVELS 9

struct Widgets {
    GtkWidget *status_label;
    GtkWidget *battery_label;
    GtkWidget *telemetry_label;
    GtkWidget *speed_label;
    GtkWidget *vacuum_btn;
    GtkWidget *arm_btn;
    GtkWidget *wiper_btn;
    GtkWidget *uv_btn;
    GtkWidget *auto_btn;
    GtkWidget *estop_btn;
    GtkWidget *speed_buttons[NUM_SPEED_LEVELS];
};

extern Widgets g_widgets;

void create_hmi_interface(GtkApplication *app);
void update_status();
void update_speed_buttons();
void update_telemetry();

#endif // GUI_HPP
