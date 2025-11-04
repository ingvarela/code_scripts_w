#include "ProjectName.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <stdbool.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <app_common.h>
#include <time.h>

#define LOG_TAG "ST_AUTO_REFRESH"
#define TOKEN_FILE "tokens.txt"
#define SAVE_FOLDER "/opt/usr/home/owner/media/Images"
#define API_BASE "https://api.smartthings.com/v1"
#define TOKEN_ENDPOINT "https://auth-global.api.smartthings.com/oauth/token"
#define REFRESH_INTERVAL_HOURS 24

typedef struct {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    Ecore_Timer *refresh_timer;
} appdata_s;

typedef struct {
    char client_id[512];
    char client_secret[512];
    char auth_code[256];
    char access_token[4096];
    char refresh_token[2048];
    char device_id[128];
} token_data_t;

typedef struct { char *buf; size_t len; } mem_t;

/* ---------- Utility: Logging ---------- */
static void ui_log(appdata_s *ad, const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    char buf[1024];
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    const char *prev = elm_entry_entry_get(ad->entry_log);
    size_t new_len = strlen(prev) + strlen(buf) + 8;
    char *new_txt = malloc(new_len);
    snprintf(new_txt, new_len, "%s<br>%s", prev, buf);
    elm_entry_entry_set(ad->entry_log, new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
    dlog_print(DLOG_INFO, LOG_TAG, "%s", buf);
}

/* ---------- File and Folder ---------- */
static void ensure_paths(void) {
    struct stat st = {0};
    const char *data_path = app_get_data_path();
    if (stat(data_path, &st) == -1) mkdir(data_path, 0755);
    if (stat(SAVE_FOLDER, &st) == -1) mkdir(SAVE_FOLDER, 0755);
}

static char* token_file_path(void) {
    static char path[512];
    snprintf(path, sizeof(path), "%s%s", app_get_data_path(), TOKEN_FILE);
    return path;
}

/* ---------- File read/write ---------- */
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
        else if (!strcmp(key, "device_id")) strncpy(t->device_id, val, sizeof(t->device_id)-1);
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
    fprintf(fp, "device_id=%s\n", t->device_id);
    fclose(fp);
}

/* ---------- CURL helpers ---------- */
static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = userdata;
    size_t add = size * nmemb;
    m->buf = realloc(m->buf, m->len + add + 1);
    memcpy(m->buf + m->len, ptr, add);
    m->len += add;
    m->buf[m->len] = '\0';
    return add;
}

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

/* ---------- Token Management ---------- */
static bool parse_and_store_tokens(mem_t *m, token_data_t *t) {
    char *acc = strstr(m->buf, "\"access_token\"");
    char *ref = strstr(m->buf, "\"refresh_token\"");
    if (!acc) return false;
    sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", t->access_token);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%2047[^\"]\"", t->refresh_token);
    return (strlen(t->access_token) > 0);
}

static bool exchange_auth_code(appdata_s *ad, token_data_t *t) {
    ui_log(ad, "Obtaining tokens using auth code...");
    char body[2048];
    snprintf(body, sizeof(body),
        "grant_type=authorization_code&client_id=%s&client_secret=%s&code=%s&redirect_uri=https://postman-echo.com/get",
        t->client_id, t->client_secret, t->auth_code);
    mem_t m = {0};
    if (!http_post_form(body, &m)) { ui_log(ad, "Auth code exchange failed."); free(m.buf); return false; }
    bool ok = parse_and_store_tokens(&m, t);
    free(m.buf);
    if (ok) { save_tokens(t); ui_log(ad, "New tokens obtained."); }
    return ok;
}

static bool refresh_tokens(appdata_s *ad, token_data_t *t) {
    if (strlen(t->refresh_token)==0) return false;
    ui_log(ad, "Refreshing access token...");
    char body[2048];
    snprintf(body, sizeof(body),
        "grant_type=refresh_token&client_id=%s&client_secret=%s&refresh_token=%s",
        t->client_id, t->client_secret, t->refresh_token);
    mem_t m = {0};
    if (!http_post_form(body, &m)) { ui_log(ad, "Token refresh failed."); free(m.buf); return false; }
    bool ok = parse_and_store_tokens(&m, t);
    free(m.buf);
    if (ok) { save_tokens(t); ui_log(ad, "Token refreshed successfully."); }
    return ok;
}

static bool check_tokens_and_refresh(appdata_s *ad, token_data_t *t) {
    if (strlen(t->access_token)==0) {
        if (strlen(t->refresh_token)>0) return refresh_tokens(ad, t);
        else if (strlen(t->auth_code)>0) return exchange_auth_code(ad, t);
        else { ui_log(ad, "No credentials available."); return false; }
    }
    return true;
}

/* ---------- Image Capture ---------- */
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

