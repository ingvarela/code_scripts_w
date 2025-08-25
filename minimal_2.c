// Tizen 9.0 Native (EFL) — Minimal UI using only base widgets and <project.h>
// TV/Emulator-safe version: removes Conformant (which can crash on TV profile/emulators)
// and keeps only core EFL widgets. No extra libs.

#include "project.h"  // pulls in app.h, Elementary, dlog, etc.

#define LOG_TAG "minimal_ui_tv"

typedef struct {
    Evas_Object *win;     // top-level window
    Evas_Object *bg;      // background
    Evas_Object *root;    // vertical box

    // Row 1: device field + 3 buttons
    Evas_Object *row1;
    Evas_Object *entry_device;
    Evas_Object *btn_take_capture;
    Evas_Object *btn_refresh;
    Evas_Object *btn_clear;

    // Row 2: token field + Load token
    Evas_Object *row2;
    Evas_Object *entry_token;
    Evas_Object *btn_load_token;

    // Image area
    Evas_Object *img_frame;
    Evas_Object *img;

    // Footer
    Evas_Object *status;
} appdata_s;

// --- stubs ---
static void on_take_capture(void *d, Evas_Object *o, void *e){(void)d;(void)o;(void)e;}
static void on_refresh     (void *d, Evas_Object *o, void *e){(void)d;(void)o;(void)e;}
static void on_clear       (void *d, Evas_Object *o, void *e){(void)d;(void)o;(void)e;}
static void on_load_token  (void *d, Evas_Object *o, void *e){(void)d;(void)o;(void)e;}

static Evas_Object* make_button(Evas_Object *parent, const char *label, Evas_Smart_Cb cb, void *ud){
    Evas_Object *b = elm_button_add(parent); if(!b) return NULL;
    elm_object_text_set(b, label);
    evas_object_smart_callback_add(b, "clicked", cb, ud);
    elm_object_focus_allow_set(b, EINA_TRUE);
    evas_object_show(b);
    return b;
}

