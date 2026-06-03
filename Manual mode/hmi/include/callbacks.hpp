#ifndef CALLBACKS_HPP
#define CALLBACKS_HPP

#include <gtk/gtk.h>

// Movement direction state machine
enum MoveDir { DIR_NONE = 0, DIR_FWD, DIR_BWD, DIR_LEFT, DIR_RIGHT };
extern MoveDir g_move_dir;

// Movement callbacks (gesture-based: press=start, release=stop)
void on_move_pressed(GtkGestureClick*, int, double, double, gpointer data);
void on_move_released(GtkGestureClick*, int, double, double, gpointer);
void on_move_cancelled(GtkGestureClick*, gpointer);
void stop_movement();

// Button callbacks
void on_stop(GtkWidget*, gpointer);
void on_estop(GtkWidget*, gpointer);
void on_reset(GtkWidget*, gpointer);
void on_vacuum(GtkWidget *w, gpointer);
void on_arm(GtkWidget *w, gpointer);
void on_wiper(GtkWidget *w, gpointer);
void on_uv(GtkWidget *w, gpointer);
void on_auto_toggle(GtkWidget *w, gpointer);
void on_speed_select(GtkWidget*, gpointer data);

// Timers
gboolean serial_poll_tick(gpointer);
gboolean battery_tick(gpointer);

#endif // CALLBACKS_HPP
