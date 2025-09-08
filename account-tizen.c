#include "project.h"
#include <samsung_account.h>

#define LOGTAG "MYDEVICE"

static samsung_account_h g_handle = NULL;
static Evas_Object *g_status_label = NULL;   // UI label for showing response

// ---- Callback from Samsung Account API ----
static void connection_changed_cb(samsung_account_error_e err,
                                  samsung_account_connection_status_e status,
                                  void* data)
{
    if (err == SAMSUNG_ACCOUNT_ERROR_NONE &&
        status == SAMSUNG_ACCOUNT_CONNECTION_STATUS_CONNECTED) {
        dlog_print(DLOG_INFO, LOGTAG, "Connected successfully");

        // Update label text on screen
        elm_object_text_set(g_status_label, "Status: Connected ✅");
    } else {
        dlog_print(DLOG_ERROR, LOGTAG, "Connection failed (err=%d, status=%d)", err, status);

        // Show failure
        elm_object_text_set(g_status_label, "Status: Failed ❌");
    }
}

// ---- Button click handler ----
static void _connect_btn_clicked_cb(void *data, Evas_Object *obj, void *event_info)
{
    int ret = samsung_account_connect(&g_handle, connection_changed_cb, NULL);
    if (ret != SAMSUNG_ACCOUNT_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOGTAG, "samsung_account_connect failed (ret=%d)", ret);
        elm_object_text_set(g_status_label, "Status: Connect API failed");
        return;
    }

    elm_object_text_set(g_status_label, "Status: Connecting…");
}

// ---- GUI creation ----
void create_base_gui(appdata_s *ad)
{
    ad->win = elm_win_util_standard_add(PACKAGE, PACKAGE);
    elm_win_autodel_set(ad->win, EINA_TRUE);

    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // Root vertical box
    Evas_Object *vbox = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(vbox, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(vbox, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_object_content_set(ad->conform, vbox);
    evas_object_show(vbox);

    // Button: Connect
    Evas_Object *btn = elm_button_add(vbox);
    elm_object_text_set(btn, "Connect to Samsung Account");
    evas_object_smart_callback_add(btn, "clicked", _connect_btn_clicked_cb, NULL);
    evas_object_show(btn);
    elm_box_pack_end(vbox, btn);

    // Status label (global so callback can update it)
    g_status_label = elm_label_add(vbox);
    elm_object_text_set(g_status_label, "Status: Idle");
    evas_object_size_hint_weight_set(g_status_label, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(g_status_label, 0.0, 0.0);
    evas_object_show(g_status_label);
    elm_box_pack_end(vbox, g_status_label);

    evas_object_resize(ad->win, 720, 1280);
    evas_object_show(ad->win);
}