static void ui_build(appdata_s *ad) {
    // Window
    ad->win = elm_win_util_standard_add("minimal-ui", "Device UI (Minimal)");
    if (!ad->win) return;
    elm_win_autodel_set(ad->win, EINA_TRUE);

    // Background (instead of Conformant)
    ad->bg = elm_bg_add(ad->win);
    evas_object_size_hint_weight_set(ad->bg, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->bg);
    evas_object_show(ad->bg);

    // Root vertical box attached to window directly
    ad->root = elm_box_add(ad->win);
    elm_box_padding_set(ad->root, 0, 8);
    evas_object_size_hint_weight_set(ad->root, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->root, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_win_resize_object_add(ad->win, ad->root);
    evas_object_show(ad->root);

    // Row 1
    ad->row1 = elm_box_add(ad->root);
    elm_box_horizontal_set(ad->row1, EINA_TRUE);
    evas_object_size_hint_weight_set(ad->row1, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(ad->row1, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(ad->root, ad->row1);
    evas_object_show(ad->row1);

    ad->entry_device = elm_entry_add(ad->row1);
    elm_entry_single_line_set(ad->entry_device, EINA_TRUE);
    elm_object_part_text_set(ad->entry_device, "guide", "deviceId (e.g., demo-001)");
    evas_object_size_hint_weight_set(ad->entry_device, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(ad->entry_device, EVAS_HINT_FILL, 0.5);
    evas_object_size_hint_min_set(ad->entry_device, 0, 80);
    elm_box_pack_end(ad->row1, ad->entry_device);
    evas_object_show(ad->entry_device);

    ad->btn_take_capture = make_button(ad->row1, "Take capture", on_take_capture, ad);
    ad->btn_refresh      = make_button(ad->row1, "Refresh",      on_refresh,      ad);
    ad->btn_clear        = make_button(ad->row1, "Clear",        on_clear,        ad);

    // Row 2
    ad->row2 = elm_box_add(ad->root);
    elm_box_horizontal_set(ad->row2, EINA_TRUE);
    evas_object_size_hint_weight_set(ad->row2, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(ad->row2, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(ad->root, ad->row2);
    evas_object_show(ad->row2);

    ad->entry_token = elm_entry_add(ad->row2);
    elm_entry_single_line_set(ad->entry_token, EINA_TRUE);
    elm_object_part_text_set(ad->entry_token, "guide", "device token");
    evas_object_size_hint_weight_set(ad->entry_token, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(ad->entry_token, EVAS_HINT_FILL, 0.5);
    evas_object_size_hint_min_set(ad->entry_token, 0, 80);
    elm_box_pack_end(ad->row2, ad->entry_token);
    evas_object_show(ad->entry_token);

    ad->btn_load_token = make_button(ad->row2, "Load token", on_load_token, ad);

    // Image area
    ad->img_frame = elm_frame_add(ad->root);
    elm_object_text_set(ad->img_frame, "Image");
    evas_object_size_hint_weight_set(ad->img_frame, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->img_frame, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->root, ad->img_frame);
    evas_object_show(ad->img_frame);

    ad->img = elm_image_add(ad->img_frame);
    elm_image_resizable_set(ad->img, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img, EINA_TRUE);
    evas_object_size_hint_weight_set(ad->img, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->img, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_object_content_set(ad->img_frame, ad->img);
    evas_object_show(ad->img);

    // Footer
    ad->status = elm_label_add(ad->root);
    elm_object_text_set(ad->status, "Ready — GUI only (TV/emulator-safe).");
    evas_object_size_hint_weight_set(ad->status, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(ad->status, 0.0, 0.5);
    elm_box_pack_end(ad->root, ad->status);
    evas_object_show(ad->status);

    // Finalize
    evas_object_resize(ad->win, 1920, 1080); // TV-friendly default
    evas_object_show(ad->win);
}

// lifecycle
static bool app_create(void *data) { appdata_s *ad = data; ui_build(ad); return true; }
static void app_control(app_control_h app_control, void *data){(void)app_control;(void)data;}
static void app_pause(void *data){(void)data;}
static void app_resume(void *data){(void)data;}
static void app_terminate(void *data){(void)data;}
static void ui_app_lang_changed(app_event_info_h a, void *u){(void)a;(void)u;}
static void ui_app_orient_changed(app_event_info_h a, void *u){(void)a;(void)u;}
static void ui_app_region_changed(app_event_info_h a, void *u){(void)a;(void)u;}
static void ui_app_low_memory(app_event_info_h a, void *u){(void)a;(void)u;}
static void ui_app_low_battery(app_event_info_h a, void *u){(void)a;(void)u;}

int main(int argc, char *argv[]){
    appdata_s ad = {0};
    ui_app_lifecycle_callback_s cbs = {0};
    app_event_handler_h handlers[5] = {NULL,};
    cbs.create = app_create; cbs.terminate = app_terminate; cbs.pause = app_pause; cbs.resume = app_resume; cbs.app_control = app_control;
    ui_app_add_event_handler(&handlers[APP_EVENT_LOW_MEMORY], APP_EVENT_LOW_MEMORY, ui_app_low_memory, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_LOW_BATTERY], APP_EVENT_LOW_BATTERY, ui_app_low_battery, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_LANGUAGE_CHANGED], APP_EVENT_LANGUAGE_CHANGED, ui_app_lang_changed, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_REGION_FORMAT_CHANGED], APP_EVENT_REGION_FORMAT_CHANGED, ui_app_region_changed, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_DEVICE_ORIENTATION_CHANGED], APP_EVENT_DEVICE_ORIENTATION_CHANGED, ui_app_orient_changed, &ad);
    int ret = ui_app_main(argc, argv, &cbs, &ad);
    if (ret != APP_ERROR_NONE) dlog_print(DLOG_ERROR, LOG_TAG, "ui_app_main failed: %d", ret);
    return ret;
}
