#include "st_app.h"
#include <system_info.h>  // Needed for device ID retrieval

typedef struct appdata {
	Evas_Object *win;
	Evas_Object *conform;
	Evas_Object *label;
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
	/* Let window go to hide state. */
	elm_win_lower(ad->win);
}

static void
_btn_click_cb(void *data, Evas_Object *obj, void *event_info)
{
	appdata_s *ad = data;
	elm_object_text_set(ad->label, "<align=center>Button Clicked!</align>");
}

static void
create_base_gui(appdata_s *ad)
{
	/* Window */
	ad->win = elm_win_util_standard_add(PACKAGE, PACKAGE);
	elm_win_autodel_set(ad->win, EINA_TRUE);

	if (elm_win_wm_rotation_supported_get(ad->win)) {
		int rots[4] = { 0, 90, 180, 270 };
		elm_win_wm_rotation_available_rotations_set(ad->win, (const int *)(&rots), 4);
	}

	evas_object_smart_callback_add(ad->win, "delete,request", win_delete_request_cb, NULL);
	eext_object_event_callback_add(ad->win, EEXT_CALLBACK_BACK, win_back_cb, ad);

	/* Conformant */
	ad->conform = elm_conformant_add(ad->win);
	elm_win_indicator_mode_set(ad->win, ELM_WIN_INDICATOR_SHOW);
	elm_win_indicator_opacity_set(ad->win, ELM_WIN_INDICATOR_OPAQUE);
	evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
	elm_win_resize_object_add(ad->win, ad->conform);
	evas_object_show(ad->conform);

	/* Main vertical box */
	Evas_Object *box = elm_box_add(ad->conform);
	evas_object_size_hint_weight_set(box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
	elm_box_padding_set(box, 0, 20);
	evas_object_show(box);
	elm_object_content_set(ad->conform, box);

	/* Horizontal box for Device ID row */
	Evas_Object *id_hbox = elm_box_add(box);
	elm_box_horizontal_set(id_hbox, EINA_TRUE);
	evas_object_size_hint_weight_set(id_hbox, EVAS_HINT_EXPAND, 0.0);
	evas_object_size_hint_align_set(id_hbox, EVAS_HINT_FILL, 0.0);
	elm_box_pack_end(box, id_hbox);
	evas_object_show(id_hbox);

	/* Label: "Device ID:" */
	Evas_Object *id_label = elm_label_add(id_hbox);
	elm_object_text_set(id_label, "<align=left><font_size=30>Device ID:</font_size></align>");
	evas_object_size_hint_weight_set(id_label, 0.0, 0.0);
	evas_object_size_hint_align_set(id_label, 0.0, 0.5);
	elm_box_pack_end(id_hbox, id_label);
	evas_object_show(id_label);

	/* Label for device ID value */
	Evas_Object *id_value_label = elm_label_add(id_hbox);
	char *device_id = NULL;
	int res = system_info_get_platform_string("http://tizen.org/system/tizenid", &device_id);
	if (res == SYSTEM_INFO_ERROR_NONE && device_id) {
		char formatted_id[128];
		snprintf(formatted_id, sizeof(formatted_id), "<align=right><font_size=30>%s</font_size></align>", device_id);
		elm_object_text_set(id_value_label, formatted_id);
		free(device_id);
	} else {
		elm_object_text_set(id_value_label, "<align=right><font_size=30>Unknown</font_size></align>");
	}
	evas_object_size_hint_weight_set(id_value_label, EVAS_HINT_EXPAND, 0.0);
	evas_object_size_hint_align_set(id_value_label, 1.0, 0.5);
	elm_box_pack_end(id_hbox, id_value_label);
	evas_object_show(id_value_label);

	/* Hello Tizen Label */
	ad->label = elm_label_add(box);
	elm_object_text_set(ad->label, "<align=center>Hello Tizen</align>");
	evas_object_size_hint_weight_set(ad->label, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
	evas_object_size_hint_align_set(ad->label, EVAS_HINT_FILL, 0.5);
	elm_box_pack_end(box, ad->label);
	evas_object_show(ad->label);

	/* Button */
	Evas_Object *btn = elm_button_add(box);
	elm_object_text_set(btn, "Click Me");
	evas_object_smart_callback_add(btn, "clicked", _btn_click_cb, ad);
	evas_object_size_hint_weight_set(btn, EVAS_HINT_EXPAND, 0.0);
	evas_object_size_hint_align_set(btn, EVAS_HINT_FILL, 0.5);
	elm_box_pack_end(box, btn);
	evas_object_show(btn);

	/* Show window */
	evas_object_show(ad->win);
}

static bool
app_create(void *data)
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
	if (ret != APP_ERROR_NONE) {
		dlog_print(DLOG_ERROR, LOG_TAG, "app_event_get_language() failed. Err = %d.", ret);
		return;
	}

	if (language != NULL) {
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
	int ret = 0;

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
		dlog_print(DLOG_ERROR, LOG_TAG, "app_main() is failed. err = %d", ret);
	}

	return ret;
}

