#define ELM_DEPRECATED_API_SUPPORT

#include <app.h>
#include <Elementary.h>
#include <Evas.h>
#include <curl/curl.h>
#include <dlog.h>
#include <sys/stat.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>
#include <stdbool.h>
#include "cJSON.h"

// ---------- CONFIG ----------
#define TOKEN_DIR "/opt/usr/home/owner/apps_private/smartthings_app/"
#define TOKEN_FILE TOKEN_DIR "token.txt"
#define API_BASE "https://api.smartthings.com/v1"
#define REFRESH_INTERVAL_SEC 30
#define TOKEN_URL "https://auth-global.api.smartthings.com/oauth/token"

// ---------- STRUCTS ----------
typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_output;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    bool live_running;
} appdata_s;

typedef struct { char *buf; size_t len; } mem_t;
typedef struct {
    char client_id[256];
    char client_secret[256];
    char refresh_token[1024];
    char access_token[1024];
    char expires_in[64];
} token_data_t;

// ---------- GLOBAL ----------
static char *ACCESS_TOKEN = NULL;
static const char* DEVICE_ID = "95c6572c-6373-41f4-9cba-daf39a38f59c";

// ---------- LOGGING ----------
static void ui_log_append(appdata_s *ad, const char *text) {
    const char *prev = elm_entry_entry_get(ad->entry_log);
    char *new_txt = malloc(strlen(prev) + strlen(text) + 8);
    sprintf(new_txt, "%s<br>%s", prev, text);
    elm_entry_entry_set(ad->entry_log, new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
}

static void log_event(const char *msg) {
    const char *logfile = TOKEN_DIR "app_log.txt";
    FILE *fp = fopen(logfile, "a");
    if (fp) {
        time_t now = time(NULL);
        fprintf(fp, "[%s] %s\n", ctime(&now), msg);
        fclose(fp);
    }
    dlog_print(DLOG_INFO, "ST_LOG", "%s", msg);
}

// ---------- HTTP HELPERS ----------
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

static char* http_post(const char *url,const char *token,const char *payload){
    CURL *curl=curl_easy_init(); if(!curl)return NULL;
    mem_t m={.buf=calloc(1,1),.len=0};
    struct curl_slist *hdr=NULL; char auth[512];
    snprintf(auth,sizeof(auth),"Authorization: Bearer %s",token);
    hdr=curl_slist_append(hdr,auth);
    hdr=curl_slist_append(hdr,"Content-Type: application/json");
    curl_easy_setopt(curl,CURLOPT_URL,url);
    curl_easy_setopt(curl,CURLOPT_HTTPHEADER,hdr);
    curl_easy_setopt(curl,CURLOPT_POSTFIELDS,payload);
    curl_easy_setopt(curl,CURLOPT_WRITEFUNCTION,write_cb);
    curl_easy_setopt(curl,CURLOPT_WRITEDATA,&m);
    curl_easy_perform(curl); curl_easy_cleanup(curl);
    curl_slist_free_all(hdr);
    return m.buf;
}

static bool http_download_file(const char *url,const char *token,const char *save_path){
    CURL *curl=curl_easy_init(); if(!curl)return false;
    FILE *fp=fopen(save_path,"wb"); if(!fp)return false;
    struct curl_slist *hdr=NULL; char auth[512];
    snprintf(auth,sizeof(auth),"Authorization: Bearer %s",token);
    hdr=curl_slist_append(hdr,auth);
    curl_easy_setopt(curl,CURLOPT_URL,url);
    curl_easy_setopt(curl,CURLOPT_HTTPHEADER,hdr);
    curl_easy_setopt(curl,CURLOPT_WRITEDATA,fp);
    CURLcode res=curl_easy_perform(curl);
    curl_easy_cleanup(curl); curl_slist_free_all(hdr); fclose(fp);
    return (res==CURLE_OK);
}

// ---------- TOKEN FILE HANDLING ----------
static bool read_kv_file(const char *path, token_data_t *t) {
    FILE *fp = fopen(path, "r");
    if (!fp) return false;
    char line[512];
    while (fgets(line, sizeof(line), fp)) {
        char *eq = strchr(line, '=');
        if (!eq) continue;
        *eq = '\0';
        char *key = line, *val = eq + 1;
        val[strcspn(val, "\r\n")] = '\0';
        if (strcmp(key, "client_id") == 0) strncpy(t->client_id, val, sizeof(t->client_id));
        else if (strcmp(key, "client_secret") == 0) strncpy(t->client_secret, val, sizeof(t->client_secret));
        else if (strcmp(key, "refresh_token") == 0) strncpy(t->refresh_token, val, sizeof(t->refresh_token));
        else if (strcmp(key, "access_token") == 0) strncpy(t->access_token, val, sizeof(t->access_token));
        else if (strcmp(key, "expires_in") == 0) strncpy(t->expires_in, val, sizeof(t->expires_in));
    }
    fclose(fp);
    return true;
}

static bool write_kv_file(const char *path, token_data_t *t) {
    FILE *fp = fopen(path, "w");
    if (!fp) return false;
    fprintf(fp,"client_id=%s\nclient_secret=%s\nrefresh_token=%s\naccess_token=%s\nexpires_in=%s\n",
        t->client_id, t->client_secret, t->refresh_token, t->access_token, t->expires_in);
    fclose(fp);
    log_event("💾 token.txt updated successfully.");
    return true;
}

// ---------- TOKEN REFRESH ----------
static bool refresh_token_c(token_data_t *t) {
    log_event("🔁 Performing SmartThings token refresh...");
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    char credentials[1024];
    snprintf(credentials, sizeof(credentials), "%s:%s", t->client_id, t->client_secret);
    char *b64 = NULL;
    {
        static const char tbl[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        size_t out_len=((strlen(credentials)+2)/3)*4+4;
        b64=malloc(out_len); int val=0,valb=-6,i,j=0;
        for(i=0;credentials[i];i++){val=(val<<8)+credentials[i];valb+=8;
            while(valb>=0){b64[j++]=tbl[(val>>valb)&0x3F];valb-=6;}}
        while(valb>-6){b64[j++]=tbl[((val<<8)>>(valb+8))&0x3F];valb-=6;}
        while(j%4)b64[j++]='='; b64[j]='\0';
    }

    char auth[512]; snprintf(auth,sizeof(auth),"Authorization: Basic %s",b64);
    free(b64);
    char data[1024];
    snprintf(data,sizeof(data),"grant_type=refresh_token&refresh_token=%s",t->refresh_token);

    mem_t m={.buf=calloc(1,1),.len=0};
    struct curl_slist *headers=NULL;
    headers=curl_slist_append(headers,auth);
    headers=curl_slist_append(headers,"Content-Type: application/x-www-form-urlencoded");
    curl_easy_setopt(curl,CURLOPT_URL,TOKEN_URL);
    curl_easy_setopt(curl,CURLOPT_HTTPHEADER,headers);
    curl_easy_setopt(curl,CURLOPT_POSTFIELDS,data);
    curl_easy_setopt(curl,CURLOPT_WRITEFUNCTION,write_cb);
    curl_easy_setopt(curl,CURLOPT_WRITEDATA,&m);
    curl_easy_setopt(curl,CURLOPT_SSL_VERIFYPEER,0L);
    CURLcode res=curl_easy_perform(curl);
    curl_slist_free_all(headers); curl_easy_cleanup(curl);
    if(res!=CURLE_OK){ log_event("❌ CURL refresh failed."); free(m.buf); return false; }

    cJSON *json=cJSON_Parse(m.buf);
    if(!json){ log_event("❌ JSON parse failed."); free(m.buf); return false; }
    const cJSON *acc=cJSON_GetObjectItem(json,"access_token");
    const cJSON *ref=cJSON_GetObjectItem(json,"refresh_token");
    if(acc&&acc->valuestring) strncpy(t->access_token,acc->valuestring,sizeof(t->access_token));
    if(ref&&ref->valuestring) strncpy(t->refresh_token,ref->valuestring,sizeof(t->refresh_token));
    cJSON_Delete(json); free(m.buf);
    log_event("✅ Token refreshed successfully.");
    return true;
}

// ---------- TOKEN INITIALIZATION ----------
static bool validate_access_token(const char *token) {
    if (!token || strlen(token) < 10) return false;
    const char *test_endpoint = "https://api.smartthings.com/v1/devices";
    char *resp = http_get(test_endpoint, token);
    if (!resp) return false;
    bool valid = strstr(resp, "items") != NULL;
    free(resp);
    return valid;
}

static void ensure_token_dir_exists(void) {
    struct stat st = {0};
    if (stat(TOKEN_DIR, &st) == -1) mkdir(TOKEN_DIR, 0777);
}

static bool initialize_token_file(appdata_s *ad) {
    ensure_token_dir_exists();
    const char *res_dir = app_get_resource_path();
    char res_token[512];
    snprintf(res_token, sizeof(res_token), "%stoken.txt", res_dir);
    token_data_t t = {0};

    struct stat st;
    if (stat(TOKEN_FILE, &st) == 0) {
        ui_log_append(ad, "🔍 Found token.txt in permanent storage.");
        if (!read_kv_file(TOKEN_FILE, &t)) return false;
        if (validate_access_token(t.access_token)) {
            ui_log_append(ad, "✅ Access token valid.");
            ACCESS_TOKEN = strdup(t.access_token);
            return true;
        }
        if (refresh_token_c(&t)) {
            write_kv_file(TOKEN_FILE, &t);
            ACCESS_TOKEN = strdup(t.access_token);
            ui_log_append(ad, "✅ Token refreshed.");
            return true;
        }
        return false;
    }

    ui_log_append(ad, "📁 Copying token.txt from res...");
    FILE *src=fopen(res_token,"r"); if(!src)return false;
    FILE *dst=fopen(TOKEN_FILE,"w"); if(!dst){fclose(src);return false;}
    char buf[1024]; size_t n; while((n=fread(buf,1,sizeof(buf),src))>0) fwrite(buf,1,n,dst);
    fclose(src); fclose(dst);
    if (read_kv_file(TOKEN_FILE,&t)&&refresh_token_c(&t)){
        write_kv_file(TOKEN_FILE,&t); ACCESS_TOKEN=strdup(t.access_token);
        ui_log_append(ad,"✅ Token initialized and refreshed."); return true;
    }
    return false;
}

// ---------- UI CREATION ----------
static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add("ST_LIVE","SmartThings Live Capture");
    elm_win_autodel_set(ad->win,EINA_TRUE);
    evas_object_color_set(ad->win,200,200,200,255);

    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win,ad->conform);
    evas_object_show(ad->conform);

    ad->box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform,ad->box);
    evas_object_show(ad->box);

    Evas_Object *btn_caps=elm_button_add(ad->box);
    elm_object_text_set(btn_caps,"Show Capabilities");
    evas_object_size_hint_weight_set(btn_caps,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,btn_caps);
    evas_object_show(btn_caps);

    ad->img_view = elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view,EINA_TRUE,EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view,EINA_FALSE);
    evas_object_size_hint_weight_set(ad->img_view,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,ad->img_view);
    evas_object_hide(ad->img_view);

    Evas_Object *btn_live=elm_button_add(ad->box);
    elm_object_text_set(btn_live,"Start Live Capture");
    evas_object_size_hint_weight_set(btn_live,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,btn_live);
    evas_object_show(btn_live);

    Evas_Object *scroller=elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller,EVAS_HINT_EXPAND,0.4);
    elm_box_pack_end(ad->box,scroller);

    ad->entry_log=elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log,EINA_TRUE);
    elm_entry_editable_set(ad->entry_log,EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log,ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log,"Initializing SmartThings app...");
    elm_object_content_set(scroller,ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    ad->entry_output=elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_output,EINA_TRUE);
    elm_entry_editable_set(ad->entry_output,EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_output,ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_output,"Model Output:");
    elm_box_pack_end(ad->box,ad->entry_output);
    evas_object_show(ad->entry_output);

    evas_object_show(ad->win);
}

// ---------- MAIN ----------
static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    create_base_gui(ad);
    ui_log_append(ad,"🚀 Initializing SmartThings Token System...");
    if(initialize_token_file(ad))
        ui_log_append(ad,"✅ Token system ready.");
    else ui_log_append(ad,"❌ Token initialization failed.");
    return true;
}

static void app_control(app_control_h app_control, void *data){}
static void app_pause(void *data){}
static void app_resume(void *data){}
static void app_terminate(void *data){curl_global_cleanup();}

int main(int argc,char*argv[]){
    appdata_s ad={0,};
    ui_app_lifecycle_callback_s cb={0,};
    cb.create=app_create;
    cb.terminate=app_terminate;
    cb.pause=app_pause;
    cb.resume=app_resume;
    cb.app_control=app_control;
    return ui_app_main(argc,argv,&cb,&ad);
}