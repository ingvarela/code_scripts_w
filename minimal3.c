#include "project.h"

/* -------- Optional tiny helpers scoped to main.c only -------- */
static Evas_Object* add_separator(Evas_Object *parent) {
    Evas_Object *sep = elm_separator_add(parent);
    elm_separator_horizontal_set(sep, EINA_TRUE);
    evas_object_size_hint_weight_set(sep, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(sep, EVAS_HINT_FILL, 0.5);
    return sep;
}

static Evas_Object* add_spacer(Evas_Object *parent, Evas_Coord h) {
    Evas_Object *rect = evas_object_rectangle_add(evas_object_evas_get(parent));
    evas_object_color_set(rect, 0, 0, 0, 0); // transparent
    evas_object_size_hint_min_set(rect, 1, h);
    return rect;
}
/* ------------------------------------------------------------- */

static bool app_create(void *data) {
    appdata_s *ad = (appdata_s *)data;

    /* Keep whatever your template already does */
    create_base_gui(ad);

    /* From here down, we ONLY add UI elements to the existing root box. */
    if (!ad || !ad->box) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Root box not available; cannot add extra UI.");
        return true;
    }

    /* Title */
    Evas_Object *title = elm_label_add(ad->box);
    elm_object_text_set(title, "<b><align=left>Device Control Panel</align></b>");
    evas_object_size_hint_weight_set(title, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(title, EVAS_HINT_FILL, 0.0);
    elm_box_pack_start(ad->box, title);
    evas_object_show(title);

    /* Small spacer */
    Evas_Object *sp1 = add_spacer(ad->box, 6);
    elm_box_pack_end(ad->box, sp1);
    evas_object_show(sp1);

    /* Token row: entry + 'Load Token' button */
    Evas_Object *token_row = elm_box_add(ad->box);
    elm_box_horizontal_set(token_row, EINA_TRUE);
    evas_object_size_hint_weight_set(token_row, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(token_row, EVAS_HINT_FILL, 0.0);
    elm_box_padding_set(token_row, 8, 0);
    elm_box_pack_end(ad->box, token_row);
    evas_object_show(token_row);

    Evas_Object *token_entry = elm_entry_add(token_row);
    elm_entry_single_line_set(token_entry, EINA_TRUE);
    elm_entry_scrollable_set(token_entry, EINA_TRUE);
    elm_object_part_text_set(token_entry, "guide", "Enter device token…");
    evas_object_size_hint_weight_set(token_entry, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(token_entry, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(token_row, token_entry);
    evas_object_show(token_entry);

    Evas_Object *btn_load_token = elm_button_add(token_row);
    elm_object_text_set(btn_load_token, "Load Token");
    evas_object_size_hint_weight_set(btn_load_token, 0.0, 0.0);
    evas_object_size_hint_align_set(btn_load_token, 0.0, 0.5);
    elm_box_pack_end(token_row, btn_load_token);
    evas_object_show(btn_load_token);

    /* Separator */
    Evas_Object *sep1 = add_separator(ad->box);
    elm_box_pack_end(ad->box, sep1);
    evas_object_show(sep1);

    /* Device status label */
    Evas_Object *status = elm_label_add(ad->box);
    elm_object_text_set(status, "<align=left>Device Status: <b>Unknown</b></align>");
    evas_object_size_hint_weight_set(status, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(status, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(ad->box, status);
    evas_object_show(status);

    /* Progress bar (for any ongoing operation) */
    Evas_Object *pb = elm_progressbar_add(ad->box);
    elm_progressbar_pulse_set(pb, EINA_TRUE);
    elm_progressbar_pulse(pb, EINA_TRUE);
    evas_object_size_hint_weight_set(pb, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(pb, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(ad->box, pb);
    evas_object_show(pb);

    /* Spacer */
    Evas_Object *sp2 = add_spacer(ad->box, 6);
    elm_box_pack_end(ad->box, sp2);
    evas_object_show(sp2);

    /* Capture row: image placeholder (uses ad->image if your base GUI created one) + 'Take Capture' button */
    Evas_Object *cap_row = elm_box_add(ad->box);
    elm_box_horizontal_set(cap_row, EINA_TRUE);
    evas_object_size_hint_weight_set(cap_row, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(cap_row, EVAS_HINT_FILL, 0.0);
    elm_box_padding_set(cap_row, 8, 0);
    elm_box_pack_end(ad->box, cap_row);
    evas_object_show(cap_row);

    /* If your base GUI already made an image widget (ad->image), re-use it visually by inserting a small label */
    Evas_Object *cap_label = elm_label_add(cap_row);
    elm_object_text_set(cap_label, "<align=left>ImageCapture:</align>");
    evas_object_size_hint_weight_set(cap_label, 0.0, 0.0);
    evas_object_size_hint_align_set(cap_label, 0.0, 0.5);
    elm_box_pack_end(cap_row, cap_label);
    evas_object_show(cap_label);

    Evas_Object *btn_capture = elm_button_add(cap_row);
    elm_object_text_set(btn_capture, "Take Capture");
    evas_object_size_hint_weight_set(btn_capture, 0.0, 0.0);
    evas_object_size_hint_align_set(btn_capture, 0.0, 0.5);
    elm_box_pack_end(cap_row, btn_capture);
    evas_object_show(btn_capture);

    /* Motion sensor toggle (use a check as a simple switch) */
    Evas_Object *motion_row = elm_box_add(ad->box);
    elm_box_horizontal_set(motion_row, EINA_TRUE);
    elm_box_padding_set(motion_row, 8, 0);
    evas_object_size_hint_weight_set(motion_row, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(motion_row, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(ad->box, motion_row);
    evas_object_show(motion_row);

    Evas_Object *motion_label = elm_label_add(motion_row);
    elm_object_text_set(motion_label, "<align=left>Motion Sensor:</align>");
    evas_object_size_hint_weight_set(motion_label, 0.0, 0.0);
    evas_object_size_hint_align_set(motion_label, 0.0, 0.5);
    elm_box_pack_end(motion_row, motion_label);
    evas_object_show(motion_label);

    Evas_Object *motion_check = elm_check_add(motion_row);
    elm_object_text_set(motion_check, "Enabled");
    evas_object_size_hint_weight_set(motion_check, 0.0, 0.0);
    evas_object_size_hint_align_set(motion_check, 0.0, 0.5);
    elm_box_pack_end(motion_row, motion_check);
    evas_object_show(motion_check);

    /* Separator */
    Evas_Object *sep2 = add_separator(ad->box);
    elm_box_pack_end(ad->box, sep2);
    evas_object_show(sep2);

    /* Common action buttons row: Connect / Settings */
    Evas_Object *actions = elm_box_add(ad->box);
    elm_box_horizontal_set(actions, EINA_TRUE);
    elm_box_padding_set(actions, 8, 0);
    evas_object_size_hint_weight_set(actions, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(actions, EVAS_HINT_FILL, 0.0);
    elm_box_pack_end(ad->box, actions);
    evas_object_show(actions);

    Evas_Object *btn_connect = elm_button_add(actions);
    elm_object_text_set(btn_connect, "Connect");
    evas_object_size_hint_weight_set(btn_connect, 0.0, 0.0);
    evas_object_size_hint_align_set(btn_connect, 0.0, 0.5);
    elm_box_pack_end(actions, btn_connect);
    evas_object_show(btn_connect);

    Evas_Object *btn_settings = elm_button_add(actions);
    elm_object_text_set(btn_settings, "Settings");
    evas_object_size_hint_weight_set(btn_settings, 0.0, 0.0);
    evas_object_size_hint_align_set(btn_settings, 0.0, 0.5);
    elm_box_pack_end(actions, btn_settings);
    evas_object_show(btn_settings);

    return true;
}

static void app_control(app_control_h app_control, void *data) {
    dlog_print(DLOG_INFO, LOG_TAG, "app_control invoked");
}

static void app_pause(void *data) {
    dlog_print(DLOG_INFO, LOG_TAG, "app_pause");
}

static void app_resume(void *data) {
    dlog_print(DLOG_INFO, LOG_TAG, "app_resume");
}

static void app_terminate(void *data) {
    dlog_print(DLOG_INFO, LOG_TAG, "app_terminate");
}

static void ui_app_lang_changed(app_event_info_h event_info, void *user_data) {
    char *locale = NULL;
    system_settings_get_value_string(SYSTEM_SETTINGS_KEY_LOCALE_LANGUAGE, &locale);
    if (locale) {
        elm_language_set(locale);
        free(locale);
    }
}

static void ui_app_orient_changed(app_event_info_h event_info, void *user_data) {
    dlog_print(DLOG_INFO, LOG_TAG, "orientation changed");
}

int main(int argc, char *argv[]) {
    appdata_s ad = {0,};
    ui_app_lifecycle_callback_s cbs = {0,};

    cbs.create = app_create;
    cbs.terminate = app_terminate;
    cbs.pause = app_pause;
    cbs.resume = app_resume;
    cbs.app_control = app_control;

    app_event_handler_h handlers[5] = {NULL,};
    ui_app_add_event_handler(&handlers[APP_EVENT_LANGUAGE_CHANGED], APP_EVENT_LANGUAGE_CHANGED, ui_app_lang_changed, &ad);
    ui_app_add_event_handler(&handlers[APP_EVENT_DEVICE_ORIENTATION_CHANGED], APP_EVENT_DEVICE_ORIENTATION_CHANGED, ui_app_orient_changed, &ad);

    int ret = ui_app_main(argc, argv, &cbs, &ad);
    if (ret != APP_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "ui_app_main() failed. err = %d", ret);
    }
    return ret;
}
