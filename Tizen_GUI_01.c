// Tizen 9.0 Native (EFL) — SmartThings-style UI mock (GUI only)
// Updates per request:
//  - Capabilities shown: deviceStatus, imageCapture, motionSensor
//  - Change "Load" button → "Take capture"
//  - Add Token field + "Load token" button
//  - No functionality wired — just layout/widgets

#include <app.h>
#include <Elementary.h>
#include <dlog.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LOG_TAG "st_ui_mock"

typedef struct {
    Evas_Object *win, *conform, *root;
    Evas_Object *header_label;

    // Row 1: Device field + actions
    Evas_Object *row1, *device_entry;
    Evas_Object *btn_capture, *btn_refresh, *btn_clear;

    // Row 2: Token field + load
    Evas_Object *row2, *token_entry, *btn_load_token;

    // Summary card
    Evas_Object *card_frame, *card_box;
    Evas_Object *lbl_name, *lbl_location, *lbl_status;

    // Capabilities
    Evas_Object *cap_frame, *cap_list;

    // Options
    Evas_Object *opt_box, *ck_auto, *ck_verbose;

    // Footer
    Evas_Object *status;
} App;

static void set_status(App *a, const char *msg) {
    if (!a || !a->status) return; elm_object_text_set(a->status, msg);
}

// Stub callbacks (no functionality per request)
static void cb_take_capture(void *data, Evas_Object *obj, void *ev){ (void)data;(void)obj;(void)ev; }
static void cb_refresh(void *data, Evas_Object *obj, void *ev){ (void)data;(void)obj;(void)ev; }
static void cb_clear(void *data, Evas_Object *obj, void *ev){ (void)data;(void)obj;(void)ev; }
static void cb_load_token(void *data, Evas_Object *obj, void *ev){ (void)data;(void)obj;(void)ev; }
static void cb_toggle(void *data, Evas_Object *obj, void *ev){ (void)data;(void)obj;(void)ev; }

static Evas_Object* make_button(Evas_Object *parent, const char *label, Evas_Smart_Cb cb, void *data) {
    Evas_Object *b = elm_button_add(parent);
    elm_object_text_set(b, label);
    evas_object_smart_callback_add(b, "clicked", cb, data);
    evas_object_show(b);
    return b;
}

static void add_capability(App *a, const char *cap, const char *desc) {
    char buf[256]; snprintf(buf, sizeof(buf), "%s — %s", cap, desc);
    elm_list_item_append(a->cap_list, buf, NULL, NULL, NULL, NULL);
}

