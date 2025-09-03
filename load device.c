// main.c
#include "project.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>   // PATH_MAX

// ---------- Config ----------
static const char *kRelPath = "config/device_id.txt";  // inside res/
#define DEVBUF_SZ 256
// ---------------------------

// ---- Your connect function (stub; replace as needed) ----
static int ST_Connect(const char *device_id) {
    dlog_print(DLOG_INFO, "MYDEVICE", "ST_Connect called with ID: %s",
               device_id ? device_id : "(null)");
    // TODO: Replace with real logic
    return 0; // success
}

// Read first non-empty line from a file into buf (UTF-8). Returns 1 on success.
static int read_first_line(const char *abs_path, char *buf, size_t bufsz) {
    FILE *fp = fopen(abs_path, "r");
    if (!fp) return 0;
    if (!fgets(buf, (int)bufsz, fp)) { fclose(fp); return 0; }
    fclose(fp);
    // strip CR/LF
    size_t n = strlen(buf);
    while (n && (buf[n-1] == '\n' || buf[n-1] == '\r')) { buf[--n] = '\0'; }
    return n > 0;
}

// Button callback: loads ID from res file, sets entry, calls ST_Connect()
static void _connect_btn_clicked_cb(void *data, Evas_Object *obj, void *event_info) {
    Evas_Object *entry = (Evas_Object *)data;

    // Build absolute path to res/config/device_id.txt
    char fullpath[PATH_MAX];
    const char *resdir = app_get_resource_path(); // e.g., /opt/usr/apps/<id>/res/
    if (!resdir) {
        dlog_print(DLOG_ERROR, "MYDEVICE", "app_get_resource_path() failed");
        return;
    }
    snprintf(fullpath, sizeof(fullpath), "%s%s", resdir, kRelPath);

    char idbuf[DEVBUF_SZ] = {0};
    if (!read_first_line(fullpath, idbuf, sizeof(idbuf))) {
        dlog_print(DLOG_ERROR, "MYDEVICE", "Could not read device ID from %s", fullpath);
        return;
    }

    // Put the value into the Entry UI
    // Note: elm_entry expects markup; for plain text it’s fine to set directly.
    elm_entry_entry_set(entry, idbuf);

    // Call your connect logic
    dlog_print(DLOG_INFO, "MYDEVICE", "Connecting with Device ID: %s", idbuf);
    int rc = ST_Connect(idbuf);
    if (rc == 0) {
        dlog_print(DLOG_INFO, "MYDEVICE", "Connection SUCCESS");
    } else {
        dlog_print(DLOG_ERROR, "MYDEVICE", "Connection FAILED (rc=%d)", rc);
    }
}

void create_base_gui(appdata_s *ad) {
    // Window
    ad->win = elm_win_util_standard_add(PACKAGE, PACKAGE);
    elm_win_autodel_set(ad->win, EINA_TRUE);

    // Conformant
    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // Root vertical box
    Evas_Object *vbox = elm_box_add(ad->conform);
    elm_box_padding_set(vbox, ELM_SCALE_SIZE(10), ELM_SCALE_SIZE(10));
    evas_object_size_hint_weight_set(vbox, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(vbox, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_object_content_set(ad->conform, vbox);
    evas_object_show(vbox);

    // Top row: "Device ID:" + entry + button
    Evas_Object *hbox = elm_box_add(vbox);
    elm_box_horizontal_set(hbox, EINA_TRUE);
    elm_box_padding_set(hbox, ELM_SCALE_SIZE(8), 0);
    evas_object_size_hint_weight_set(hbox, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(hbox, EVAS_HINT_FILL, 0.0);
    evas_object_show(hbox);
    elm_box_pack_end(vbox, hbox);

    Evas_Object *lbl = elm_label_add(hbox);
    elm_object_text_set(lbl, "Device ID:");
    evas_object_size_hint_weight_set(lbl, 0.0, 0.0);
    evas_object_size_hint_align_set(lbl, 0.0, 0.5);
    evas_object_show(lbl);
    elm_box_pack_end(hbox, lbl);

    Evas_Object *entry = elm_entry_add(hbox);
    elm_entry_single_line_set(entry, EINA_TRUE);
    elm_object_part_text_set(entry, "guide", "Enter ID...");
    evas_object_size_hint_weight_set(entry, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(entry, EVAS_HINT_FILL, 0.5);
    evas_object_show(entry);
    elm_box_pack_end(hbox, entry);

    Evas_Object *btn = elm_button_add(hbox);
    elm_object_text_set(btn, "Connect to Device");
    evas_object_size_hint_weight_set(btn, 0.0, 0.0);
    evas_object_size_hint_align_set(btn, 0.0, 0.5);
    evas_object_smart_callback_add(btn, "clicked", _connect_btn_clicked_cb, entry);
    evas_object_show(btn);
    elm_box_pack_end(hbox, btn);

    evas_object_resize(ad->win, 720, 1280);
    evas_object_show(ad->win);
}