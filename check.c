static const char* ACCESS_TOKEN = "9376ae6e-3776-4a2f-8c4a-08b6d9ae793f";
static const char* DEVICE_ID    = "286bfff3-ad00-4b6b-8c77-6f400dfa99a8";
static const char* API_BASE     = "https://api.smartthings.com/v1";
#define REFRESH_INTERVAL_SEC 5
#define SAVE_FOLDER "/opt/usr/home/owner/content/Pictures"
// ----------------------------

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    bool live_running;
} appdata_s;

// ---------- HTTP Helpers ----------
typedef struct { char *buf; size_t len; } mem_t;

static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = userdata;
    size_t new_len = m->len + size * nmemb;
    m->buf = realloc(m->buf, new_len + 1);
    memcpy(m->buf + m->len, ptr, size * nmemb);
    m->buf[new_len] = '\0';
    m->len = new_len;
    return size * nmemb;
}

static char* http_get(const char *url, const char *token) {
    CURL *curl = curl_easy_init();
    if (!curl) return NULL;
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    return m.buf;
}

static char* http_post(const char *url, const char *token, const char *payload) {
    CURL *curl = curl_easy_init();
    if (!curl) return NULL;
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);
    headers = curl_slist_append(headers, "Content-Type: application/json");
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    return m.buf;
}

static bool http_download_file(const char *url, const char *token, const char *save_path) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;
    FILE *fp = fopen(save_path, "wb");
    if (!fp) return false;
    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, NULL);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, fp);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    fclose(fp);
    return (res == CURLE_OK);
}
// ----------------------------------

static void ui_log_set(appdata_s *ad, const char *text) {
    elm_entry_entry_set(ad->entry_log, text);
    elm_entry_cursor_end_set(ad->entry_log);
}
static void ui_log_append(appdata_s *ad, const char *text) {
    const char *prev = elm_entry_entry_get(ad->entry_log);
    char *new_txt = malloc(strlen(prev) + strlen(text) + 8);
    sprintf(new_txt, "%s<br>%s", prev, text);
    elm_entry_entry_set(ad->entry_log, new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
}

static void take_image_capture(appdata_s *ad, const char *save_path) {
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);

    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";

    if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
        printf("Failed to send refresh command.\n");
    }

    sleep(5); // Wait for the refresh command to be processed

    // Step 2: Send the image capture command
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    free(http_post(url, ACCESS_TOKEN, payload));

    sleep(5); // Wait for SmartThings to process capture

    // Step 3: Fetch the device status to get the image URL
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    char *status = http_get(url, ACCESS_TOKEN);
    if (!status) {
        ui_log_append(ad, "Failed to fetch device status.");
        return;
    }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "No image URL found in status.");
        free(status);
        return;
    }

    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    // Step 4: Download the captured image
    ui_log_append(ad, "Downloading captured image...");
    if (http_download_file(image_url, ACCESS_TOKEN, save_path)) {
        ui_log_append(ad, "Image updated.");
        elm_image_file_set(ad->img_view, save_path, NULL);
        evas_object_show(ad->img_view);

        // Log the full path where the image is saved
        char log_message[512];
        snprintf(log_message, sizeof(log_message), "Image saved at: %s", save_path);
        ui_log_append(ad, log_message);

        // Step 5: Read the image file and encode it in Base64
        size_t image_size;
        unsigned char* image_data = readImageToBytes(save_path, &image_size);
        if (image_data) {
            size_t output_length;
            char* base64_encoded = encode_base64(image_data, image_size, &output_length);
            if (base64_encoded) {
                ui_log_append(ad, "Base64 encoded image:");
                ui_log_append(ad, base64_encoded);

                // Free the Base64-encoded string
                free(base64_encoded);
            } else {
                ui_log_append(ad, "Failed to encode image data to Base64.");
            }

            // Free the image data
            free(image_data);
        } else {
            ui_log_append(ad, "Failed to read image data.");
        }
    } else {
        ui_log_append(ad, "Failed to download image.");
    }

    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");

    if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
        printf("Failed to send refresh command.\n");
    }

    sleep(3); // Wait for the refresh command to be processed
}
