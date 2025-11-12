static void create_base_gui(appdata_s *ad) {

    // Window
    ad->win = elm_win_util_standard_add("ST_LIVE","SmartThings Live Capture");
    elm_win_autodel_set(ad->win, EINA_TRUE);
    evas_object_color_set(ad->win, 200,200,200,255);

    // Conformant
    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // Main vertical container
    ad->box = elm_box_add(ad->conform);
    elm_box_horizontal_set(ad->box, EINA_FALSE);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);


    /* =======================================================
     *  BUTTON ROW (HORIZONTAL)
     * =======================================================*/
    Evas_Object *button_row = elm_box_add(ad->box);
    elm_box_horizontal_set(button_row, EINA_TRUE);  

    // Make the row fixed height
    evas_object_size_hint_weight_set(button_row, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(button_row, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, button_row);
    evas_object_show(button_row);

    // BUTTON: Show Capabilities
    Evas_Object *btn_caps = elm_button_add(button_row);
    elm_object_text_set(btn_caps, "Show Capabilities");
    evas_object_smart_callback_add(btn_caps,"clicked",show_caps_clicked,ad);
    evas_object_size_hint_weight_set(btn_caps, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_caps, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(button_row, btn_caps);
    evas_object_show(btn_caps);

    // BUTTON: Capture Once
    Evas_Object *btn_once = elm_button_add(button_row);
    elm_object_text_set(btn_once, "Capture Once");
    evas_object_smart_callback_add(btn_once,"clicked",capture_once_clicked,ad);
    evas_object_size_hint_weight_set(btn_once, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_once, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(button_row, btn_once);
    evas_object_show(btn_once);

    // BUTTON: Start Live Capture
    Evas_Object *btn_live = elm_button_add(button_row);
    elm_object_text_set(btn_live, "Start Live Capture");
    evas_object_smart_callback_add(btn_live,"clicked",live_clicked,ad);
    evas_object_size_hint_weight_set(btn_live, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_live, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(button_row, btn_live);
    evas_object_show(btn_live);


    /* =======================================================
     *  IMAGE VIEW  (TAKES MOST SPACE)
     * =======================================================*/
    ad->img_view = elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);

    // Make image the largest area (weight 4)
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, 4.0);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, ad->img_view);
    evas_object_hide(ad->img_view);  // until first capture


    /* =======================================================
     *  LOG VIEW (Scroller + Entry)
     * =======================================================*/
    Evas_Object *scroller = elm_scroller_add(ad->box);
    elm_scroller_policy_set(scroller, ELM_SCROLLER_POLICY_AUTO, ELM_SCROLLER_POLICY_AUTO);

    // Medium amount of space (weight 2)
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, 2.0);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, scroller);
    evas_object_show(scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Initializing SmartThings app...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);


    /* =======================================================
     *  MODEL OUTPUT
     * =======================================================*/
    ad->entry_output = elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_output, EINA_TRUE);
    elm_entry_editable_set(ad->entry_output, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_output, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_output, "Model Output:");

    // Smallest space (weight 1)
    evas_object_size_hint_weight_set(ad->entry_output, EVAS_HINT_EXPAND, 1.0);
    evas_object_size_hint_align_set(ad->entry_output, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, ad->entry_output);
    evas_object_show(ad->entry_output);


    /* =======================================================
     *  SHOW WINDOW
     * =======================================================*/
    evas_object_show(ad->win);
}