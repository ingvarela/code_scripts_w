#include "st_rest.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <cJSON.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>
#include <tizen.h>
#include <libgen.h>

// ---------- CONFIG ----------
static const char* API_BASE = "https://api.smartthings.com/v1";
#define REFRESH_INTERVAL_SEC 30
#define TOKEN_URL "https://auth-global.api.smartthings.com/oauth/token"
// ----------------------------

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_output;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    bool live_running;
    bool live_continuous;
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
// ----------------------------

// ====================================================
// BASIC UTILS
// ====================================================
static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = userdata;
    size_t new_len = m->len + size * nmemb;
    m->buf = realloc(m->buf, new_len + 1);
    memcpy(m->buf + m->len, ptr, size * nmemb);
    m->buf[new_len] = '\0';
    m->len = new_len;
    return size * nmemb;
}

static void log_event(const char *msg) {
    const char *data_path = app_get_data_path();
    char log_path[512];
    snprintf(log_path, sizeof(log_path), "%stoken_refresh.log", data_path);
    FILE *fp = fopen(log_path, "a");
    if (fp) {
        time_t now = time(NULL);
        fprintf(fp, "[%s] %s\n", ctime(&now), msg);
        fclose(fp);
    }
    dlog_print(DLOG_INFO, "ST_LOG", "%s", msg);
}

// ====================================================
// STEP 1 — FIRST-RUN COPY (only if not already in /data)
// ====================================================
static bool ensure_token_in_data_path(void) {
    const char *data_dir = app_get_data_path();
    const char *res_dir  = app_get_resource_path();
    char data_path[512], res_path[512];
    snprintf(data_path, sizeof(data_path), "%stoken.txt", data_dir);
    snprintf(res_path,  sizeof(res_path),  "%stoken.txt", res_dir);

    struct stat st;
    if (stat(data_path, &st) == 0) {
        log_event("✅ token.txt already present in data path (no copy performed).");
        return true;
    }

    FILE *src = fopen(res_path, "r");
    if (!src) {
        log_event("❌ Failed to open source token.txt in res.");
        return false;
    }
    FILE *dst = fopen(data_path, "w");
    if (!dst) {
        log_event("❌ Failed to create token.txt in data path.");
        fclose(src);
        return false;
    }

    char buf[1024];
    size_t bytes;
    while ((bytes = fread(buf, 1, sizeof(buf), src)) > 0)
        fwrite(buf, 1, bytes, dst);
    fclose(src); fclose(dst);
    log_event("✅ token.txt copied from res → data (first run).");
    return true;
}

// ====================================================
// TOKEN REFRESH HANDLERS
// ====================================================
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
    fprintf(fp,
        "client_id=%s\nclient_secret=%s\nrefresh_token=%s\naccess_token=%s\nexpires_in=%s\n",
        t->client_id, t->client_secret, t->refresh_token, t->access_token, t->expires_in);
    fclose(fp);
    log_event("💾 token.txt updated successfully.");
    return true;
}

