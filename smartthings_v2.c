#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <app_common.h>

#define LOG_TAG "ST_LIVE_REFRESH"

// ---------- CONFIG ----------
static const char* CLIENT_ID     = "YOUR_CLIENT_ID";     // <--- paste yours
static const char* CLIENT_SECRET = "YOUR_CLIENT_SECRET"; // <--- paste yours
static char REFRESH_TOKEN[1024]  = "YOUR_REFRESH_TOKEN"; // <--- paste initial refresh token
static char ACCESS_TOKEN[4096]   = "";                   // will be auto-refreshed
static const char* DEVICE_ID     = "286bfff3-ad00-4b6b-8c77-6f400dfa99a8";
static const char* API_BASE      = "https://api.smartthings.com/v1";
#define REFRESH_INTERVAL_SEC 5
#define SAVE_FOLDER "/opt/usr/home/owner/media/Images"
// --------------------------------

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

static char* http_request(const char *url, const char *token,
                          const char *payload, long *out_code) {
    CURL *curl = curl_easy_init();
    if (!curl) return NULL;
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    struct curl_slist *headers = NULL;
    char auth[512];
    if (token && strlen(token) > 0) {
        snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
        headers = curl_slist_append(headers, auth);
    }
    if (payload)
        headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    if (payload)
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    CURLcode res = curl_easy_perform(curl);
    if (out_code)
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, out_code);
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

// ---------- UI Log ----------
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
// ----------------------------------

// ---------- TOKEN REFRESH ----------
static bool refresh_token(appdata_s *ad) {
    ui_log_append(ad, "Refreshing access token...");
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    mem_t m = { .buf = calloc(1,1), .len = 0 };
    char post_fields[2048];
    snprintf(post_fields, sizeof(post_fields),
        "grant_type=refresh_token&client_id=%s&client_secret=%s&refresh_token=%s",
        CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN);

    curl_easy_setopt(curl, CURLOPT_URL, "https://auth-global.api.smartthings.com/oauth/token");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_fields);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || !m.buf) {
        ui_log_append(ad, "Token refresh failed (network).");
        free(m.buf);
        return false;
    }

    char *acc = strstr(m.buf, "\"access_token\"");
    char *ref = strstr(m.buf, "\"refresh_token\"");
    if (acc) sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", ACCESS_TOKEN);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%1023[^\"]\"", REFRESH_TOKEN);

    if (strlen(ACCESS_TOKEN) == 0) {
        ui_log_append(ad, "Failed to parse refreshed token.");
        free(m.buf);
        return false;
    }

    // Save updated tokens
    const char *path = app_get_data_path();
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "w");
    if (fp) {
        fprintf(fp, "%s\n%s\n", ACCESS_TOKEN, REFRESH_TOKEN);
        fclose(fp);
    }
    free(m.buf);
    ui_log_append(ad, "Access token refreshed successfully.");
    return true;
}
// ----------------------------------

// ---------- CAPTURE LOGIC ----------
static void ensure_save_folder(void) {
    struct stat st = {0};
    if (stat(SAVE_FOLDER, &st) == -1) mkdir(SAVE_FOLDER, 0755);
}

static bool take_image_capture(appdata_s *ad, const char *save_path);

static bool perform_api_call(appdata_s *ad, const char *url,
                             const char *payload, char **out_response) {
    long code = 0;
    char *resp = http_request(url, ACCESS_TOKEN, payload, &code);
    if (code == 401) { // token expired
        ui_log_append(ad, "Token expired. Refreshing...");
        if (refresh_token(ad)) {
            free(resp);
            resp = http_request(url, ACCESS_TOKEN, payload, &code);
        }
    }
    if (out_response) *out_response = resp;
    return (resp && code >= 200 && code < 300);
}

static bool take_image_capture(appdata_s *ad, const char *save_path) {
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";

    char *resp = NULL;
    if (!perform_api_call(ad, url, payload, &resp)) {
        ui_log_append(ad, "Failed to send capture command.");
        free(resp);
        return false;
    }
    free(resp);

    sleep(3);

    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    char *status = NULL;
    if (!perform_api_call(ad, url, NULL, &status)) {
        ui_log_append(ad, "Failed to fetch device status.");
        free(status);
        return false;
    }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "No image URL found.");
        free(status);
        return false;
    }
    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    if (http_download_file(image_url, ACCESS_TOKEN, save_path)) {
        ui_log_append(ad, "Image updated.");
        elm_image_file_set(ad->img_view, save_path, NULL);
        evas_object_show(ad->img_view);
        return true;
    }
    ui_log_append(ad, "Image download failed.");
    return false;
}
// ----------------------------------

// ---------- BUTTONS ----------
static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);
    ui_log_set(ad, "Fetching capabilities...");
    char *resp = NULL;
    if (perform_api_call(ad, url, NULL, &resp)) {
        ui_log_append(ad, resp);
    } else {
        ui_log_append(ad, "Failed to get capabilities.");
    }
    free(resp);
}

static Eina_Bool live_loop_cb(void *data) {
    appdata_s *ad = data;
    if (!ad->live_running) return ECORE_CALLBACK_CANCEL;

    ensure_save_folder();
    char save_path[512];
    snprintf(save_path, sizeof(save_path), "%s/captured_image.jpg", SAVE_FOLDER);
    take_image_capture(ad, save_path);

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
// ----------------------------------

// ---------- GUI ----------
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("ST_LIVE", "SmartThings Live Capture");
    elm_win_autodel_set(ad->win, EINA_TRUE);

    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    ad->box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);

    // Buttons
    Evas_Object *btn_caps = elm_button_add(ad->box);
    elm_object_text_set(btn_caps, "Show Capabilities");
    evas_object_smart_callback_add(btn_caps, "clicked", show_caps_clicked, ad);
    elm_box_pack_end(ad->box, btn_caps);
    evas_object_show(btn_caps);

    Evas_Object *btn_live = elm_button_add(ad->box);
    elm_object_text_set(btn_live, "Start Live Capture");
    evas_object_smart_callback_add(btn_live, "clicked", live_clicked, ad);
    elm_box_pack_end(ad->box, btn_live);
    evas_object_show(btn_live);

    // Scrollable log (half height)
    Evas_Object *scroller = elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, 0.5);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Press 'Show Capabilities' or 'Start Live Capture'...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    // Image view (bottom half)
    ad->img_view = elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, 0.5);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, ad->img_view);
    evas_object_hide(ad->img_view);

    evas_object_show(ad->win);
}
// ----------------------------------

// ---------- Lifecycle ----------
static bool app_create(void *data) {
    appdata_s *ad = data;
    ad->live_running = false;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_save_folder();
    create_base_gui(ad);
    return true;
}
static void app_terminate(void *data) { curl_global_cleanup(); }
static void app_control(app_control_h app_control, void *data) {}
static void app_pause(void *data) {}
static void app_resume(void *data) {}
// ----------------------------------

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