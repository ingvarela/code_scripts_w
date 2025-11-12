// ====== NEW: save directory for captures ======
#define CAPTURE_SAVE_DIR "/opt/usr/home/owner/content/Pictures/"

static void ensure_dir_exists(const char *path) {
    struct stat st = {0};
    if (stat(path, &st) == -1) {
        mkdir(path, 0777);
    }
}

// --- Capture, refresh, and loop ---
static unsigned char* readImageToBytes(const char* filePath,size_t* size){
    FILE* f=fopen(filePath,"rb"); if(!f)return NULL;
    fseek(f,0,SEEK_END); long sz=ftell(f); rewind(f);
    *size=(size_t)sz;
    unsigned char* buf=malloc(*size);
    if(!buf){ fclose(f); return NULL; }
    fread(buf,1,*size,f);
    fclose(f);
    return buf;
}

static char* encode_base64(const unsigned char* data,size_t len,size_t* outlen){
    static const char tbl[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    char* out=malloc(4*((len+2)/3)+1); size_t i=0,j=0;
    if(!out) return NULL;
    while(i<len){
        uint32_t a = i<len?data[i++]:0;
        uint32_t b = i<len?data[i++]:0;
        uint32_t c = i<len?data[i++]:0;
        uint32_t t=(a<<16)|(b<<8)|c;
        out[j++]=tbl[(t>>18)&63];
        out[j++]=tbl[(t>>12)&63];
        out[j++]=(i>len+1)?'=':tbl[(t>>6)&63];
        out[j++]=(i>len  )?'=':tbl[(t    )&63];
    }
    out[j]='\0';
    if(outlen)*outlen=j;
    return out;
}

static void take_image_capture(appdata_s *ad){
    if(!ACCESS_TOKEN){ ui_log_append(ad,"No valid ACCESS_TOKEN."); return; }

    // Ensure destination directory exists
    ensure_dir_exists(CAPTURE_SAVE_DIR);

    // Unique filename in Pictures dir
    char img_path[512];
    snprintf(img_path,sizeof(img_path), "%scapture_%ld.jpg", CAPTURE_SAVE_DIR, (long)time(NULL));

    char url[512];
    snprintf(url,sizeof(url),"%s/devices/%s/commands",API_BASE,DEVICE_ID);

    // (Optional) Refresh before take — kept from your original behavior
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\",\"command\":\"refresh\",\"arguments\":[]}]}";
    ui_log_append(ad, "Sending refresh command...");
    char *r1 = http_post(url, ACCESS_TOKEN, payload_refresh);
    if (!r1) ui_log_append(ad, "Failed to send refresh command.");
    free(r1);
    sleep(5);

    // Take snapshot
    ui_log_append(ad, "Requesting image capture...");
    const char payload_take[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\",\"command\":\"take\",\"arguments\":[]}]}";
    char *r2 = http_post(url, ACCESS_TOKEN, payload_take);
    free(r2);
    sleep(5);

    // Get status to find image URL
    snprintf(url,sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    char *status = http_get(url, ACCESS_TOKEN);
    if (!status) { ui_log_append(ad, "Failed to fetch device status."); return; }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "No image URL found in status.");
        free(status);
        return;
    }

    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    // Download to Pictures dir
    ui_log_append(ad, "Downloading captured image...");
    if (!http_download_file(image_url, ACCESS_TOKEN, img_path)) {
        ui_log_append(ad, "Failed to download image.");
        return;
    }

    // Show on UI
    ui_log_append(ad, "Image updated.");
    elm_image_file_set(ad->img_view, img_path, NULL);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    evas_object_show(ad->img_view);

    char log_message[512];
    snprintf(log_message,sizeof(log_message), "Image saved at: %s", img_path);
    ui_log_append(ad, log_message);

    // Base64 + prompt.json in the same Pictures dir
    size_t img_size = 0;
    unsigned char *img_data = readImageToBytes(img_path, &img_size);
    if (!img_data) { ui_log_append(ad, "Failed to read image data."); return; }

    size_t out_len = 0;
    char *base64 = encode_base64(img_data, img_size, &out_len);
    free(img_data);
    if (!base64) { ui_log_append(ad, "Base64 encoding failed."); return; }

    char txt_path[512];
    snprintf(txt_path,sizeof(txt_path), "%sbase64_img.txt", CAPTURE_SAVE_DIR);
    FILE *txt = fopen(txt_path, "w");
    if (txt) {
        fwrite(base64, 1, out_len, txt);
        fclose(txt);
        ui_log_append(ad, "Base64 encoded image saved to base64_img.txt");
    } else {
        ui_log_append(ad, "Failed to save base64_img.txt");
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
            snprintf(json_path,sizeof(json_path), "%sprompt.json", CAPTURE_SAVE_DIR);
            FILE *jf = fopen(json_path, "w");
            if (jf) {
                fprintf(jf, "%s", json_str);
                fclose(jf);
                ui_log_append(ad, "prompt.json created successfully.");
            } else {
                ui_log_append(ad, "Failed to create prompt.json.");
            }
            free(json_str);
        } else {
            ui_log_append(ad, "Failed to serialize JSON.");
        }
        cJSON_Delete(json);
    }
    free(base64);
    sleep(3);
}

