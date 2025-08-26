#include "st_app.h"
#include <system_info.h>
#include <download.h>

#define DOWNLOAD_IMAGE_PATH "/opt/usr/media/Downloads/capture.jpg"

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *image_box;
    Evas_Object *url_entry;
    download_h download;
} appdata_s;

static void
win_delete_request_cb(void *data, Evas_Object *obj, void *event_info)
{
    ui_app_exit();
}

static void
win_back_cb(void *data, Evas_Object *obj, void *event_info)
{
    appdata_s *ad = data;
    elm_win_lower(ad->win);
}

static void
_take_capture_cb(void *data, Evas_Object *obj, void *event_info)
{
    dlog_print(DLOG_INFO, LOG_TAG, "Take Capture button clicked.");
}

static void
download_completed_cb(download_h download, const char *file_path, void *user_data)
{
    appdata_s *ad = (appdata_s *)user_data;
    dlog_print(DLOG_INFO, LOG_TAG, "Download completed: %s", file_path);

    if (!elm_image_file_set(ad->image_box, file_path, NULL)) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Failed to display downloaded image.");
    }
}

static void
_load_capture_cb(void *data, Evas_Object *obj, void *event_info)
{
    appdata_s *ad = data;

    const char *url = elm_object_text_get(ad->url_entry);
    if (!url || strlen(url) == 0) {
        dlog_print(DLOG_WARN, LOG_TAG, "No URL entered.");
        return;
    }

    int ret = download_set_url(ad->download, url);
    if (ret != DOWNLOAD_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Failed to set URL: %d", ret);
        return;
    }

    ret = download_set_destination(ad->download, DOWNLOAD_IMAGE_PATH);
    if (ret != DOWNLOAD_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Failed to set destination: %d", ret);
        return;
    }

    ret = download_start(ad->download);
    if (ret != DOWNLOAD_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Download start failed: %d", ret);
    }
}

static Evas_Object*
create_spacer(Evas_Object *parent, int height)
{
    Evas_Object *rect = evas_object_rectangle_add(evas_object_evas_get(parent));
    evas_object_color_set(rect, 0, 0, 0, 0);
    evas_object_size_hint_min_set(rect, 1, height);
    evas_object_show(rect);
    return rect;
}

