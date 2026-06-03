/**
 * Swacch Robot — Final GTK4 GUI
 * Adapted from gui_teleop_node.cpp (cloned repo)
 * with serial communication and 4-category logging.
 */

#include "gui.hpp"
#include "callbacks.hpp"
#include "system_state.hpp"
#include "serial_comm.hpp"
#include "logger.hpp"

#include <string>
#include <cstdio>

// Global widget references
Widgets g_widgets;

// Speed level definitions (from gui_teleop_node.cpp)
static const char* SPEED_NAMES[NUM_SPEED_LEVELS] = {
    "1: Crawl", "2: Slow", "3: Gentle",
    "4: Medium", "5: Normal", "6: Fast",
    "7: Faster", "8: Rush", "9: Max"
};

// ---- Display update helpers ----

void update_status() {
    std::string markup = "<span font='12' weight='bold'>" +
                         g_system_state.status + "</span>";
    gtk_label_set_markup(GTK_LABEL(g_widgets.status_label), markup.c_str());

    std::string bat = "<span font='11'>Battery: " +
                      std::to_string(g_system_state.battery_level) + "%</span>";
    gtk_label_set_markup(GTK_LABEL(g_widgets.battery_label), bat.c_str());
}

void update_speed_buttons() {
    int current = g_system_state.speed_level - 1;  // 1-indexed to 0-indexed
    for (int i = 0; i < NUM_SPEED_LEVELS; i++) {
        if (i == current) {
            gtk_widget_add_css_class(g_widgets.speed_buttons[i], "speed-active");
        } else {
            gtk_widget_remove_css_class(g_widgets.speed_buttons[i], "speed-active");
        }
    }

    char buf[128];
    snprintf(buf, sizeof(buf),
             "<span font='11'>Speed Level: %d / %d</span>",
             g_system_state.speed_level, NUM_SPEED_LEVELS);
    gtk_label_set_markup(GTK_LABEL(g_widgets.speed_label), buf);
}

void update_telemetry() {
    char buf[256];
    const char* conn_color = g_serial.is_connected() ? "green" : "red";
    const char* conn_text = g_serial.is_connected() ? "Connected" : "Disconnected";

    const char* move_text = g_system_state.moving ? "MOVING" : "IDLE";
    const char* move_color = g_system_state.moving ? "orange" : "green";

    snprintf(buf, sizeof(buf),
             "<span font='11'>Arduino: <span foreground='%s' weight='bold'>%s</span>  |  "
             "Motors: <span foreground='%s' weight='bold'>%s</span>  |  "
             "Vacuum: %s  Arm: %s  Wiper: %s  UV: %s</span>",
             conn_color, conn_text,
             move_color, move_text,
             g_system_state.vacuum_active ? "ON" : "off",
             g_system_state.arm_active ? "ON" : "off",
             g_system_state.wiper_active ? "ON" : "off",
             g_system_state.uv_active ? "ON" : "off");
    gtk_label_set_markup(GTK_LABEL(g_widgets.telemetry_label), buf);
}

// ---- CSS styling (from gui_teleop_node.cpp) ----

static void apply_css() {
    GtkCssProvider *provider = gtk_css_provider_new();
    const char *css =
        "window { background-color: #1a1a2e; }\n"
        "label { color: #e0e0e0; }\n"
        "button { border-radius: 6px; padding: 6px 12px; font-weight: bold;\n"
        "         background: linear-gradient(#2d3436, #636e72);\n"
        "         color: white; border: 1px solid #555; font-size: 12px; }\n"
        "button:hover { background: linear-gradient(#636e72, #2d3436); }\n"
        "button.destructive-action { background: linear-gradient(#c0392b, #e74c3c);\n"
        "                            color: white; }\n"
        "button.destructive-action:hover { background: linear-gradient(#e74c3c, #c0392b); }\n"
        "button.suggested-action { background: linear-gradient(#2980b9, #3498db);\n"
        "                          color: white; }\n"
        "button.suggested-action:hover { background: linear-gradient(#3498db, #2980b9); }\n"
        "button.speed-active { background: linear-gradient(#27ae60, #2ecc71);\n"
        "                      color: white; border: 2px solid #1e8449; }\n"
        "frame { border: 1px solid #444; border-radius: 8px; padding: 4px; }\n"
        "frame > label { color: #aaa; font-size: 11px; }\n";

    gtk_css_provider_load_from_data(provider, css, -1);
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(),
        GTK_STYLE_PROVIDER(provider),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION
    );
    g_object_unref(provider);
}

