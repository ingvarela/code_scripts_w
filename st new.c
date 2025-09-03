// main.c
#include "project.h"
#include <string.h>   // for strlen

// --------- YOUR CONNECT FUNCTION (stub to replace) ---------
/**
 * ST_Connect:
 * Replace this with your real connection logic.
 * Return 0 on success, non-zero on failure.
 */
static int ST_Connect(const char *device_id)
{
    // TODO: replace this stub with your real implementation
    dlog_print(DLOG_INFO, "MYDEVICE", "ST_Connect called with ID: %s", device_id ? device_id : "(null)");

    // Simulate work...
    // e.g., open socket, call API, etc.

    // Simulate success:
    return 0;
}
// -----------------------------------------------------------


// Button callback: reads entry text and calls ST_Connect()
static void
_connect_btn_clicked_cb(void *data, Evas_Object *obj, void *event_info)
{
    // "data" is the entry widget we stored when wiring the callback
    Evas_Object *entry = (Evas_Object *)data;

    // Get user text (UTF-8). Note: this returns entry markup if any. For plain
    // text usage we generally keep it as-is when the entry is single-line.
    const char *device_id = elm_entry_entry_get(entry);

    if (!device_id || strlen(device_id) == 0) {
        dlog_print(DLOG_WARN, "MYDEVICE", "No Device ID entered");
        return;
    }

    dlog_print(DLOG_INFO, "MYDEVICE", "Connecting with Device ID: %s", device_id);

    int rc = ST_Connect(device_id);
    if (rc == 0) {
        dlog_print(DLOG_INFO, "MYDEVICE", "Connection SUCCESS");
    } else {
        dlog_print(DLOG_ERROR, "MYDEVICE", "Connection FAILED (rc=%d)", rc);
    }
}

void create_base_gui(appdata_s *ad)
{
    // Window
    ad->win = elm_win_util_standard_add(PACKAGE, PACKAGE);
    elm_win_autodel_set(ad->win, EINA_TRUE);

    // Conformant
    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // Root vertical box (page)
    Evas_Object *vbox = elm_box_add(ad->conform);
    elm_box_padding_set(vbox, ELM_SCALE_SIZE(10), ELM_SCALE_SIZE(10));
    evas_object_size_hint_weight_set(vbox, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(vbox, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_object_content_set(ad->conform, vbox);
    evas_object_show(vbox);

    // --- Top bar: label + entry + button ---
    Evas_Object *hbox = elm_box_add(vbox);
    elm_box_horizontal_set(hbox, EINA_TRUE);
    elm_box_padding_set(hbox, ELM_SCALE_SIZE(8), 0);
    evas_object_size_hint_weight_set(hbox, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(hbox, EVAS_HINT_FILL, 0.0);
    evas_object_show(hbox);
    elm_box_pack_end(vbox, hbox);

    // Label
    Evas_Object *lbl = elm_label_add(hbox);
    elm_object_text_set(lbl, "Device ID:");
    evas_object_size_hint_weight_set(lbl, 0.0, 0.0);
    evas_object_size_hint_align_set(lbl, 0.0, 0.5);
    evas_object_show(lbl);
    elm_box_pack_end(hbox, lbl);

    // Entry
    Evas_Object *entry = elm_entry_add(hbox);
    elm_entry_single_line_set(entry, EINA_TRUE);
    elm_object_part_text_set(entry, "guide", "Enter ID...");
    evas_object_size_hint_weight_set(entry, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(entry, EVAS_HINT_FILL, 0.5);
    evas_object_show(entry);
    elm_box_pack_end(hbox, entry);

    // Button
    Evas_Object *btn = elm_button_add(hbox);
    elm_object_text_set(btn, "Connect to Device");
    evas_object_size_hint_weight_set(btn, 0.0, 0.0);
    evas_object_size_hint_align_set(btn, 0.0, 0.5);
    // Pass the entry pointer so callback can read its text
    evas_object_smart_callback_add(btn, "clicked", _connect_btn_clicked_cb, entry);
    evas_object_show(btn);
    elm_box_pack_end(hbox, btn);

    // Finalize window
    evas_object_resize(ad->win, 720, 1280);
    evas_object_show(ad->win);
}