static bool refresh_token_c(token_data_t *t) {
    log_event("🔁 Performing SmartThings token refresh...");
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    // Base64 encode Basic Auth manually
    char credentials[1024];
    snprintf(credentials, sizeof(credentials), "%s:%s", t->client_id, t->client_secret);
    char *b64 = NULL;
    {
        size_t out_len = ((strlen(credentials) + 2) / 3) * 4 + 4;
        b64 = malloc(out_len);
        const char *tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        int val=0, valb=-6, i,j=0;
        for (i=0; credentials[i]; i++) {
            val=(val<<8)+credentials[i];
            valb+=8;
            while(valb>=0){ b64[j++]=tbl[(val>>valb)&0x3F]; valb-=6;}
        }
        while(valb>-6){ b64[j++]=tbl[((val<<8)>>(valb+8))&0x3F]; valb-=6;}
        while(j%4) b64[j++]='=';
        b64[j]='\0';
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
    if(!json){ log_event("❌ JSON parse failed."); free(m.buf); return false;}
    const cJSON *acc=cJSON_GetObjectItem(json,"access_token");
    const cJSON *ref=cJSON_GetObjectItem(json,"refresh_token");
    const cJSON *exp=cJSON_GetObjectItem(json,"expires_in");
    if(acc&&acc->valuestring) strncpy(t->access_token,acc->valuestring,sizeof(t->access_token));
    if(ref&&ref->valuestring) strncpy(t->refresh_token,ref->valuestring,sizeof(t->refresh_token));
    if(exp&&exp->valuestring) snprintf(t->expires_in,sizeof(t->expires_in),"%s",exp->valuestring);
    cJSON_Delete(json); free(m.buf);
    log_event("✅ Token refreshed successfully.");
    return true;
}

// ====================================================
// REFRESH SEQUENCE WITH UI FEEDBACK
// ====================================================
static bool token_refresh_sequence(appdata_s *ad) {
    const char *data_path = app_get_data_path();
    char token_path[512]; snprintf(token_path,sizeof(token_path),"%stoken.txt",data_path);
    token_data_t t={0};
    if(!read_kv_file(token_path,&t)){
        log_event("❌ Could not read token.txt."); elm_entry_entry_set(ad->entry_log,"❌ Missing token.txt."); return false;
    }
    if(!refresh_token_c(&t)){
        log_event("❌ Refresh failed."); elm_entry_entry_set(ad->entry_log,"⚠️ Token expired or invalid. Replace res/token.txt."); return false;
    }
    if(!write_kv_file(token_path,&t)){
        log_event("⚠️ Write failed."); elm_entry_entry_set(ad->entry_log,"⚠️ Could not write token.txt."); return false;
    }
    ACCESS_TOKEN=strdup(t.access_token);
    log_event("🔓 ACCESS_TOKEN updated.");
    elm_entry_entry_set(ad->entry_log,"✅ Token refreshed successfully.");
    return true;
}

// ====================================================
// HTTP POST + FILE DOWNLOAD HELPERS
// ====================================================
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

// ====================================================
// IMAGE CAPTURE LOGIC
// ====================================================
static void take_image_capture(appdata_s *ad){
    if(!ACCESS_TOKEN){ ui_log_append(ad,"⚠️ No valid ACCESS_TOKEN."); return;}
    char url[512]; snprintf(url,sizeof(url),"%s/devices/%s/commands",API_BASE,DEVICE_ID);

    ui_log_append(ad,"📷 Sending image capture command...");
    const char *payload_take="{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\",\"command\":\"take\",\"arguments\":[]}]}";
    char *resp=http_post(url,ACCESS_TOKEN,payload_take);
    free(resp);
    sleep(2);

    snprintf(url,sizeof(url),"%s/devices/%s/status",API_BASE,DEVICE_ID);
    char *status=http_post(url,ACCESS_TOKEN,"");
    if(!status){ ui_log_append(ad,"❌ Failed to fetch status."); return;}
    char *found=strstr(status,"https://");
    if(!found){ ui_log_append(ad,"❌ No image URL in response."); free(status); return;}
    char img_url[512]; sscanf(found,"%511[^\"]",img_url); free(status);

    const char *data_path=app_get_data_path();
    char img_path[512]; snprintf(img_path,sizeof(img_path),"%scaptured_image.jpg",data_path);
    if(http_download_file(img_url,ACCESS_TOKEN,img_path)){
        ui_log_append(ad,"✅ Image downloaded.");
        elm_image_file_set(ad->img_view,img_path,NULL);
        evas_object_show(ad->img_view);
    } else ui_log_append(ad,"❌ Download failed.");
}

// ====================================================
// UI HELPERS
// ====================================================
static void ui_log_append(appdata_s *ad,const char *text){
    const char *prev=elm_entry_entry_get(ad->entry_log);
    char *new_txt=malloc(strlen(prev)+strlen(text)+8);
    sprintf(new_txt,"%s<br>%s",prev,text);
    elm_entry_entry_set(ad->entry_log,new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
}

// ====================================================
// UI CREATION
// ====================================================
static void create_base_gui(appdata_s *ad){
    ad->win=elm_win_util_standard_add("ST_LIVE","SmartThings Live Capture");
    elm_win_autodel_set(ad->win,EINA_TRUE);

    ad->conform=elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win,ad->conform);
    evas_object_show(ad->conform);

    ad->box=elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform,ad->box);
    evas_object_show(ad->box);

    // Capture button
    Evas_Object *btn_capture=elm_button_add(ad->box);
    elm_object_text_set(btn_capture,"Capture Image");
    evas_object_smart_callback_add(btn_capture,"clicked",take_image_capture,ad);
    elm_box_pack_end(ad->box,btn_capture); evas_object_show(btn_capture);

    ad->img_view=elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view,EINA_TRUE,EINA_TRUE);
    evas_object_size_hint_weight_set(ad->img_view,EVAS_HINT_EXPAND,EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box,ad->img_view);

    ad->entry_log=elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_log,EINA_TRUE);
    elm_entry_editable_set(ad->entry_log,EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log,ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log,"Initializing...");
    elm_box_pack_end(ad->box,ad->entry_log);
    evas_object_show(ad->entry_log);

    evas_object_show(ad->win);
}

// ====================================================
// APP LIFECYCLE
// ====================================================
static bool app_create(void *data){
    appdata_s *ad=data; curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_token_in_data_path();
    create_base_gui(ad);
    ui_log_append(ad,"🔁 Checking SmartThings token...");
    if(!token_refresh_sequence(ad)){
        ui_log_append(ad,"⚠️ Token invalid or expired. Replace res/token.txt.");
        return true;
    }
    ui_log_append(ad,"✅ Token refreshed. Ready to capture.");
    return true;
}

static void app_terminate(void *data){ curl_global_cleanup(); }

int main(int argc,char *argv[]){
    appdata_s ad={0,}; ui_app_lifecycle_callback_s cb={0,};
    cb.create=app_create; cb.terminate=app_terminate;
    return ui_app_main(argc,argv,&cb,&ad);
}