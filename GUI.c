static void create_base_gui(appdata_s *ad) {
    // --- Window setup ---
    ad->win = elm_win_util_standard_add("ST_LIVE", "SmartThings Live Capture");
    elm_win_autodel_set(ad->win, EINA_TRUE);
    evas_object_color_set(ad->win, 200, 200, 200, 255);

    // --- Conformant ---
    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // --- Main box (vertical layout) ---
    ad->box = elm_box_add(ad->conform);
    elm_box_padding_set(ad->box, 0, 10);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);

    // --- Row box for buttons (horizontal layout) ---
    Evas_Object *btn_row = elm_box_add(ad->box);
    elm_box_horizontal_set(btn_row, EINA_TRUE);
    elm_box_homogeneous_set(btn_row, EINA_TRUE);
    evas_object_size_hint_weight_set(btn_row, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(btn_row, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, btn_row);
    evas_object_show(btn_row);

    // --- Capture Once button ---
    Evas_Object *btn_capture = elm_button_add(btn_row);
    elm_object_text_set(btn_capture, "Capture Once");
    evas_object_size_hint_weight_set(btn_capture, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(btn_capture, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_smart_callback_add(btn_capture, "clicked", (Evas_Smart_Cb)take_image_capture, ad);
    elm_box_pack_end(btn_row, btn_capture);
    evas_object_show(btn_capture);

    // --- Live Capture button ---
    Evas_Object *btn_live = elm_button_add(btn_row);
    elm_object_text_set(btn_live, "Start Live Capture");
    evas_object_size_hint_weight_set(btn_live, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(btn_live, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_smart_callback_add(btn_live, "clicked", live_clicked, ad);
    elm_box_pack_end(btn_row, btn_live);
    evas_object_show(btn_live);

    // --- Show Capabilities button ---
    Evas_Object *btn_caps = elm_button_add(ad->box);
    elm_object_text_set(btn_caps, "Show Device Capabilities");
    evas_object_size_hint_weight_set(btn_caps, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(btn_caps, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_smart_callback_add(btn_caps, "clicked", show_caps_clicked, ad);
    elm_box_pack_end(ad->box, btn_caps);
    evas_object_show(btn_caps);

    // --- Image preview ---
    ad->img_view = elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, ad->img_view);
    evas_object_hide(ad->img_view);

    // --- Log section ---
    Evas_Object *scroller = elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, 0.4);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Initializing SmartThings app...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    // --- Output area ---
    ad->entry_output = elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_output, EINA_TRUE);
    elm_entry_editable_set(ad->entry_output, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_output, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_output, "Model Output:");
    evas_object_size_hint_weight_set(ad->entry_output, EVAS_HINT_EXPAND, 0.1);
    evas_object_size_hint_align_set(ad->entry_output, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, ad->entry_output);
    evas_object_show(ad->entry_output);

    // --- Show window ---
    evas_object_show(ad->win);
}