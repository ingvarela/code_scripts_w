#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <app_common.h>
#include <errno.h>

#define LOG_TAG "ST_LIVE_REFRESH"

// ---------- CONFIG ----------
static const char* DEVICE_ID  = "286bfff3-ad00-4b6b-8c77-6f400dfa99a8";
static const char* API_BASE   = "https://api.smartthings.com/v1";
#define REFRESH_INTERVAL_SEC 5
#define SAVE_FOLDER "/opt/usr/home/owner/media/Images"
// --------------------------------

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    Ecore_Timer *live_timer;
    bool live_running;
} appdata_s;

// ---------- Safe UI Log ----------
static void ui_log_append(appdata_s *ad, const char *text) {
    if (!ad || !text) return;
    if (!ad->entry_log) { // UI not ready yet: print to dlog only
        dlog_print(DLOG_INFO, LOG_TAG, "%s", text);
        return;
    }
    const char *prev = elm_entry_entry_get(ad->entry_log);
    if (!prev) prev = "";
    size_t new_len = strlen(prev) + strlen(text) + 8;
    char *buf = (char*)malloc(new_len);
    if (!buf) { dlog_print(DLOG_ERROR, LOG_TAG, "malloc failed in ui_log_append"); return; }
    snprintf(buf, new_len, "%s<br>%s", prev, text);
    elm_entry_entry_set(ad->entry_log, buf);
    free(buf);
    elm_entry_cursor_end_set(ad->entry_log);
}
static void ui_log_set(appdata_s *ad, const char *text) {
    if (!ad || !text || !ad->entry_log) { if (text) dlog_print(DLOG_INFO, LOG_TAG, "%s", text); return; }
    elm_entry_entry_set(ad->entry_log, text);
    elm_entry_cursor_end_set(ad->entry_log);
}

// ---------- HTTP Helpers ----------
typedef struct { char *buf; size_t len; } mem_t;

static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = (mem_t*)userdata;
    if (!m) return 0;
    size_t chunk = size * nmemb;
    size_t new_len = m->len + chunk;
    char *newp = (char*)realloc(m->buf, new_len + 1);
    if (!newp) {
        dlog_print(DLOG_ERROR, LOG_TAG, "realloc failed in write_cb");
        return 0; // stop transfer
    }
    m->buf = newp;
    memcpy(m->buf + m->len, ptr, chunk);
    m->buf[new_len] = '\0';
    m->len = new_len;
    return chunk;
}

static char* http_request(const char *url, const char *token,
                          const char *payload, long *out_code) {
    if (!url) return NULL;
    CURL *curl = curl_easy_init();
    if (!curl) { dlog_print(DLOG_ERROR, LOG_TAG, "curl init failed"); return NULL; }

    mem_t m = { .buf = NULL, .len = 0 };
    struct curl_slist *headers = NULL;
    if (token && *token) {
        char auth[512]; snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
        headers = curl_slist_append(headers, auth);
    }
    if (payload) headers = curl_slist_append(headers, "Content-Type: application/json");

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    if (payload) curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    // Uncomment next line only if you hit CA issues during dev:
    // curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);

    CURLcode res = curl_easy_perform(curl);
    long code = 0;
    if (res == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &code);
    if (out_code) *out_code = code;

    curl_easy_cleanup(curl);
    if (headers) curl_slist_free_all(headers);

    if (res != CURLE_OK) {
        dlog_print(DLOG_ERROR, LOG_TAG, "curl perform error: %s", curl_easy_strerror(res));
        if (m.buf) free(m.buf);
        return NULL;
    }
    if (!m.buf) {
        // Ensure caller always gets a valid C-string
        m.buf = (char*)calloc(1,1);
    }
    return m.buf;
}

static bool http_download_file(const char *url, const char *token, const char *save_path) {
    if (!url || !save_path) return false;
    CURL *curl = curl_easy_init();
    if (!curl) { dlog_print(DLOG_ERROR, LOG_TAG, "curl init failed (download)"); return false; }

    FILE *fp = fopen(save_path, "wb");
    if (!fp) {
        dlog_print(DLOG_ERROR, LOG_TAG, "fopen failed: %s", strerror(errno));
        curl_easy_cleanup(curl);
        return false;
    }

    struct curl_slist *headers = NULL;
    if (token && *token) {
        char auth[512]; snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
        headers = curl_slist_append(headers, auth);
    }
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, fp);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, NULL);
    curl_easy_setopt(curl, CURLOPT_FAILONERROR, 1L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);

    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    if (headers) curl_slist_free_all(headers);
    fclose(fp);

    if (res != CURLE_OK) {
        dlog_print(DLOG_ERROR, LOG_TAG, "download error: %s", curl_easy_strerror(res));
        unlink(save_path); // remove partial file
        return false;
    }
    return true;
}

