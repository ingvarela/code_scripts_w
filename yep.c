// ======================================================
// IMAGE CAPTURE — timestamped, reliable, and prompt.json per capture
// ======================================================

#define SAVE_FOLDER "/opt/usr/home/owner/content/Pictures/"

// --- Utility: timestamp string ---
static void current_timestamp(char *buf, size_t size) {
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    strftime(buf, size, "%Y%m%d_%H%M%S", t);
}

// --- Read file into bytes ---
static unsigned char* readImageToBytes(const char* filePath, size_t* size) {
    FILE* f = fopen(filePath, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    *size = sz;
    unsigned char* buf = malloc(sz);
    if (!buf) { fclose(f); return NULL; }
    fread(buf, 1, sz, f);
    fclose(f);
    return buf;
}

// --- Encode Base64 ---
static char* encode_base64(const unsigned char* data, size_t len, size_t* outlen) {
    static const char tbl[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    char* out = malloc(4 * ((len + 2) / 3) + 1);
    if (!out) return NULL;
    size_t i, j;
    for (i = 0, j = 0; i < len;) {
        uint32_t a = i < len ? data[i++] : 0;
        uint32_t b = i < len ? data[i++] : 0;
        uint32_t c = i < len ? data[i++] : 0;
        uint32_t t = (a << 16) | (b << 8) | c;
        out[j++] = tbl[(t >> 18) & 63];
        out[j++] = tbl[(t >> 12) & 63];
        out[j++] = (i > len + 1) ? '=' : tbl[(t >> 6) & 63];
        out[j++] = (i > len) ? '=' : tbl[t & 63];
    }
    out[j] = '\0';
    *outlen = j;
    return out;
}

// --- Conditional header for SmartThings signed URLs ---
static bool http_download_file_smart(const char *url, const char *token, const char *save_path) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;
    FILE *fp = fopen(save_path, "wb");
    if (!fp) { curl_easy_cleanup(curl); return false; }

    struct curl_slist *headers = NULL;
    if (!strstr(url, "?token=")) {
        char auth[512];
        snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
        headers = curl_slist_append(headers, auth);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, NULL);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, fp);
    CURLcode res = curl_easy_perform(curl);

    if (headers) curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    fclose(fp);
    return (res == CURLE_OK);
}

// --- Single capture with prompt.json per image ---
static void take_image_capture(appdata_s *ad) {
    if (!ACCESS_TOKEN) {
        ui_log_append(ad, "⚠️ No valid ACCESS_TOKEN.");
        return;
    }

    char timestamp[64];
    current_timestamp(timestamp, sizeof(timestamp));

    char img_path[512];
    snprintf(img_path, sizeof(img_path), "%scapture_%s.jpg", SAVE_FOLDER, timestamp);

    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);

    // 1️⃣ Refresh
    ui_log_append(ad, "🔁 Sending refresh command...");
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";
    char *r1 = http_post(url, ACCESS_TOKEN, payload_refresh);
    if (!r1) ui_log_append(ad, "❌ Failed to send refresh command.");
    free(r1);
    sleep(5);

    // 2️⃣ Trigger capture
    ui_log_append(ad, "📸 Triggering image capture...");
    const char payload_take[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    char *r2 = http_post(url, ACCESS_TOKEN, payload_take);
    free(r2);
    sleep(5);

    // 3️⃣ Fetch status for image URL
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    ui_log_append(ad, "📡 Fetching latest device status...");
    char *status = http_get(url, ACCESS_TOKEN);
    if (!status) { ui_log_append(ad, "❌ Failed to fetch device status."); return; }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "⚠️ No image URL found in status response.");
        free(status);
        return;
    }

    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    // 4️⃣ Download new image
    ui_log_append(ad, "⬇️ Downloading captured image...");
    if (!http_download_file_smart(image_url, ACCESS_TOKEN, img_path)) {
        ui_log_append(ad, "❌ Failed to download image.");
        return;
    }

    // 5️⃣ Display the image
    elm_image_file_set(ad->img_view, img_path, NULL);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    evas_object_show(ad->img_view);

    char msg[512];
    snprintf(msg, sizeof(msg), "✅ Image saved: %s", img_path);
    ui_log_append(ad, msg);

    // 6️⃣ Base64 encode
    size_t img_size = 0;
    unsigned char *img_data = readImageToBytes(img_path, &img_size);
    if (!img_data) { ui_log_append(ad, "Failed to read image."); return; }

    size_t out_len = 0;
    char *base64 = encode_base64(img_data, img_size, &out_len);
    free(img_data);
    if (!base64) { ui_log_append(ad, "Base64 encoding failed."); return; }

    // 7️⃣ Save base64 file
    char txt_path[512];
    snprintf(txt_path, sizeof(txt_path), "%sbase64_%s.txt", SAVE_FOLDER, timestamp);
    FILE *txt = fopen(txt_path, "w");
    if (txt) {
        fwrite(base64, 1, out_len, txt);
        fclose(txt);
        ui_log_append(ad, "💾 Base64 file saved.");
    }

    // 8️⃣ Create prompt_<timestamp>.json
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "method", "generate_from_image");
    cJSON *params = cJSON_CreateArray();
    cJSON_AddItemToArray(params, cJSON_CreateString(
        "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
        "<|im_start|>user\n<image> Please describe what can be seen in this image.\n"
        "Return only a short caption or summary.<|im_end|>\n"
        "<|im_start|>assistant\n"));
    cJSON_AddItemToArray(params, cJSON_CreateString(base64));
    cJSON_AddItemToObject(json, "params", params);
    cJSON_AddNumberToObject(json, "id", 42);

    char *json_str = cJSON_Print(json);
    if (json_str) {
        char json_path[512];
        snprintf(json_path, sizeof(json_path), "%sprompt_%s.json", SAVE_FOLDER, timestamp);
        FILE *jf = fopen(json_path, "w");
        if (jf) {
            fprintf(jf, "%s", json_str);
            fclose(jf);
            ui_log_append(ad, "🧠 prompt.json created.");
        }
        free(json_str);
    }
    cJSON_Delete(json);
    free(base64);
}

// ======================================================
// LIVE CAPTURE LOOP (reuses take_image_capture())
// ======================================================

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
        ui_log_append(ad, "▶️ Starting live capture...");
        ecore_timer_add(REFRESH_INTERVAL_SEC, live_loop_cb, ad);
    } else {
        ad->live_running = false;
        elm_object_text_set(obj, "Start Live Capture");
        ui_log_append(ad, "⏹ Live capture stopped.");
    }
}