static void
create_base_gui(appdata_s *ad)
{
    ad->win = elm_win_util_standard_add(PACKAGE, PACKAGE);
    elm_win_autodel_set(ad->win, EINA_TRUE);

    if (elm_win_wm_rotation_supported_get(ad->win)) {
        int rots[4] = { 0, 90, 180, 270 };
        elm_win_wm_rotation_available_rotations_set(ad->win, rots, 4);
    }

    evas_object_smart_callback_add(ad->win, "delete,request", win_delete_request_cb, NULL);
    eext_object_event_callback_add(ad->win, EEXT_CALLBACK_BACK, win_back_cb, ad);

    ad->conform = elm_conformant_add(ad->win);
    elm_win_indicator_mode_set(ad->win, ELM_WIN_INDICATOR_SHOW);
    elm_win_indicator_opacity_set(ad->win, ELM_WIN_INDICATOR_OPAQUE);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    Evas_Object *box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_box_padding_set(box, 0, 15);
    evas_object_show(box);
    elm_object_content_set(ad->conform, box);

    // Title
    Evas_Object *title = elm_label_add(box);
    elm_object_text_set(title, "<align=center><font_size=40><color=#2e86de>Smart Thing Client Device Control App</color></font_size></align>");
    evas_object_size_hint_weight_set(title, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(title, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(box, title);
    evas_object_show(title);

    elm_box_pack_end(box, create_spacer(box, 5));

    // Device ID row
    Evas_Object *id_hbox = elm_box_add(box);
    elm_box_horizontal_set(id_hbox, EINA_TRUE);
    evas_object_size_hint_weight_set(id_hbox, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(id_hbox, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(box, id_hbox);
    evas_object_show(id_hbox);

    Evas_Object *id_label = elm_label_add(id_hbox);
    elm_object_text_set(id_label, "<align=left><font_size=32><color=#555555>Device ID:</color></font_size></align>");
    evas_object_size_hint_weight_set(id_label, 0.0, 0.0);
    evas_object_size_hint_align_set(id_label, 0.0, 0.5);
    elm_box_pack_end(id_hbox, id_label);
    evas_object_show(id_label);

    Evas_Object *id_value_label = elm_label_add(id_hbox);
    char *device_id = NULL;
    int res = system_info_get_platform_string("http://tizen.org/system/tizenid", &device_id);
    if (res == SYSTEM_INFO_ERROR_NONE && device_id) {
        char formatted_id[128];
        snprintf(formatted_id, sizeof(formatted_id), "<align=right><font_size=32><color=#000000>%s</color></font_size></align>", device_id);
        elm_object_text_set(id_value_label, formatted_id);
        free(device_id);
    } else {
        elm_object_text_set(id_value_label, "<align=right><font_size=32><color=#999999>Unknown</color></font_size></align>");
    }
    evas_object_size_hint_weight_set(id_value_label, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(id_value_label, 1.0, 0.5);
    elm_box_pack_end(id_hbox, id_value_label);
    evas_object_show(id_value_label);

    elm_box_pack_end(box, create_spacer(box, 10));

    // Device status, capabilities, motion capture
    const char* labels[] = {
        "Device Status: [status]",
        "Capabilities:",
        "MotionCapture Status: [value]",
        "ImageCapture:"
    };
    for (int i = 0; i < 4; ++i) {
        Evas_Object *lbl = elm_label_add(box);
        char buf[256];
        snprintf(buf, sizeof(buf), "<align=left><font_size=30><color=#444444>%s</color></font_size></align>", labels[i]);
        elm_object_text_set(lbl, buf);
        evas_object_size_hint_weight_set(lbl, EVAS_HINT_EXPAND, 0.0);
        evas_object_size_hint_align_set(lbl, EVAS_HINT_FILL, 0.0);
        elm_box_pack_end(box, lbl);
        evas_object_show(lbl);
    }

    // URL Entry
    ad->url_entry = elm_entry_add(box);
    elm_entry_single_line_set(ad->url_entry, EINA_TRUE);
    elm_entry_scrollable_set(ad->url_entry, EINA_TRUE);
    elm_object_part_text_set(ad->url_entry, "guide", "Paste image URL here...");
    elm_entry_input_panel_layout_set(ad->url_entry, ELM_INPUT_PANEL_LAYOUT_URL);
    elm_entry_cnp_mode_set(ad->url_entry, ELM_CNP_MODE_PLAINTEXT);
    evas_object_size_hint_weight_set(ad->url_entry, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(ad->url_entry, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(box, ad->url_entry);
    evas_object_show(ad->url_entry);

    // Buttons
    Evas_Object *btn_hbox = elm_box_add(box);
    elm_box_horizontal_set(btn_hbox, EINA_TRUE);
    evas_object_size_hint_weight_set(btn_hbox, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_hbox, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(box, btn_hbox);
    evas_object_show(btn_hbox);

    Evas_Object *capture_btn = elm_button_add(btn_hbox);
    elm_object_text_set(capture_btn, "<font_size=28>Take Capture</font_size>");
    evas_object_smart_callback_add(capture_btn, "clicked", _take_capture_cb, ad);
    evas_object_size_hint_weight_set(capture_btn, 0.5, 0.0);
    evas_object_size_hint_align_set(capture_btn, 0.5, 0.5);
    elm_box_pack_end(btn_hbox, capture_btn);
    evas_object_show(capture_btn);

    Evas_Object *load_btn = elm_button_add(btn_hbox);
    elm_object_text_set(load_btn, "<font_size=28>Load Capture</font_size>");
    evas_object_smart_callback_add(load_btn, "clicked", _load_capture_cb, ad);
    evas_object_size_hint_weight_set(load_btn, 0.5, 0.0);
    evas_object_size_hint_align_set(load_btn, 0.5, 0.5);
    elm_box_pack_end(btn_hbox, load_btn);
    evas_object_show(load_btn);

    elm_box_pack_end(box, create_spacer(box, 15));

    // Image box
    ad->image_box = elm_image_add(box);
    evas_object_size_hint_weight_set(ad->image_box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->image_box, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_image_file_set(ad->image_box, "/opt/usr/apps/org.example.st_app/res/images/placeholder.png", NULL);
    elm_box_pack_end(box, ad->image_box);
    evas_object_show(ad->image_box);

    // Prepare download handle
    int ret = download_create(&ad->download);
    if (ret != DOWNLOAD_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "download_create() failed: %d", ret);
        return;
    }

    ret = download_set_completed_cb(ad->download, download_completed_cb, ad);
    if (ret != DOWNLOAD_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "download_set_completed_cb() failed: %d", ret);
    }
}

static bool app_create(void *data)
{
    appdata_s *ad = data;
    create_base_gui(ad);
    return true;
}

static void app_control(app_control_h app_control, void *data) { }
static void app_pause(void *data) { }
static void app_resume(void *data) { }
static void app_terminate(void *data) { }

static void ui_app_lang_changed(app_event_info_h event_info, void *user_data)
{
    int ret;
    char *language;
    ret = app_event_get_language(event_info, &language);
    if (ret == APP_ERROR_NONE && language != NULL) {
        elm_language_set(language);
        free(language);
    }
}

static void ui_app_orient_changed(app_event_info_h event_info, void *user_data) { }
static void ui_app_region_changed(app_event_info_h event_info, void *user_data) { }
static void ui_app_low_battery(app_event_info_h event_info, void *user_data) { }
static void ui_app_low_memory(app_event_info_h event_info, void *user_data) { }

int main(int argc, char *argv[])
{
    appdata_s ad = {0,};
    int ret;

    ui_app_lifecycle_callback_s event_callback = {0,};
    app_event_handler_h handlers[5] = {NULL, };

    event_callback.create = app_create;
    event_callback.terminate = app_terminate;
    event_callback.pause = app_pause;
    event_callback.resume = app_resume;
    event_callback.app_control = app_control;

    ui_app_add_event_handler(&handlers[APP_EVENT_LOW_BATTERY], APP_EVENT_LOW_BATTERY, ui_app_low_battery, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_LOW_MEMORY], APP_EVENT_LOW_MEMORY, ui_app_low_memory, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_DEVICE_ORIENTATION_CHANGED], APP_EVENT_DEVICE_ORIENTATION_CHANGED, ui_app_orient_changed, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_LANGUAGE_CHANGED], APP_EVENT_LANGUAGE_CHANGED, ui_app_lang_changed, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_REGION_FORMAT_CHANGED], APP_EVENT_REGION_FORMAT_CHANGED, ui_app_region_changed, &ad);

    ret = ui_app_main(argc, argv, &event_callback, &ad);
    if (ret != APP_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "app_main() failed: %d", ret);
    }

    return ret;
}
