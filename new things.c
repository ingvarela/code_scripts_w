#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>

#define LOG_TAG "ST_TOKEN_FLOW"
#define TOKEN_FILE "tokens.txt"
#define TOKEN_ENDPOINT "https://auth-global.api.smartthings.com/oauth/token"

typedef struct {
    Evas_Object *win, *conform, *box, *entry_log;
} appdata_s;

typedef struct {
    char client_id[512];
    char client_secret[512];
    char auth_code[128];
    char access_token[4096];
    char refresh_token[2048];
} token_data_t;

/* ---------- Logging UI ---------- */
static void ui_log_append(appdata_s *ad, const char *text) {
    const char *prev = elm_entry_entry_get(ad->entry_log);
    size_t new_len = strlen(prev) + strlen(text) + 8;
    char *new_txt = malloc(new_len);
    snprintf(new_txt, new_len, "%s<br>%s", prev, text);
    elm_entry_entry_set(ad->entry_log, new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
}

/* ---------- CURL buffer ---------- */
typedef struct { char *buf; size_t len; } mem_t;
static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = userdata;
    size_t add = size * nmemb;
    m->buf = realloc(m->buf, m->len + add + 1);
    memcpy(m->buf + m->len, ptr, add);
    m->len += add;
    m->buf[m->len] = '\0';
    return add;
}

/* ---------- Token File IO ---------- */
static void ensure_data_folder(void) {
    const char *path = app_get_data_path();
    struct stat st = {0};
    if (stat(path, &st) == -1) mkdir(path, 0755);
}

static char* token_file_path(void) {
    static char path[512];
    snprintf(path, sizeof(path), "%s%s", app_get_data_path(), TOKEN_FILE);
    return path;
}

static bool load_tokens(token_data_t *t) {
    FILE *fp = fopen(token_file_path(), "r");
    if (!fp) return false;
    char line[2048];
    while (fgets(line, sizeof(line), fp)) {
        char *eq = strchr(line, '=');
        if (!eq) continue;
        *eq = '\0';
        char *key = line;
        char *val = eq + 1;
        val[strcspn(val, "\r\n")] = '\0';
        if (!strcmp(key, "client_id")) strncpy(t->client_id, val, sizeof(t->client_id)-1);
        else if (!strcmp(key, "client_secret")) strncpy(t->client_secret, val, sizeof(t->client_secret)-1);
        else if (!strcmp(key, "auth_code")) strncpy(t->auth_code, val, sizeof(t->auth_code)-1);
        else if (!strcmp(key, "access_token")) strncpy(t->access_token, val, sizeof(t->access_token)-1);
        else if (!strcmp(key, "refresh_token")) strncpy(t->refresh_token, val, sizeof(t->refresh_token)-1);
    }
    fclose(fp);
    return true;
}

static void save_tokens(const token_data_t *t) {
    FILE *fp = fopen(token_file_path(), "w");
    if (!fp) return;
    fprintf(fp, "client_id=%s\n", t->client_id);
    fprintf(fp, "client_secret=%s\n", t->client_secret);
    fprintf(fp, "auth_code=%s\n", t->auth_code);
    fprintf(fp, "access_token=%s\n", t->access_token);
    fprintf(fp, "refresh_token=%s\n", t->refresh_token);
    fclose(fp);
}

/* ---------- Token Requests ---------- */
static bool http_post_form(const char *body, mem_t *m) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;
    m->buf = calloc(1,1); m->len = 0;
    curl_easy_setopt(curl, CURLOPT_URL, TOKEN_ENDPOINT);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, m);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    return (res == CURLE_OK);
}

static bool parse_and_store_tokens(mem_t *m, token_data_t *t) {
    char *acc = strstr(m->buf, "\"access_token\"");
    char *ref = strstr(m->buf, "\"refresh_token\"");
    if (!acc || !ref) return false;
    sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", t->access_token);
    sscanf(ref, "\"refresh_token\"%*[^:]:\"%2047[^\"]\"", t->refresh_token);
    return (strlen(t->access_token) > 0 && strlen(t->refresh_token) > 0);
}

static bool exchange_auth_code(appdata_s *ad, token_data_t *t) {
    if (strlen(t->auth_code) == 0) return false;
    ui_log_append(ad, "Requesting new tokens using authorization code...");
    char body[2048];
    snprintf(body, sizeof(body),
        "grant_type=authorization_code&client_id=%s&client_secret=%s&code=%s&redirect_uri=https://postman-echo.com/get",
        t->client_id, t->client_secret, t->auth_code);

    mem_t m = {0};
    if (!http_post_form(body, &m)) { ui_log_append(ad, "HTTP request failed."); free(m.buf); return false; }

    bool ok = parse_and_store_tokens(&m, t);
    free(m.buf);
    if (ok) {
        ui_log_append(ad, "Received new access + refresh tokens.");
        save_tokens(t);
    } else ui_log_append(ad, "Failed to parse token response.");
    return ok;
}

static bool refresh_tokens(appdata_s *ad, token_data_t *t) {
    if (strlen(t->refresh_token) == 0) return false;
    ui_log_append(ad, "Refreshing access token...");
    char body[2048];
    snprintf(body, sizeof(body),
        "grant_type=refresh_token&client_id=%s&client_secret=%s&refresh_token=%s",
        t->client_id, t->client_secret, t->refresh_token);

    mem_t m = {0};
    if (!http_post_form(body, &m)) { ui_log_append(ad, "HTTP request failed."); free(m.buf); return false; }

    bool ok = parse_and_store_tokens(&m, t);
    free(m.buf);
    if (ok) {
        ui_log_append(ad, "Refreshed tokens successfully.");
        save_tokens(t);
    } else ui_log_append(ad, "Failed to parse refreshed token response.");
    return ok;
}

/* ---------- Button callbacks ---------- */
static void refresh_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    token_data_t t = {0};
    ensure_data_folder();
    if (!load_tokens(&t)) { ui_log_append(ad, "Cannot read tokens.txt."); return; }

    if (strlen(t.access_token) == 0 && strlen(t.auth_code) > 0) {
        exchange_auth_code(ad, &t);
    } else {
        refresh_tokens(ad, &t);
    }
}

/* ---------- GUI ---------- */
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("token-refresh", "SmartThings Token Manager");
    elm_win_autodel_set(ad->win, EINA_TRUE);

    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    ad->box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);

    Evas_Object *btn = elm_button_add(ad->box);
    elm_object_text_set(btn, "Get / Refresh Tokens");
    evas_object_smart_callback_add(btn, "clicked", refresh_clicked, ad);
    elm_box_pack_end(ad->box, btn);
    evas_object_show(btn);

    ad->entry_log = elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_WORD);
    elm_entry_entry_set(ad->entry_log, "Press button to obtain tokens...");
    evas_object_size_hint_weight_set(ad->entry_log, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad->entry_log, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, ad->entry_log);
    evas_object_show(ad->entry_log);

    evas_object_show(ad->win);
}

/* ---------- Lifecycle ---------- */
static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_data_folder();
    create_base_gui(ad);
    return true;
}
static void app_terminate(void *data) { curl_global_cleanup(); }
static void app_control(app_control_h app_control, void *data) {}
static void app_pause(void *data) {}
static void app_resume(void *data) {}

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