// ---------- TOKEN MANAGER ----------
typedef struct {
    char client_id[256];
    char client_secret[256];
    char refresh_token[1024];
    char access_token[4096];
    char auth_code[64];
    bool loaded;
} TokenData;

static TokenData TOKENS;

static void token_save(TokenData *t) {
    if (!t) return;
    const char *path = app_get_data_path();
    if (!path) return;
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "w");
    if (!fp) { dlog_print(DLOG_ERROR, LOG_TAG, "token_save fopen failed"); return; }
    fprintf(fp, "client_id=%s\nclient_secret=%s\nrefresh_token=%s\naccess_token=%s\nauth_code=%s\n",
            t->client_id, t->client_secret, t->refresh_token, t->access_token, t->auth_code);
    fclose(fp);
}

// robust line parser: key=value (trims newline, tolerates spaces)
static void parse_kv_line(const char *line, char *k, size_t ks, char *v, size_t vs) {
    if (!line || !k || !v) return;
    const char *eq = strchr(line, '=');
    if (!eq) { *k = *v = '\0'; return; }
    size_t klen = (size_t)(eq - line);
    if (klen >= ks) klen = ks - 1;
    strncpy(k, line, klen); k[klen] = '\0';
    // skip '=' and possible spaces
    const char *val = eq + 1;
    while (*val == ' ' || *val == '\t') val++;
    // copy until end or newline
    size_t vlen = strcspn(val, "\r\n");
    if (vlen >= vs) vlen = vs - 1;
    strncpy(v, val, vlen); v[vlen] = '\0';
}

static void token_load(TokenData *t) {
    if (!t || t->loaded) return;
    memset(t, 0, sizeof(TokenData));
    const char *path = app_get_data_path();
    if (!path) { dlog_print(DLOG_ERROR, LOG_TAG, "app_get_data_path NULL"); return; }
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "r");
    if (!fp) { dlog_print(DLOG_INFO, LOG_TAG, "tokens.txt not found yet"); t->loaded = true; return; }
    char line[8192], key[256], val[4096];
    while (fgets(line, sizeof(line), fp)) {
        parse_kv_line(line, key, sizeof(key), val, sizeof(val));
        if (strcmp(key, "client_id") == 0) strncpy(t->client_id, val, sizeof(t->client_id)-1);
        else if (strcmp(key, "client_secret") == 0) strncpy(t->client_secret, val, sizeof(t->client_secret)-1);
        else if (strcmp(key, "refresh_token") == 0) strncpy(t->refresh_token, val, sizeof(t->refresh_token)-1);
        else if (strcmp(key, "access_token") == 0) strncpy(t->access_token, val, sizeof(t->access_token)-1);
        else if (strcmp(key, "auth_code") == 0) strncpy(t->auth_code, val, sizeof(t->auth_code)-1);
    }
    fclose(fp);
    t->loaded = true;
}

static bool token_request(TokenData *t, const char *body) {
    if (!t || !body) return false;
    CURL *curl = curl_easy_init();
    if (!curl) { dlog_print(DLOG_ERROR, LOG_TAG, "curl init failed (token_request)"); return false; }
    mem_t m = { .buf = NULL, .len = 0 };
    curl_easy_setopt(curl, CURLOPT_URL, "https://auth-global.api.smartthings.com/oauth/token");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    if (res != CURLE_OK) {
        dlog_print(DLOG_ERROR, LOG_TAG, "token_request error: %s", curl_easy_strerror(res));
        if (m.buf) free(m.buf);
        return false;
    }
    if (!m.buf) { dlog_print(DLOG_ERROR, LOG_TAG, "token_request empty body"); return false; }

    // naive parse (kept to avoid extra deps)
    char *acc = strstr(m.buf, "\"access_token\"");
    char *ref = strstr(m.buf, "\"refresh_token\"");
    if (acc) sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", t->access_token);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%1023[^\"]\"", t->refresh_token);
    free(m.buf);

    if (!*t->access_token) { dlog_print(DLOG_ERROR, LOG_TAG, "token_request parse failed"); return false; }
    token_save(t);
    return true;
}

static bool token_refresh(TokenData *t) {
    if (!t || !*t->client_id || !*t->client_secret || !*t->refresh_token) {
        dlog_print(DLOG_ERROR, LOG_TAG, "token_refresh missing fields");
        return false;
    }
    char body[2048];
    snprintf(body, sizeof(body),
             "grant_type=refresh_token&client_id=%s&client_secret=%s&refresh_token=%s",
             t->client_id, t->client_secret, t->refresh_token);
    return token_request(t, body);
}