static bool take_image_capture(appdata_s *ad, token_data_t *t) {
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, t->device_id);
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\",\"command\":\"take\"}]}";

    CURL *curl = curl_easy_init();
    if (!curl) return false;
    mem_t m = {.buf=calloc(1,1),.len=0};
    struct curl_slist *headers=NULL;
    char auth[512]; snprintf(auth,sizeof(auth),"Authorization: Bearer %s",t->access_token);
    headers=curl_slist_append(headers,auth);
    headers=curl_slist_append(headers,"Content-Type: application/json");
    curl_easy_setopt(curl,CURLOPT_URL,url);
    curl_easy_setopt(curl,CURLOPT_POSTFIELDS,payload);
    curl_easy_setopt(curl,CURLOPT_HTTPHEADER,headers);
    curl_easy_setopt(curl,CURLOPT_WRITEFUNCTION,write_cb);
    curl_easy_setopt(curl,CURLOPT_WRITEDATA,&m);
    CURLcode res=curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    free(m.buf);
    if(res!=CURLE_OK){ui_log(ad,"Capture command failed.");return false;}

    sleep(3);

    snprintf(url,sizeof(url),"%s/devices/%s/status",API_BASE,t->device_id);
    CURL *curl2=curl_easy_init();
    mem_t s={.buf=calloc(1,1),.len=0};
    headers=NULL;
    headers=curl_slist_append(headers,auth);
    curl_easy_setopt(curl2,CURLOPT_URL,url);
    curl_easy_setopt(curl2,CURLOPT_HTTPHEADER,headers);
    curl_easy_setopt(curl2,CURLOPT_WRITEFUNCTION,write_cb);
    curl_easy_setopt(curl2,CURLOPT_WRITEDATA,&s);
    curl_easy_perform(curl2);
    curl_easy_cleanup(curl2);
    curl_slist_free_all(headers);
    char *found=strstr(s.buf,"https://");
    if(!found){ui_log(ad,"No image URL found.");free(s.buf);return false;}
    char image_url[512]; sscanf(found,"%511[^\"]",image_url);
    char save_path[512]; snprintf(save_path,sizeof(save_path),"%s/capture.jpg",SAVE_FOLDER);
    bool ok=http_download_file(image_url,t->access_token,save_path);
    free(s.buf);
    if(ok){elm_image_file_set(ad->img_view,save_path,NULL);evas_object_show(ad->img_view);ui_log(ad,"Image saved and displayed.");}
    return ok;
}

/* ---------- Auto Refresh Timer ---------- */
static Eina_Bool refresh_timer_cb(void *data) {
    appdata_s *ad = data;
    token_data_t t = {0};
    if (load_tokens(&t)) {
        ui_log(ad, "Performing scheduled 24h token refresh...");
        refresh_tokens(ad, &t);
    }
    return ECORE_CALLBACK_RENEW;  // keep timer repeating
}

/* ---------- GUI ---------- */
static void create_gui(appdata_s *ad){
    ad->win=elm_win_util_standard_add("smartthings","SmartThings Auto Capture");
    elm_win_autodel_set(ad->win,EINA_TRUE);
    ad->conform=elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win,ad->conform);
    evas_object_show(ad->conform);
    ad->box=elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform,ad->box);
    evas_object_show(ad->box);
    ad->entry_log=elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_log,EINA_TRUE);
    elm_entry_editable_set(ad->entry_log,EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log,ELM_WRAP_WORD);
    elm_entry_entry_set(ad->entry_log,"Initializing...");
    evas_object_size_hint_weight_set(ad->entry_log,EVAS_HINT_EXPAND,0.4);
    evas_object_size_hint_align_set(ad->entry_log,EVAS_HINT_FILL,EVAS_HINT_FILL);
    elm_box_pack_end(ad->box,ad->entry_log);
    evas_object_show(ad->entry_log);
    ad->img_view=elm_image_add(ad->box);
    evas_object_size_hint_weight_set(ad->img_view,EVAS_HINT_EXPAND,0.6);
    evas_object_size_hint_align_set(ad->img_view,EVAS_HINT_FILL,EVAS_HINT_FILL);
    elm_box_pack_end(ad->box,ad->img_view);
    evas_object_show(ad->win);
}

/* ---------- Lifecycle ---------- */
static bool app_create(void *data){
    appdata_s *ad=data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_paths();
    create_gui(ad);
    token_data_t t={0};
    if(!load_tokens(&t)){ui_log(ad,"tokens.txt missing");return true;}
    if(check_tokens_and_refresh(ad,&t)){
        ui_log(ad,"Credentials verified, capturing...");
        take_image_capture(ad,&t);
    }else ui_log(ad,"Failed to initialize credentials.");
    // schedule automatic refresh every 24 hours
    ad->refresh_timer = ecore_timer_add(REFRESH_INTERVAL_HOURS*3600, refresh_timer_cb, ad);
    ui_log(ad, "Scheduled 24-hour background refresh.");
    return true;
}

static void app_terminate(void *data){curl_global_cleanup();}
static void app_control(app_control_h app_control,void *data){}
static void app_pause(void *data){}
static void app_resume(void *data){}

int main(int argc,char *argv[]){
    appdata_s ad={0,};
    ui_app_lifecycle_callback_s event_callback={0,};
    event_callback.create=app_create;
    event_callback.terminate=app_terminate;
    event_callback.pause=app_pause;
    event_callback.resume=app_resume;
    event_callback.app_control=app_control;
    return ui_app_main(argc,argv,&event_callback,&ad);
}