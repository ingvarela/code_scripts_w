\":[]}]}";
    ui_log_append(ad, "Sending refresh command...");
    char *r1 = http_post(url, ACCESS_TOKEN, payload_refresh);
    if (!r1) ui_log_append(ad, "⚠️ Failed to send refresh command.");
    free(r1);
    sleep(5);

    ui_log_append(ad, "Requesting image capture...");
    const char payload_take[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    char *r2 = http_post(url, ACCESS_TOKEN, payload_take);
    free(r2);
    sleep(5);

    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    char *status = http_get(url, ACCESS_TOKEN);
    if (!status) { ui_log_append(ad, "❌ Failed to fetch device status."); return; }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "⚠️ No image URL found in status.");
        free(status);
        return;
    }

    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    ui_log_append(ad, "Downloading captured image...");
    if (!http_download_file(image_url, ACCESS_TOKEN, img_path)) {
        ui_log_append(ad, "❌ Failed to download image.");
        return;
    }

    ui_log_append(ad, "✅ Image updated.");
    elm_image_file_set(ad->img_view, img_path, NULL);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    evas_object_show(ad->img_view);

    char log_message[512];
    snprintf(log_message, sizeof(log_message), "📸 Image saved at: %s", img_path);
    ui_log_append(ad, log_message);

    size_t img_size = 0;
    unsigned char *img_data = readImageToBytes(img_path, &img_size);
    if (!img_data) { ui_log_append(ad, "Failed to read image data."); return; }

    size_t out_len = 0;
    char *base64 = encode_base64(img_data, img_size, &out_len);
    free(img_data);
    if (!base64) { ui_log_append(ad, "Base64 encoding failed."); return; }

    char txt_path[512];
    snprintf(txt_path, sizeof(txt_path), "%sbase64_img.txt", TOKEN_DIR);
    FILE *txt = fopen(txt_path, "w");
    if (txt) {
        fwrite(base64, 1, out_len, txt);
        fclose(txt);
        ui_log_append(ad, "💾 Base64 encoded image saved to base64_img.txt");
    } else {
        ui_log_append(ad, "⚠️ Failed to save base64_img.txt");
    }

    cJSON *json = cJSON_CreateObject();
    if (json) {
        cJSON_AddStringToObject(json, "method", "generate_from_image");
        cJSON *params = cJSON_CreateArray();
        cJSON_AddItemToArray(params, cJSON_CreateString(
            "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
            "<|im_start|>user\n<image> Please identify the layout of the keyboard on the screen. "
            "Return the result as a comma-separated string with elements from each row.<|im_end|>\n"
            "<|im_start|>assistant\n"));
        cJSON_AddItemToArray(params, cJSON_CreateString(base64));
        cJSON_AddItemToObject(json, "params", params);
        cJSON_AddNumberToObject(json, "id", 42);

        char *json_str = cJSON_Print(json);
        if (json_str) {
            char json_path[512];
            snprintf(json_path, sizeof(json_path), "%sprompt.json", TOKEN_DIR);
            FILE *jf = fopen(json_path, "w");
            if (jf) {
                fprintf(jf, "%s", json_str);
                fclose(jf);
                ui_log_append(ad, "✅ prompt.json created successfully.");
            } else ui_log_append(ad, "❌ Failed to create prompt.json.");
            free(json_str);
        } else ui_log_append(ad, "⚠️ Failed to serialize JSON.");
        cJSON_Delete(json);
    }
    free(base64);
    sleep(3);
}

// ------------------------------
// Live capture loop
// ------------------------------
static Eina_Bool live_loop_cb(void *data) {
    appdata_s *ad = data;
    if (!ad->live_running) return ECORE_CALLBACK_CANCEL;
    take_image_capture(ad);
    return ad->live_running ? ECORE_CALLBACK_RENEW : ECORE_CALLBACK_CANCEL;
}

static void live_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (!ad->live_running) {
        ad->live_running = true;
        elm_object_text_set(obj, "Stop Live Capture");
        ui_log_append(ad, "Starting live capture...");
        ecore_timer_add(REFRESH_INTERVAL_SEC, live_loop_cb, ad);
    } else {
        ad->live_running = false;
        elm_object_text_set(obj, "Start Live Capture");
        ui_log_append(ad, "Live capture stopped.");
    }
}

// ------------------------------
// Show device capabilities
// ------------------------------
static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (!ACCESS_TOKEN) { ui_log_append(ad, "⚠️ No ACCESS_TOKEN."); return; }
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);
    ui_log_append(ad, "Fetching device capabilities...");
    char *resp = http_get(url, ACCESS_TOKEN);
    if (resp) {
        ui_log_append(ad, "<b>Capabilities:</b>");
        ui_log_append(ad, resp);
        free(resp);
    } else ui_log_append(ad, "❌ Failed to fetch capabilities.");
}

// ------------------------------
// Application lifecycle
// ------------------------------
static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    create_base_gui(ad);
    ui_log_append(ad, "🚀 Initializing SmartThings Token System...");

    if (initialize_token_file(ad)) {
        ui_log_append(ad, "✅ Token system ready. SmartThings API available.");
    } else {
        ui_log_append(ad, "❌ Token initialization failed. Check credentials.");
    }

    // Attach button callbacks
    Evas_Object *btn_caps = elm_object_item_widget_get(elm_box_children_get(ad->box)[0]);
    Evas_Object *btn_live = elm_object_item_widget_get(elm_box_children_get(ad->box)[2]);
    evas_object_smart_callback_add(btn_caps, "clicked", show_caps_clicked, ad);
    evas_object_smart_callback_add(btn_live, "clicked", live_clicked, ad);

    return true;
}

static void app_control(app_control_h app_control, void *data) {}
static void app_pause(void *data) {}
static void app_resume(void *data) {}
static void app_terminate(void *data) { curl_global_cleanup(); }

// ------------------------------
// Main entry
// ------------------------------
int main(int argc, char *argv[]) {
    appdata_s ad = {0,};
    ui_app_lifecycle_callback_s event_callback = {0,};
    event_callback.create = app_create;
    event_callback.terminate = app_terminate;
    event_callback.pause = app_pause;
    event_callback.resume = app_resume;
    event_callback.app_control = app_control;
    return ui_app_main(argc, argv, &event_callback, &ad);
}