static bool token_exchange_code(TokenData *t, const char *redirect_uri) {
    if (!t || !*t->client_id || !*t->client_secret || !*t->auth_code || !redirect_uri) {
        dlog_print(DLOG_ERROR, LOG_TAG, "token_exchange_code missing fields");
        return false;
    }
    char body[2048];
    snprintf(body, sizeof(body),
             "grant_type=authorization_code&client_id=%s&client_secret=%s&code=%s&redirect_uri=%s",
             t->client_id, t->client_secret, t->auth_code, redirect_uri);
    return token_request(t, body);
}

static const char* get_access_token(appdata_s *ad) {
    token_load(&TOKENS);
    if (!*TOKENS.access_token) {
        ui_log_append(ad, "No access token found, trying authorization code...");
        if (token_exchange_code(&TOKENS, "https://httpbin.org/get")) {
            ui_log_append(ad, "Access token obtained from authorization code.");
        } else {
            ui_log_append(ad, "Authorization code exchange failed. Check tokens.txt.");
        }
    }
    return TOKENS.access_token;
}

// ---------- PATH SETUP ----------
static void ensure_app_folders(appdata_s *ad) {
    struct stat st;
    memset(&st, 0, sizeof(st));

    // 1) Ensure app data folder exists (for tokens.txt)
    const char *data_path = app_get_data_path();
    if (data_path && stat(data_path, &st) == -1) {
        if (mkdir(data_path, 0755) == 0) {
            dlog_print(DLOG_INFO, LOG_TAG, "Created data folder: %s", data_path);
            ui_log_append(ad, "Created data folder successfully.");
        } else {
            dlog_print(DLOG_ERROR, LOG_TAG, "Failed to create data folder: %s", data_path);
            ui_log_append(ad, "⚠️ Failed to create data folder.");
        }
    } else {
        ui_log_append(ad, "Data folder ready.");
    }

    // 2) Ensure image save folder exists
    memset(&st, 0, sizeof(st));
    if (stat(SAVE_FOLDER, &st) == -1) {
        if (mkdir(SAVE_FOLDER, 0755) == 0) {
            dlog_print(DLOG_INFO, LOG_TAG, "Created save folder: %s", SAVE_FOLDER);
            ui_log_append(ad, "Created image save folder successfully.");
        } else {
            dlog_print(DLOG_ERROR, LOG_TAG, "Failed to create save folder: %s", SAVE_FOLDER);
            ui_log_append(ad, "⚠️ Failed to create image save folder.");
        }
    } else {
        ui_log_append(ad, "Image save folder ready.");
    }
}

// ---------- CAPTURE LOGIC ----------
static bool perform_api_call(appdata_s *ad, const char *url,
                             const char *payload, char **out_response) {
    if (out_response) *out_response = NULL;
    if (!url) { ui_log_append(ad, "perform_api_call: URL is null"); return false; }
    if (!DEVICE_ID || !*DEVICE_ID) { ui_log_append(ad, "Missing DEVICE_ID"); return false; }

    long code = 0;
    const char *token = get_access_token(ad);
    if (!token || !*token) { ui_log_append(ad, "No access token available"); return false; }

    char *resp = http_request(url, TOKENS.access_token, payload, &code);
    if (code == 401) {
        ui_log_append(ad, "Token expired. Refreshing...");
        if (token_refresh(&TOKENS)) {
            if (resp) free(resp);
            resp = http_request(url, TOKENS.access_token, payload, &code);
        } else {
            ui_log_append(ad, "Token refresh failed.");
        }
    }
    if (out_response) *out_response = resp;
    return (resp && code >= 200 && code < 300);
}

static bool take_image_capture(appdata_s *ad, const char *save_path) {
    if (!ad || !save_path) return false;

    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";

    char *resp = NULL;
    if (!perform_api_call(ad, url, payload, &resp)) {
        ui_log_append(ad, "Failed to send capture command.");
        if (resp) free(resp);
        return false;
    }
    if (resp) free(resp);

    // wait a bit for device to update status
    sleep(3);

    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    char *status = NULL;
    if (!perform_api_call(ad, url, NULL, &status)) {
        ui_log_append(ad, "Failed to fetch device status.");
        if (status) free(status);
        return false;
    }
    if (!status) { ui_log_append(ad, "Empty status body."); return false; }

    // naive extraction of first https URL
    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "No image URL found in status.");
        free(status);
        return false;
    }
    char image_url[1024] = {0};
    sscanf(found, "%1023[^\"]", image_url);
    free(status);

    if (!*image_url) {
        ui_log_append(ad, "Parsed image URL empty.");
        return false;
    }

    if (http_download_file(image_url, TOKENS.access_token, save_path)) {
        ui_log_append(ad, "Image saved. Updating UI...");
        if (ad->img_view) {
            elm_image_file_set(ad->img_view, save_path, NULL);
            evas_object_show(ad->img_view);
        }
        return true;
    }
    ui_log_append(ad, "Image download failed.");
    return false;
}