static void build_ui(App *a) {
    // Window + conformant
    a->win = elm_win_util_standard_add("st-ui", "SmartThings Device (Mock)");
    elm_win_autodel_set(a->win, EINA_TRUE);

    a->conform = elm_conformant_add(a->win);
    evas_object_size_hint_weight_set(a->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(a->win, a->conform);
    evas_object_show(a->conform);

    // Root vbox
    a->root = elm_box_add(a->conform);
    elm_box_padding_set(a->root, 0, 8);
    evas_object_size_hint_weight_set(a->root, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(a->root, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_object_content_set(a->conform, a->root);
    evas_object_show(a->root);

    // Header
    a->header_label = elm_label_add(a->root);
    elm_object_text_set(a->header_label, "<align=left><b>SmartThings Device</b> — capabilities viewer (GUI only)</align>");
    evas_object_size_hint_weight_set(a->header_label, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->header_label, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(a->root, a->header_label);
    evas_object_show(a->header_label);

    // Row 1: Device field + actions
    a->row1 = elm_box_add(a->root);
    elm_box_horizontal_set(a->row1, EINA_TRUE);
    evas_object_size_hint_weight_set(a->row1, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->row1, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(a->root, a->row1);
    evas_object_show(a->row1);

    a->device_entry = elm_entry_add(a->row1);
    elm_entry_single_line_set(a->device_entry, EINA_TRUE);
    elm_object_part_text_set(a->device_entry, "guide", "deviceId or URL (e.g., device:demo-001)");
    evas_object_size_hint_weight_set(a->device_entry, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->device_entry, EVAS_HINT_FILL, 0.5);
    evas_object_size_hint_min_set(a->device_entry, 0, 80);
    elm_box_pack_end(a->row1, a->device_entry);
    evas_object_show(a->device_entry);

    a->btn_capture = make_button(a->row1, "Take capture", cb_take_capture, a);
    a->btn_refresh = make_button(a->row1, "Refresh", cb_refresh, a);
    a->btn_clear   = make_button(a->row1, "Clear", cb_clear, a);

    // Row 2: Token field + load token
    a->row2 = elm_box_add(a->root);
    elm_box_horizontal_set(a->row2, EINA_TRUE);
    evas_object_size_hint_weight_set(a->row2, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->row2, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(a->root, a->row2);
    evas_object_show(a->row2);

    a->token_entry = elm_entry_add(a->row2);
    elm_entry_single_line_set(a->token_entry, EINA_TRUE);
    elm_object_part_text_set(a->token_entry, "guide", "Device token");
    evas_object_size_hint_weight_set(a->token_entry, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->token_entry, EVAS_HINT_FILL, 0.5);
    evas_object_size_hint_min_set(a->token_entry, 0, 80);
    elm_box_pack_end(a->row2, a->token_entry);
    evas_object_show(a->token_entry);

    a->btn_load_token = make_button(a->row2, "Load token", cb_load_token, a);

    // Summary card
    a->card_frame = elm_frame_add(a->root);
    elm_object_text_set(a->card_frame, "Device Summary");
    evas_object_size_hint_weight_set(a->card_frame, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->card_frame, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(a->root, a->card_frame);
    evas_object_show(a->card_frame);

    a->card_box = elm_box_add(a->card_frame);
    elm_box_padding_set(a->card_box, 0, 4);
    evas_object_size_hint_weight_set(a->card_box, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->card_box, EVAS_HINT_FILL, 0.5);
    elm_object_content_set(a->card_frame, a->card_box);
    evas_object_show(a->card_box);

    a->lbl_name = elm_label_add(a->card_box);
    elm_object_text_set(a->lbl_name, "<b>Name:</b> —");
    elm_box_pack_end(a->card_box, a->lbl_name);
    evas_object_show(a->lbl_name);

    a->lbl_location = elm_label_add(a->card_box);
    elm_object_text_set(a->lbl_location, "<b>Location:</b> —");
    elm_box_pack_end(a->card_box, a->lbl_location);
    evas_object_show(a->lbl_location);

    a->lbl_status = elm_label_add(a->card_box);
    elm_object_text_set(a->lbl_status, "<b>Status:</b> —");
    elm_box_pack_end(a->card_box, a->lbl_status);
    evas_object_show(a->lbl_status);

    // Capabilities list
    a->cap_frame = elm_frame_add(a->root);
    elm_object_text_set(a->cap_frame, "Capabilities");
    evas_object_size_hint_weight_set(a->cap_frame, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(a->cap_frame, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(a->root, a->cap_frame);
    evas_object_show(a->cap_frame);

    Evas_Object *sc = elm_scroller_add(a->cap_frame);
    elm_scroller_bounce_set(sc, EINA_FALSE, EINA_TRUE);
    elm_scroller_policy_set(sc, ELM_SCROLLER_POLICY_AUTO, ELM_SCROLLER_POLICY_AUTO);
    elm_object_content_set(a->cap_frame, sc);
    evas_object_show(sc);

    a->cap_list = elm_list_add(sc);
    evas_object_size_hint_weight_set(a->cap_list, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(a->cap_list, EVAS_HINT_FILL, Evas_Coord(1.0));
    elm_object_content_set(sc, a->cap_list);
    evas_object_show(a->cap_list);

    // Prefill with requested capabilities
    add_capability(a, "deviceStatus", "online/offline");
    add_capability(a, "imageCapture", "take photo / last image");
    add_capability(a, "motionSensor", "active/inactive");
    elm_list_go(a->cap_list);

    // Options
    a->opt_box = elm_box_add(a->root);
    elm_box_horizontal_set(a->opt_box, EINA_TRUE);
    evas_object_size_hint_weight_set(a->opt_box, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->opt_box, 0.0, 0.5);
    elm_box_pack_end(a->root, a->opt_box);
    evas_object_show(a->opt_box);

    a->ck_auto = elm_check_add(a->opt_box);
    elm_object_text_set(a->ck_auto, "Auto-refresh");
    evas_object_smart_callback_add(a->ck_auto, "changed", cb_toggle, a);
    elm_box_pack_end(a->opt_box, a->ck_auto);
    evas_object_show(a->ck_auto);

    a->ck_verbose = elm_check_add(a->opt_box);
    elm_object_text_set(a->ck_verbose, "Verbose logs");
    evas_object_smart_callback_add(a->ck_verbose, "changed", cb_toggle, a);
    elm_box_pack_end(a->opt_box, a->ck_verbose);
    evas_object_show(a->ck_verbose);

    // Footer
    a->status = elm_label_add(a->root);
    elm_object_text_set(a->status, "Enter deviceId and token, then use the buttons (GUI only).");
    evas_object_size_hint_weight_set(a->status, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->status, 0.0, 0.5);
    elm_box_pack_end(a->root, a->status);
    evas_object_show(a->status);

    evas_object_resize(a->win, 720, 1280);
    evas_object_show(a->win);
}

// lifecycle
static bool app_create(void *data) { App *a = data; build_ui(a); return true; }
static void app_terminate(void *data) { (void)data; }
static void noop(app_event_info_h e, void *u){(void)e;(void)u;}

int main(int argc, char *argv[]) {
    App a = {0}; ui_app_lifecycle_callback_s cb = {0};
    cb.create = app_create; cb.terminate = app_terminate;
    app_event_handler_h h1,h2,h3,h4,h5;
    ui_app_add_event_handler(&h1, APP_EVENT_LOW_MEMORY, noop, NULL);
    ui_app_add_event_handler(&h2, APP_EVENT_LOW_BATTERY, noop, NULL);
    ui_app_add_event_handler(&h3, APP_EVENT_LANGUAGE_CHANGED, noop, NULL);
    ui_app_add_event_handler(&h4, APP_EVENT_REGION_FORMAT_CHANGED, noop, NULL);
    ui_app_add_event_handler(&h5, APP_EVENT_DEVICE_ORIENTATION_CHANGED, noop, NULL);
    int r = ui_app_main(argc, argv, &cb, &a);
    if (r != APP_ERROR_NONE) dlog_print(DLOG_ERROR, LOG_TAG, "ui_app_main failed: %d", r);
    return r;
}
