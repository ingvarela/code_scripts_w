#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <stdbool.h>
#include <string.h>

#define LOG_TAG "ST_DEVICE_VIEWER"

// Paste your personal access token here
static const char* ACCESS_TOKEN = "YOUR_ACCESS_TOKEN";  // <-- Replace with your token
static const char* API_BASE     = "https://api.smartthings.com/v1";

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_log;
    char first_device_id[256];  // to store first found deviceId
} appdata_s;

// ---------- HTTP helper ----------
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
// ---------------------------------

// ---------- UI log helper ----------
static void ui_log_set(appdata_s *ad, const char *text) {
    if (!ad->entry_log) return;
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

// ---------- Actions ----------
static void list_devices_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    ui_log_set(ad, "Fetching devices list...");
    char url[512];
    snprintf(url, sizeof(url), "%s/devices", API_BASE);
    char *resp = http_get(url, ACCESS_TOKEN);
    if (!resp) {
        ui_log_set(ad, "Request failed. Check network or token.");
        return;
    }

    ui_log_set(ad, "Devices:\n");
    char *ptr = resp;
    int count = 0;

    // find each deviceId and name using naive string scanning
    while ((ptr = strstr(ptr, "\"deviceId\"")) != NULL) {
        char id[128] = {0};
        char name[128] = {0};
        sscanf(ptr, "\"deviceId\"%*[^:]:\"%127[^\"]\"", id);
        char *nameptr = strstr(ptr, "\"name\"");
        if (nameptr) sscanf(nameptr, "\"name\"%*[^:]:\"%127[^\"]\"", name);
        char line[256];
        snprintf(line, sizeof(line), "• %s — %s", name[0] ? name : "(unnamed)", id);
        ui_log_append(ad, line);
        if (count == 0) snprintf(ad->first_device_id, sizeof(ad->first_device_id), "%s", id);
        count++;
        ptr += strlen("\"deviceId\"");
    }

    if (count == 0)
        ui_log_append(ad, "No devices found.");
    else
        ui_log_append(ad, "<br><b>Tip:</b> Press 'Show Capabilities' to view the first device.");

    free(resp);
}

static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (strlen(ad->first_device_id) == 0) {
        ui_log_set(ad, "No device selected. Please list devices first.");
        return;
    }

    ui_log_set(ad, "Fetching capabilities for first device...");
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, ad->first_device_id);
    char *resp = http_get(url, ACCESS_TOKEN);
    if (resp) {
        ui_log_append(ad, "<br><b>Device Capabilities:</b>");
        ui_log_append(ad, resp);
        free(resp);
    } else {
        ui_log_append(ad, "Failed to fetch capabilities.");
    }
}
// ----------------------------------

// ---------- GUI ----------
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("ST_DEV", "SmartThings Devices Viewer");
    elm_win_autodel_set(ad->win, EINA_TRUE);

    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    ad->box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);

    // Button: List Devices
    Evas_Object *btn_list = elm_button_add(ad->box);
    elm_object_text_set(btn_list, "List Devices");
    evas_object_smart_callback_add(btn_list, "clicked", list_devices_clicked, ad);
    elm_box_pack_end(ad->box, btn_list);
    evas_object_show(btn_list);

    // Button: Show Capabilities
    Evas_Object *btn_caps = elm_button_add(ad->box);
    elm_object_text_set(btn_caps, "Show Capabilities");
    evas_object_smart_callback_add(btn_caps, "clicked", show_caps_clicked, ad);
    elm_box_pack_end(ad->box, btn_caps);
    evas_object_show(btn_caps);

    // Scrollable log/output
    Evas_Object *scroller = elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Press 'List Devices' to start...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    evas_object_show(ad->win);
}
// ----------------------------------

// ---------- Lifecycle ----------
static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    create_base_gui(ad);
    return true;
}
static void app_terminate(void *data) {
    curl_global_cleanup();
}
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