// ---------- BUTTONS ----------
static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    (void)obj; (void)event_info;
    appdata_s *ad = (appdata_s*)data;
    if (!ad) return;
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);
    ui_log_set(ad, "Fetching capabilities...");
    char *resp = NULL;
    if (perform_api_call(ad, url, NULL, &resp)) {
        ui_log_append(ad, resp ? resp : "(empty response)");
    } else {
        ui_log_append(ad, "Failed to get capabilities.");
    }
    if (resp) free(resp);
}

static Eina_Bool live_loop_cb(void *data) {
    appdata_s *ad = (appdata_s*)data;
    if (!ad || !ad->live_running) return ECORE_CALLBACK_CANCEL;

    char save_path[512];
    snprintf(save_path, sizeof(save_path), "%s/captured_image.jpg", SAVE_FOLDER);
    take_image_capture(ad, save_path);

    return ad->live_running ? ECORE_CALLBACK_RENEW : ECORE_CALLBACK_CANCEL;
}

static void live_clicked(void *data, Evas_Object *obj, void *event_info) {
    (void)obj; (void)event_info;
    appdata_s *ad = (appdata_s*)data;
    if (!ad) return;

    if (!ad->live_running) {
        ad->live_running = true;
        if (obj) elm_object_text_set(obj, "Stop Live Capture");
        ui_log_append(ad, "Starting live capture...");
        // store timer handle so we can cancel safely
        ad->live_timer = ecore_timer_add(REFRESH_INTERVAL_SEC, live_loop_cb, ad);
        if (!ad->live_timer) ui_log_append(ad, "⚠️ Failed to start timer.");
    } else {
        ad->live_running = false;
        if (obj) elm_object_text_set(obj, "Start Live Capture");
        if (ad->live_timer) { ecore_timer_del(ad->live_timer); ad->live_timer = NULL; }
        ui_log_append(ad, "Live capture stopped.");
    }
}

// ---------- GUI ----------
static void create_base_gui(appdata_s *ad) {
    if (!ad) return;

    ad->win = elm_win_util_standard_add("ST_LIVE", "SmartThings Live Capture");
    if (!ad->win) { dlog_print(DLOG_ERROR, LOG_TAG, "Failed to create window"); return; }
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

    // Scrollable log (top half)
    Evas_Object *scroller = elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, 0.5);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Initializing...");
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

// ---------- Lifecycle ----------
static bool app_create(void *data) {
    appdata_s *ad = (appdata_s*)data;
    if (!ad) return false;
    memset(ad, 0, sizeof(*ad));
    ad->live_running = false;
    ad->live_timer = NULL;

    curl_global_init(CURL_GLOBAL_DEFAULT);

    // Build UI first so ui_log_* can safely write on-screen
    create_base_gui(ad);

    // Ensure folders and then tokens
    ensure_app_folders(ad);
    const char *token = get_access_token(ad);
    if (token && *token) ui_log_append(ad, "Token system ready.");
    else ui_log_append(ad, "Token unavailable. Check tokens.txt.");

    return true;
}

static void app_terminate(void *data) {
    appdata_s *ad = (appdata_s*)data;
    if (ad && ad->live_timer) { ecore_timer_del(ad->live_timer); ad->live_timer = NULL; }
    curl_global_cleanup();
}

static void app_control(app_control_h app_control, void *data) { (void)app_control; (void)data; }
static void app_pause(void *data) { (void)data; }
static void app_resume(void *data) { (void)data; }

// ---------- main ----------
int main(int argc, char *argv[]) {
    appdata_s ad; memset(&ad, 0, sizeof(ad));
    ui_app_lifecycle_callback_s event_callback; memset(&event_callback, 0, sizeof(event_callback));
    event_callback.create = app_create;
    event_callback.terminate = app_terminate;
    event_callback.pause = app_pause;
    event_callback.resume = app_resume;
    event_callback.app_control = app_control;
    return ui_app_main(argc, argv, &event_callback, &ad);
}