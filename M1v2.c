#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <cjson/cJSON.h>
#include <smartthings_client.h>
#include <app_common.h>
#include <dlog.h>
#include <app_control.h>
#include <efl_extension.h>
#include <stdbool.h>
#include <unistd.h>

#define LOG_TAG "STCLIENT"

// ---------- CONFIG ----------
static const char* CLIENT_ID     = "YOUR_CLIENT_ID";
static const char* CLIENT_SECRET = "YOUR_CLIENT_SECRET";
static const char* REDIRECT_URI  = "YOUR_REGISTERED_REDIRECT_URI";
static const char* SCOPES        = "r:devices:* x:devices:*";
static const char* AUTH_BASE     = "https://auth-global.api.smartthings.com/oauth/authorize";
static const char* TOKEN_URL     = "https://auth-global.api.smartthings.com/oauth/token";
static const char* API_BASE      = "https://api.smartthings.com/v1";
// ----------------------------

// ---------- APP DATA ----------
typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *btn_auth;
    Evas_Object *btn_list;
    Evas_Object *btn_capture;
    char data_path[PATH_MAX];
    char access_token[4096];
    char refresh_token[4096];
    smartthings_client_h st_handle;
} appdata_s;
// -----------------------------

// ---------- CURL helpers ----------
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
static char* http_post_form(const char *url, const char *user, const char *pass,
                            const char *postdata) {
    CURL *curl = curl_easy_init();
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    struct curl_slist *headers = NULL;
    headers = curl_slist_append(headers, "Content-Type: application/x-www-form-urlencoded");
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, postdata);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    if (user && pass) {
        char creds[512];
        snprintf(creds, sizeof(creds), "%s:%s", user, pass);
        curl_easy_setopt(curl, CURLOPT_USERPWD, creds);
        curl_easy_setopt(curl, CURLOPT_HTTPAUTH, CURLAUTH_BASIC);
    }
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    return m.buf;
}
// -----------------------------------

// ---------- SmartThings Client SDK ----------
static void client_status_cb(smartthings_client_h handle,
                             smartthings_client_status_e status, void *user_data) {
    dlog_print(DLOG_INFO, LOG_TAG, "Client status: %d", status);
}
static void client_connection_cb(smartthings_client_h handle,
                                 bool connected, void *user_data) {
    dlog_print(DLOG_INFO, LOG_TAG, "Connected: %d", connected);
}
static void start_client(appdata_s *ad) {
    int r = smartthings_client_initialize(&ad->st_handle, client_status_cb, ad);
    if (r == SMARTTHINGS_CLIENT_ERROR_NONE) {
        smartthings_client_set_connection_status_cb(ad->st_handle, client_connection_cb, ad);
        smartthings_client_start(ad->st_handle);
        dlog_print(DLOG_INFO, LOG_TAG, "SmartThings Client started");
    } else {
        dlog_print(DLOG_ERROR, LOG_TAG, "SmartThings Client init failed: %d", r);
    }
}
static void stop_client(appdata_s *ad) {
    if (ad->st_handle) {
        smartthings_client_stop(ad->st_handle);
        smartthings_client_deinitialize(ad->st_handle);
        ad->st_handle = NULL;
    }
}
// --------------------------------------------

// ---------- OAuth + REST ----------
static void authorize_clicked(void *data, Evas_Object *obj, void *event_info) {
    char url[1024];
    snprintf(url, sizeof(url),
             "%s?response_type=code&client_id=%s&redirect_uri=%s&scope=%s",
             AUTH_BASE, CLIENT_ID, REDIRECT_URI, SCOPES);

    dlog_print(DLOG_INFO, LOG_TAG, "Launching browser for OAuth: %s", url);

    app_control_h app_control;
    if (app_control_create(&app_control) == APP_CONTROL_ERROR_NONE) {
        app_control_set_operation(app_control, APP_CONTROL_OPERATION_VIEW);
        app_control_set_uri(app_control, url);
        app_control_send_launch_request(app_control, NULL, NULL);
        app_control_destroy(app_control);
    } else {
        dlog_print(DLOG_ERROR, LOG_TAG, "Failed to create app_control for browser launch");
    }
}

static void list_devices_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (strlen(ad->access_token) == 0) {
        dlog_print(DLOG_INFO, LOG_TAG, "No access token yet, authorize first");
        return;
    }
    char url[512];
    snprintf(url, sizeof(url), "%s/devices", API_BASE);
    CURL *curl = curl_easy_init();
    struct curl_slist *h = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", ad->access_token);
    h = curl_slist_append(h, auth);
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, h);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(h);
    dlog_print(DLOG_INFO, LOG_TAG, "Devices response: %s", m.buf);
    free(m.buf);
}

static void capture_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (strlen(ad->access_token) == 0) {
        dlog_print(DLOG_INFO, LOG_TAG, "Authorize first");
        return;
    }
    // Replace with your own deviceId for now
    const char *deviceId = "YOUR_DEVICE_ID";
    char url[1024];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, deviceId);
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    struct curl_slist *h = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", ad->access_token);
    h = curl_slist_append(h, auth);
    CURL *curl = curl_easy_init();
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, h);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(h);
    dlog_print(DLOG_INFO, LOG_TAG, "Sent imageCapture.take");
}
// --------------------------------------------

// ---------- GUI ----------
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("STTV", "SmartThings Capture");
    elm_win_autodel_set(ad->win, EINA_TRUE);

    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    ad->box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);

    ad->btn_auth = elm_button_add(ad->box);
    elm_object_text_set(ad->btn_auth, "Authorize");
    evas_object_smart_callback_add(ad->btn_auth, "clicked", authorize_clicked, ad);
    elm_box_pack_end(ad->box, ad->btn_auth);
    evas_object_show(ad->btn_auth);

    ad->btn_list = elm_button_add(ad->box);
    elm_object_text_set(ad->btn_list, "List Devices");
    evas_object_smart_callback_add(ad->btn_list, "clicked", list_devices_clicked, ad);
    elm_box_pack_end(ad->box, ad->btn_list);
    evas_object_show(ad->btn_list);

    ad->btn_capture = elm_button_add(ad->box);
    elm_object_text_set(ad->btn_capture, "Capture");
    evas_object_smart_callback_add(ad->btn_capture, "clicked", capture_clicked, ad);
    elm_box_pack_end(ad->box, ad->btn_capture);
    evas_object_show(ad->btn_capture);

    evas_object_show(ad->win);
}
// --------------------------------------------

// ---------- Standard callbacks ----------
static void win_delete_request_cb(void *data, Evas_Object *obj, void *event_info) {
    ui_app_exit();
}
static void win_back_cb(void *data, Evas_Object *obj, void *event_info) {
    ui_app_exit();
}
static bool app_create(void *data) {
    appdata_s *ad = data;
    app_get_data_path(ad->data_path, sizeof(ad->data_path));
    curl_global_init(CURL_GLOBAL_DEFAULT);
    start_client(ad);
    create_base_gui(ad);
    return true;
}
static void app_control(app_control_h app_control, void *data) {}
static void app_pause(void *data) {}
static void app_resume(void *data) {}
static void app_terminate(void *data) {
    appdata_s *ad = data;
    stop_client(ad);
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