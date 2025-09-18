// --- SmartThings Connect Button ---
Evas_Object *st_btn = elm_button_add(box);
elm_object_text_set(st_btn, "<font_size=28>SmartThings Connect</font_size>");
evas_object_size_hint_weight_set(st_btn, EVAS_HINT_EXPAND, 0.0);
evas_object_size_hint_align_set(st_btn, EVAS_HINT_FILL, 0.0);
evas_object_smart_callback_add(st_btn, "clicked", _smartthings_connect_cb, ad);
elm_box_pack_end(box, st_btn);
evas_object_show(st_btn);

// --- SmartThings Status Label ---
ad->status_label = elm_label_add(box);
elm_object_text_set(ad->status_label, "<align=left><font_size=30><color=#444444>SmartThings Status: N/A</color></font_size></align>");
evas_object_size_hint_weight_set(ad->status_label, EVAS_HINT_EXPAND, 0.0);
evas_object_size_hint_align_set(ad->status_label, EVAS_HINT_FILL, 0.0);
elm_box_pack_end(box, ad->status_label);
evas_object_show(ad->status_label);