// ------------------------------
// Live capture loop (kept as your consecutive mode)
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
        ui_log_append(ad, "Starting live capture (consecutive)...");
        ecore_timer_add(REFRESH_INTERVAL_SEC, live_loop_cb, ad);
    } else {
        ad->live_running = false;
        elm_object_text_set(obj, "Start Live Capture");
        ui_log_append(ad, "Live capture stopped.");
    }
}

// ------------------------------
// Single-shot capture button handler
// ------------------------------
static void capture_once_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    ui_log_append(ad, "Capturing single image...");
    take_image_capture(ad);
}

// ------------------------------
// Show device capabilities (unchanged)
// ------------------------------
static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (!ACCESS_TOKEN) { ui_log_append(ad, "No ACCESS_TOKEN."); return; }
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);
    ui_log_append(ad, "Fetching device capabilities...");
    char *resp = http_get(url, ACCESS_TOKEN);
    if (resp) {
        ui_log_append(ad, "<b>Capabilities:</b>");
        ui_log_append(ad, resp);
        free(resp);
    } else {
        ui_log_append(ad, "Failed to fetch capabilities.");
    }
}

// ------------------------------
// GUI: add a new "Capture Once" button; keep the rest intact
// ------------------------------
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("ST_LIVE","SmartThings Live Capture");
    elm_win_autodel_set(ad->win,EINA_TRUE);
    evas_object_color_set(ad->win,200,200,200,255);

    ad->conform=elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win,ad->conform);
    evas_object_show(ad->conform);

    ad->box=elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform,ad->box);
    evas_object_show(ad->box);

    // Show Capabilities (same)
    Evas_Object *btn_caps=elm_button_add(ad->box);
    elm_object_text_set(btn_caps,"Show Capabilities");
    evas_object_smart_callback_add(btn_caps,"clicked",show_caps_clicked,ad);
    evas_object_size_hint_weight_set(btn_caps,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,btn_caps);
    evas_object_show(btn_caps);

    // Image view (same)
    ad->img_view=elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view,EINA_TRUE,EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view,EINA_FALSE);
    evas_object_size_hint_weight_set(ad->img_view,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->img_view,EVAS_HINT_FILL,EVAS_HINT_FILL);
    elm_box_pack_end(ad->box,ad->img_view);
    evas_object_hide(ad->img_view);

    // NEW: Capture Once button
    Evas_Object *btn_once=elm_button_add(ad->box);
    elm_object_text_set(btn_once,"Capture Once");
    evas_object_smart_callback_add(btn_once,"clicked",capture_once_clicked,ad);
    evas_object_size_hint_weight_set(btn_once,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,btn_once);
    evas_object_show(btn_once);

    // Existing: Start Live Capture (consecutive loop)
    Evas_Object *btn_live=elm_button_add(ad->box);
    elm_object_text_set(btn_live,"Start Live Capture");
    evas_object_smart_callback_add(btn_live,"clicked",live_clicked,ad);
    evas_object_size_hint_weight_set(btn_live,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,btn_live);
    evas_object_show(btn_live);

    // Log scroller (same)
    Evas_Object *scroller=elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller,EVAS_HINT_EXPAND,0.4);
    evas_object_size_hint_align_set(scroller,EVAS_HINT_FILL,EVAS_HINT_FILL);
    elm_box_pack_end(ad->box,scroller);

    ad->entry_log=elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log,EINA_TRUE);
    elm_entry_editable_set(ad->entry_log,EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log,ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log,"Initializing SmartThings app...");
    elm_object_content_set(scroller,ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    // Model output (same)
    ad->entry_output=elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_output,EINA_TRUE);
    elm_entry_editable_set(ad->entry_output,EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_output,ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_output,"Model Output:");
    evas_object_size_hint_weight_set(ad->entry_output,EVAS_HINT_EXPAND,0.1);
    evas_object_size_hint_align_set(ad->entry_output,EVAS_HINT_FILL,EVAS_HINT_FILL);
    elm_box_pack_end(ad->box,ad->entry_output);
    evas_object_show(ad->entry_output);

    evas_object_show(ad->win);
}