// ---- Build the GUI (layout from gui_teleop_node.cpp) ----

void create_hmi_interface(GtkApplication *app) {
    apply_css();

    GtkWidget *window = gtk_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(window), "Swacch Robot HMI — Final");
    gtk_window_set_default_size(GTK_WINDOW(window), 820, 750);
    gtk_window_fullscreen(GTK_WINDOW(window));

    // Scrollable wrapper
    GtkWidget *scroll = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll),
                                   GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_window_set_child(GTK_WINDOW(window), scroll);

    // Main vertical box
    GtkWidget *main_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
    gtk_widget_set_margin_start(main_box, 12);
    gtk_widget_set_margin_end(main_box, 12);
    gtk_widget_set_margin_top(main_box, 8);
    gtk_widget_set_margin_bottom(main_box, 8);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll), main_box);

    // ---- Title ----
    GtkWidget *title = gtk_label_new(NULL);
    gtk_label_set_markup(GTK_LABEL(title),
        "<span font='16' weight='bold' foreground='#3498db'>Swacch Robot HMI</span>");
    gtk_box_append(GTK_BOX(main_box), title);

    // ---- Status + Battery ----
    g_widgets.status_label = gtk_label_new(NULL);
    gtk_label_set_markup(GTK_LABEL(g_widgets.status_label),
        "<span font='12' weight='bold'>System Ready</span>");
    gtk_box_append(GTK_BOX(main_box), g_widgets.status_label);

    g_widgets.battery_label = gtk_label_new(NULL);
    gtk_label_set_markup(GTK_LABEL(g_widgets.battery_label),
        "<span font='11'>Battery: 100%</span>");
    gtk_box_append(GTK_BOX(main_box), g_widgets.battery_label);

    // ---- Telemetry section ----
    GtkWidget *telemetry_frame = gtk_frame_new("Telemetry");
    gtk_box_append(GTK_BOX(main_box), telemetry_frame);

    GtkWidget *tbox = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
    gtk_widget_set_margin_start(tbox, 8);
    gtk_widget_set_margin_end(tbox, 8);
    gtk_widget_set_margin_top(tbox, 4);
    gtk_widget_set_margin_bottom(tbox, 4);
    gtk_frame_set_child(GTK_FRAME(telemetry_frame), tbox);

    g_widgets.telemetry_label = gtk_label_new(NULL);
    gtk_label_set_markup(GTK_LABEL(g_widgets.telemetry_label),
        "<span font='11'>Arduino: <span foreground='red' weight='bold'>Disconnected</span></span>");
    gtk_box_append(GTK_BOX(tbox), g_widgets.telemetry_label);

    g_widgets.speed_label = gtk_label_new(NULL);
    gtk_label_set_markup(GTK_LABEL(g_widgets.speed_label),
        "<span font='11'>Speed Level: 5 / 9</span>");
    gtk_box_append(GTK_BOX(tbox), g_widgets.speed_label);

    // ---- Emergency Stop ----
    GtkWidget *estop_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
    gtk_widget_set_halign(estop_box, GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(main_box), estop_box);

    g_widgets.estop_btn = gtk_button_new_with_label("EMERGENCY STOP");
    gtk_widget_set_size_request(g_widgets.estop_btn, 240, 50);
    gtk_widget_add_css_class(g_widgets.estop_btn, "destructive-action");
    g_signal_connect(g_widgets.estop_btn, "clicked", G_CALLBACK(on_estop), NULL);
    gtk_box_append(GTK_BOX(estop_box), g_widgets.estop_btn);

    GtkWidget *reset_btn = gtk_button_new_with_label("Reset");
    gtk_widget_set_size_request(reset_btn, 100, 50);
    gtk_widget_add_css_class(reset_btn, "suggested-action");
    g_signal_connect(reset_btn, "clicked", G_CALLBACK(on_reset), NULL);
    gtk_box_append(GTK_BOX(estop_box), reset_btn);

    // ---- Component Controls ----
    GtkWidget *comp_frame = gtk_frame_new("Component Controls");
    gtk_box_append(GTK_BOX(main_box), comp_frame);

    GtkWidget *comp_grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(comp_grid), 4);
    gtk_grid_set_column_spacing(GTK_GRID(comp_grid), 4);
    gtk_widget_set_margin_start(comp_grid, 5);
    gtk_widget_set_margin_end(comp_grid, 5);
    gtk_widget_set_margin_top(comp_grid, 4);
    gtk_widget_set_margin_bottom(comp_grid, 4);
    gtk_widget_set_halign(comp_grid, GTK_ALIGN_CENTER);
    gtk_frame_set_child(GTK_FRAME(comp_frame), comp_grid);

    g_widgets.vacuum_btn = gtk_button_new_with_label("Vacuum");
    gtk_widget_set_size_request(g_widgets.vacuum_btn, 140, 42);
    g_signal_connect(g_widgets.vacuum_btn, "clicked", G_CALLBACK(on_vacuum), NULL);
    gtk_grid_attach(GTK_GRID(comp_grid), g_widgets.vacuum_btn, 0, 0, 1, 1);

    g_widgets.arm_btn = gtk_button_new_with_label("Arm");
    gtk_widget_set_size_request(g_widgets.arm_btn, 140, 42);
    g_signal_connect(g_widgets.arm_btn, "clicked", G_CALLBACK(on_arm), NULL);
    gtk_grid_attach(GTK_GRID(comp_grid), g_widgets.arm_btn, 1, 0, 1, 1);

    g_widgets.wiper_btn = gtk_button_new_with_label("Wiper");
    gtk_widget_set_size_request(g_widgets.wiper_btn, 140, 42);
    g_signal_connect(g_widgets.wiper_btn, "clicked", G_CALLBACK(on_wiper), NULL);
    gtk_grid_attach(GTK_GRID(comp_grid), g_widgets.wiper_btn, 2, 0, 1, 1);

    g_widgets.uv_btn = gtk_button_new_with_label("UV");
    gtk_widget_set_size_request(g_widgets.uv_btn, 140, 42);
    g_signal_connect(g_widgets.uv_btn, "clicked", G_CALLBACK(on_uv), NULL);
    gtk_grid_attach(GTK_GRID(comp_grid), g_widgets.uv_btn, 3, 0, 1, 1);

    g_widgets.auto_btn = gtk_button_new_with_label("Auto");
    gtk_widget_set_size_request(g_widgets.auto_btn, 140, 42);
    g_signal_connect(g_widgets.auto_btn, "clicked", G_CALLBACK(on_auto_toggle), NULL);
    gtk_grid_attach(GTK_GRID(comp_grid), g_widgets.auto_btn, 0, 1, 2, 1);

    // ---- Speed Controls (9 levels in a 3x3 grid) ----
    GtkWidget *speed_frame = gtk_frame_new("Speed Level (1-9)");
    gtk_box_append(GTK_BOX(main_box), speed_frame);

    GtkWidget *speed_grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(speed_grid), 3);
    gtk_grid_set_column_spacing(GTK_GRID(speed_grid), 3);
    gtk_widget_set_margin_start(speed_grid, 5);
    gtk_widget_set_margin_end(speed_grid, 5);
    gtk_widget_set_margin_top(speed_grid, 4);
    gtk_widget_set_margin_bottom(speed_grid, 4);
    gtk_widget_set_halign(speed_grid, GTK_ALIGN_CENTER);
    gtk_frame_set_child(GTK_FRAME(speed_frame), speed_grid);

    for (int i = 0; i < NUM_SPEED_LEVELS; i++) {
        g_widgets.speed_buttons[i] = gtk_button_new_with_label(SPEED_NAMES[i]);
        gtk_widget_set_size_request(g_widgets.speed_buttons[i], 160, 34);
        g_signal_connect(g_widgets.speed_buttons[i], "clicked",
                         G_CALLBACK(on_speed_select), GINT_TO_POINTER(i));
        gtk_grid_attach(GTK_GRID(speed_grid), g_widgets.speed_buttons[i],
                         i % 3, i / 3, 1, 1);
    }
    update_speed_buttons();

    // ---- Movement Controls (hold to move, release to stop) ----
    GtkWidget *move_frame = gtk_frame_new("Movement Controls (hold to move)");
    gtk_box_append(GTK_BOX(main_box), move_frame);

    GtkWidget *move_grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(move_grid), 4);
    gtk_grid_set_column_spacing(GTK_GRID(move_grid), 4);
    gtk_widget_set_margin_start(move_grid, 5);
    gtk_widget_set_margin_end(move_grid, 5);
    gtk_widget_set_margin_top(move_grid, 4);
    gtk_widget_set_margin_bottom(move_grid, 4);
    gtk_widget_set_halign(move_grid, GTK_ALIGN_CENTER);
    gtk_frame_set_child(GTK_FRAME(move_frame), move_grid);

    // Helper: attach press/release gesture in CAPTURE phase
    auto attach_move = [](GtkWidget *btn, MoveDir dir) {
        GtkGesture *gesture = gtk_gesture_click_new();
        gtk_event_controller_set_propagation_phase(
            GTK_EVENT_CONTROLLER(gesture), GTK_PHASE_CAPTURE);
        g_signal_connect(gesture, "pressed",
                         G_CALLBACK(on_move_pressed), GINT_TO_POINTER(dir));
        g_signal_connect(gesture, "released",
                         G_CALLBACK(on_move_released), NULL);
        gtk_widget_add_controller(btn, GTK_EVENT_CONTROLLER(gesture));
    };

    GtkWidget *fwd = gtk_button_new_with_label("Forward");
    gtk_widget_set_size_request(fwd, 130, 50);
    attach_move(fwd, DIR_FWD);
    gtk_grid_attach(GTK_GRID(move_grid), fwd, 1, 0, 1, 1);

    GtkWidget *left = gtk_button_new_with_label("Left");
    gtk_widget_set_size_request(left, 130, 50);
    attach_move(left, DIR_LEFT);
    gtk_grid_attach(GTK_GRID(move_grid), left, 0, 1, 1, 1);

    GtkWidget *stop_btn = gtk_button_new_with_label("STOP");
    gtk_widget_set_size_request(stop_btn, 130, 50);
    gtk_widget_add_css_class(stop_btn, "destructive-action");
    g_signal_connect(stop_btn, "clicked", G_CALLBACK(on_stop), NULL);
    gtk_grid_attach(GTK_GRID(move_grid), stop_btn, 1, 1, 1, 1);

    GtkWidget *right = gtk_button_new_with_label("Right");
    gtk_widget_set_size_request(right, 130, 50);
    attach_move(right, DIR_RIGHT);
    gtk_grid_attach(GTK_GRID(move_grid), right, 2, 1, 1, 1);

    GtkWidget *bwd = gtk_button_new_with_label("Backward");
    gtk_widget_set_size_request(bwd, 130, 50);
    attach_move(bwd, DIR_BWD);
    gtk_grid_attach(GTK_GRID(move_grid), bwd, 1, 2, 1, 1);

    // Show window
    gtk_widget_set_visible(window, TRUE);

    // Timers
    g_timeout_add(50, serial_poll_tick, NULL);       // 20Hz serial poll + telemetry
    g_timeout_add_seconds(5, battery_tick, NULL);    // Battery simulation

    g_logger.jetson(LogLevel::SUCCESS, "HMI interface created successfully");
}
