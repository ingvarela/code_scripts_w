// Horizontal box for device ID row
Evas_Object *id_hbox = elm_box_add(box);
elm_box_horizontal_set(id_hbox, EINA_TRUE);
evas_object_size_hint_weight_set(id_hbox, EVAS_HINT_EXPAND, 0.0);
evas_object_size_hint_align_set(id_hbox, EVAS_HINT_FILL, 0.0);
elm_box_pack_end(box, id_hbox);
evas_object_show(id_hbox);

// Label: "Device ID:"
Evas_Object *id_label = elm_label_add(id_hbox);
elm_object_text_set(id_label, "<align=left><font_size=30>Device ID:</font_size></align>");
evas_object_size_hint_weight_set(id_label, 0.0, 0.0);
evas_object_size_hint_align_set(id_label, 0.0, 0.5);
elm_box_pack_end(id_hbox, id_label);
evas_object_show(id_label);

// Label for actual device ID value
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
