#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <app_control.h>
#include <dlog.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>

#define LOG_TAG "STREST_IMG"

// ---------- CONFIG ----------
static const char* CLIENT_ID     = "YOUR_CLIENT_ID";
static const char* CLIENT_SECRET = "YOUR_CLIENT_SECRET";
static const char* REDIRECT_URI  = "YOUR_REGISTERED_REDIRECT_URI";
static const char* SCOPES        = "r:devices:* x:devices:*";
static const char* AUTH_BASE     = "https://auth-global.api.smartthings.com/oauth/authorize";
static const char* API_BASE      = "https://api.smartthings.com/v1";
// ----------------------------

// ---------- APP DATA ----------
typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    char access_token[4096];
} appdata_s;
// -----------------------------

// ---------- CURL helper ----------
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
// -----------------------------------

// ---------- UI log helper ----------
static void ui_log_append(appdata_s *ad, const char *text) {
    if (!ad->entry_log) return;
    const char *prev = elm_entry_entry_get(ad->entry_log);
    char *new_txt = malloc(strlen(prev) + strlen(text) + 8);
    sprintf(new_txt, "%s<br>%s", prev, text);
    elm_entry_entry_set(ad->entry_log, new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
}
// -----------------------------------

// ---------- BUTTON ACTIONS ----------
static void authorize_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    char url[1024];
    snprintf(url, sizeof(url),
             "%s?response_type=code&client_id=%s&redirect_uri=%s&scope=%s",
             AUTH_BASE, CLIENT_ID, REDIRECT_URI, SCOPES);

    ui_log_append(ad, "Opening SmartThings login page...");
    app_control_h app_control;
    if (app_control_create(&app_control) == APP_CONTROL_ERROR_NONE) {
        app_control_set_operation(app_control, APP_CONTROL_OPERATION_VIEW);
        app_control_set_uri(app_control, url);
        app_control_send_launch_request(app_control, NULL, NULL);
        app_control_destroy(app_control);
    } else {
        ui_log_append(ad, "Error launching browser.");
    }
}

static void list_devices_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (strlen(ad->access_token) == 0) {
        ui_log_append(ad, "No access token. Please authorize first.");
        return;
    }
    char url[512];
    snprintf(url, sizeof(url), "%s/devices", API_BASE);
    char *resp = http_get(url, ad->access_token);
    if (resp) {
        ui_log_append(ad, "Devices JSON:");
        ui_log_append(ad, resp);
        free(resp);
    }
}

static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (strlen(ad->access_token) == 0) {
        ui_log_append(ad, "Authorize first.");
        return;
    }
    const char *deviceId = "YOUR_DEVICE_ID";
    char url[1024];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, deviceId);
    char *resp = http_get(url, ad->access_token);
    if (resp) {
        ui_log_append(ad, "Device Capabilities:");
        ui_log_append(ad, resp);
        free(resp);
    }
}

static void capture_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (strlen(ad->access_token) == 0) {
        ui_log_append(ad, "Authorize first.");
        return;
    }

    // clear previous image
    evas_object_hide(ad->img_view);

    const char *deviceId = "YOUR_DEVICE_ID";
    char url[1024];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, deviceId);
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";

    ui_log_append(ad, "Requesting image capture...");
    free(http_post(url, ad->access_token, payload));

    // wait briefly before checking status
    sleep(3);
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, deviceId);
    char *status = http_get(url, ad->access_token);
    if (!status) {
        ui_log_append(ad, "Failed to get status after capture.");
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

    char save_path[256] = "/opt/usr/home/owner/media/last_capture.jpg";
    ui_log_append(ad, "Downloading image...");
    if (http_download_file(image_url, ad->access_token, save_path)) {
        ui_log_append(ad, "Image saved. Displaying...");
        elm_image_file_set(ad->img_view, save_path, NULL);

        // auto-scale image to fit window width
        int win_w = 0, win_h = 0;
        evas_object_geometry_get(ad->win, NULL, NULL, &win_w, &win_h);
        elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
        elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
        evas_object_size_hint_min_set(ad->img_view, win_w, win_w * 0.6); // maintain aspect ratio
        evas_object_show(ad->img_view);
    } else {
        ui_log_append(ad, "Failed to download image.");
    }
}
// -----------------------------------

// ---------- GUI ----------
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("STREST_IMG", "SmartThings REST Capture");
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
    Evas_Object *btn;
    btn = elm_button_add(ad->box);
    elm_object_text_set(btn, "Authorize (Browser)");
    evas_object_smart_callback_add(btn, "clicked", authorize_clicked, ad);
    elm_box_pack_end(ad->box, btn);
    evas_object_show(btn);

    btn = elm_button_add(ad->box);
    elm_object_text_set(btn, "List Devices");
    evas_object_smart_callback_add(btn, "clicked", list_devices_clicked, ad);
    elm_box_pack_end(ad->box, btn);
    evas_object_show(btn);

    btn = elm_button_add(ad->box);
    elm_object_text_set(btn, "Show Capabilities");
    evas_object_smart_callback_add(btn, "clicked", show_caps_clicked, ad);
    elm_box_pack_end(ad->box, btn);
    evas_object_show(btn);

    btn = elm_button_add(ad->box);
    elm_object_text_set(btn, "Take Capture");
    evas_object_smart_callback_add(btn, "clicked", capture_clicked, ad);
    elm_box_pack_end(ad->box, btn);
    evas_object_show(btn);

    // Scrollable log area
    Evas_Object *scroller = elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_scroller_bounce_set(scroller, EINA_FALSE, EINA_TRUE);
    elm_box_pack_end(ad->box, scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Log output will appear here...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    // Image preview area (auto-resizing)
    ad->img_view = elm_image_add(ad->box);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, 0.5);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    elm_box_pack_end(ad->box, ad->img_view);
    evas_object_hide(ad->img_view);

    evas_object_show(ad->win);
}
// --------------------------------------------

// ---------- App Lifecycle ----------
static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    create_base_gui(ad);
    return true;
}
static void app_control(app_control_h app_control, void *data) {}
static void app_pause(void *data) {}
static void app_resume(void *data) {}
static void app_terminate(void *data) {
    curl_global_cleanup();
}
// --------------------------------------------

// ---------- MAIN ----------
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