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
#define TOKEN_DIR "/opt/usr/home/owner/content/Documents/"
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
static const char* DEVICE_ID = "95c6572c-6373-41f4-9cba-daf39a38f59c";  //ring camera identification number can be consulted at: https://my.smartthings.com/location/45cf8542-65e8-41f7-b441-999486d15a8b/rooms
																		//Needs to log into the Samsung Developers Account where the device is registered to  see the deviceID.
// ---------- Generate logs in the UI ----------
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


static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = userdata;
    size_t new_len = m->len + size * nmemb;
    m->buf = realloc(m->buf, new_len + 1);
    memcpy(m->buf + m->len, ptr, size * nmemb);
    m->buf[new_len] = '\0';
    m->len = new_len;
    return size * nmemb;
}

//HTTPS REQUESTS TO SMARTTHINGS API
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

// ---------- TOKEN REFRESH FUNCTIONS ----------
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

//Writes on the file token.txt to update for fresh values
static bool write_kv_file(const char *path, token_data_t *t) {
    FILE *fp = fopen(path, "w");
    if (!fp) return false;
    fprintf(fp,"client_id=%s\nclient_secret=%s\nrefresh_token=%s\naccess_token=%s\nexpires_in=%s\n",
        t->client_id, t->client_secret, t->refresh_token, t->access_token, t->expires_in);
    fclose(fp);
    log_event("token.txt updated successfully.");
    return true;
}

static bool refresh_token_c(token_data_t *t) {
    log_event("Performing SmartThings token refresh...");
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
    if(res!=CURLE_OK){ log_event("CURL refresh failed."); free(m.buf); return false; }

    cJSON *json=cJSON_Parse(m.buf);
    if(!json){ log_event("JSON parse failed."); free(m.buf); return false; }
    const cJSON *acc=cJSON_GetObjectItem(json,"access_token");
    const cJSON *ref=cJSON_GetObjectItem(json,"refresh_token");
    if(acc&&acc->valuestring) strncpy(t->access_token,acc->valuestring,sizeof(t->access_token));
    if(ref&&ref->valuestring) strncpy(t->refresh_token,ref->valuestring,sizeof(t->refresh_token));
    cJSON_Delete(json); free(m.buf);
    log_event("Token refreshed successfully.");
    return true;
}


// ---------- TOKEN VALIDATION ----------
static bool validate_access_token(const char *token, const char *device_id) {
    if (!token || strlen(token) < 10) return false;

    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, device_id);
    char *resp = http_get(url, token);
    if (!resp) return false;

    bool valid = strstr(resp, "components") != NULL || strstr(resp, "status") != NULL;
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

    ui_log_append(ad, "Checking for token.txt...");

    // 1️⃣ If token.txt exists in permanent directory
    if (stat(TOKEN_FILE, &st) == 0) {
        ui_log_append(ad, "Found existing token.txt in permanent directory.");

        if (!read_kv_file(TOKEN_FILE, &t)) {
            ui_log_append(ad, "Failed to read token.txt contents.");
            return false;
        }

        ui_log_append(ad, "Verifying access token validity...");
        if (validate_access_token(t.access_token, DEVICE_ID)) {
            ui_log_append(ad, "Access token is valid.");
            ACCESS_TOKEN = strdup(t.access_token);
            return true;
        }

        ui_log_append(ad, "Access token invalid. Attempting refresh...");
        if (refresh_token_c(&t)) {
            if (write_kv_file(TOKEN_FILE, &t)) {
                ACCESS_TOKEN = strdup(t.access_token);
                ui_log_append(ad, "Token refreshed and saved successfully.");
                return true;
            } else {
                ui_log_append(ad, "Failed to save refreshed token.");
                return false;
            }
        } else {
            ui_log_append(ad, "Token refresh failed.");
            return false;
        }
    }

    // 2️⃣ If token.txt does NOT exist → copy from res, do NOT refresh
    ui_log_append(ad, "No token.txt found. Copying from /res...");

    FILE *src = fopen(res_token, "r");
    if (!src) {
        ui_log_append(ad, " Missing token.txt in resources.");
        return false;
    }

    FILE *dst = fopen(TOKEN_FILE, "w");
    if (!dst) {
        fclose(src);
        ui_log_append(ad, "Failed to create token.txt in permanent folder.");
        return false;
    }

    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), src)) > 0)
        fwrite(buf, 1, n, dst);
    fclose(src);
    fclose(dst);

    ui_log_append(ad, "token.txt copied from resources (no refresh performed).");

    // Optionally load into memory for ACCESS_TOKEN use later
    if (read_kv_file(TOKEN_FILE, &t)) {
        ACCESS_TOKEN = strdup(t.access_token);
        ui_log_append(ad, "Loaded copied access token for future validation.");
    }

    return true;
}

//END OF TAKEN REFRESH METHODS//

//IMAGE CAPTURE METHODS//

#define SAVE_FOLDER "/opt/usr/home/owner/content/Pictures/"

// --- Generate timestamp for naming captures ---
static void current_timestamp(char *buf, size_t size) {
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    strftime(buf, size, "%Y%m%d_%H%M%S", t);
}

//for Base64 conversion
static unsigned char* readImageToBytes(const char* filePath, size_t* size) {
    FILE* f = fopen(filePath, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    *size = sz;
    unsigned char* buf = malloc(sz);
    if (!buf) { fclose(f); return NULL; }
    fread(buf, 1, sz, f);
    fclose(f);
    return buf;
}


static char* encode_base64(const unsigned char* data, size_t len, size_t* outlen) {
    static const char tbl[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    char* out = malloc(4 * ((len + 2) / 3) + 1);
    if (!out) return NULL;
    size_t i, j;
    for (i = 0, j = 0; i < len;) {
        uint32_t a = i < len ? data[i++] : 0;
        uint32_t b = i < len ? data[i++] : 0;
        uint32_t c = i < len ? data[i++] : 0;
        uint32_t t = (a << 16) | (b << 8) | c;
        out[j++] = tbl[(t >> 18) & 63];
        out[j++] = tbl[(t >> 12) & 63];
        out[j++] = (i > len + 1) ? '=' : tbl[(t >> 6) & 63];
        out[j++] = (i > len) ? '=' : tbl[t & 63];
    }
    out[j] = '\0';
    *outlen = j;
    return out;
}


static bool http_download_file_smart(const char *url, const char *token, const char *save_path) {
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


static void take_image_capture(appdata_s *ad) {
    if (!ACCESS_TOKEN) {
        ui_log_append(ad, "No valid ACCESS_TOKEN.");
        return;
    }

    char timestamp[64];
    current_timestamp(timestamp, sizeof(timestamp));

    char img_path[512];
    snprintf(img_path, sizeof(img_path), "%scapture_%s.jpg", SAVE_FOLDER, timestamp);

    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);

    // 1️) Refresh (sends a refresh command to the API, to refresh)
    ui_log_append(ad, "Sending refresh command...");
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";
    char *r1 = http_post(url, ACCESS_TOKEN, payload_refresh);
    if (!r1) ui_log_append(ad, "Failed to send refresh command.");
    free(r1);
    sleep(5);

    // 2️) Trigger image capture (send the 'take' command of the imageCaptures)
    ui_log_append(ad, "Triggering image capture...");
    const char payload_take[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    char *r2 = http_post(url, ACCESS_TOKEN, payload_take);
    free(r2);
    sleep(5);

    // 3️) Fetch status for image URL
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    ui_log_append(ad, "Fetching latest device status...");
    char *status = http_get(url, ACCESS_TOKEN);
    if (!status) { ui_log_append(ad, "Failed to fetch device status."); return; }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "No image URL found in status response.");
        free(status);
        return;
    }

    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    // 4️) Download new image
    /*ui_log_append(ad, "⬇️ Downloading captured image...");
    if (!http_download_file_smart(image_url, ACCESS_TOKEN, img_path)) {
        ui_log_append(ad, "Failed to download image.");
        return;
    }*/
    ui_log_append(ad, "Downloading captured image...");
    http_download_file_smart(image_url, ACCESS_TOKEN, img_path);


    // 5️) Display the image in UI,
    elm_image_file_set(ad->img_view, img_path, NULL);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
    evas_object_show(ad->img_view);

    char msg[512];
    snprintf(msg, sizeof(msg), "Image saved: %s", img_path);
    ui_log_append(ad, msg);

    // 6️) Base64 encode
    size_t img_size = 0;
    unsigned char *img_data = readImageToBytes(img_path, &img_size);
    if (!img_data) { ui_log_append(ad, "Failed to read image."); return; }

    size_t out_len = 0;
    char *base64 = encode_base64(img_data, img_size, &out_len);
    free(img_data);
    if (!base64) { ui_log_append(ad, "Base64 encoding failed."); return; }

    // 7️) Save base64 file, saving the file is done for debugging purposes.
    char txt_path[512];
    snprintf(txt_path, sizeof(txt_path), "%sbase64_%s.txt", SAVE_FOLDER, timestamp);
    FILE *txt = fopen(txt_path, "w");
    if (txt) {
        fwrite(base64, 1, out_len, txt);
        fclose(txt);
        ui_log_append(ad, "Base64 file saved.");
    }

    // 8️) Create prompt_<timestamp>.json (prompt to send to the evaluation pipeline through websockets)
    //Notes: the 'method' and 'id' values are sample values, this could change based on the Model being used for vlm evaluation.
    //The prompt used is in the 'params' field of the JSON.
    cJSON *json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "method", "generate_from_image");
    cJSON *params = cJSON_CreateArray();
    cJSON_AddItemToArray(params, cJSON_CreateString(
        "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
        "<|im_start|>user\n<image> Analyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\n"
        "Answer Yes or No.<|im_end|>\n"
        "<|im_start|>assistant\n"));
    cJSON_AddItemToArray(params, cJSON_CreateString(base64));
    cJSON_AddItemToObject(json, "params", params);
    cJSON_AddNumberToObject(json, "id", 42);

    char *json_str = cJSON_Print(json);
    if (json_str) {
        char json_path[512];
        snprintf(json_path, sizeof(json_path), "%sprompt_%s.json", SAVE_FOLDER, timestamp);
        FILE *jf = fopen(json_path, "w");
        if (jf) {
            fprintf(jf, "%s", json_str);
            fclose(jf);
            ui_log_append(ad, "prompt.json created.");
        }
        free(json_str);
    }
    cJSON_Delete(json);
    free(base64);
}


static Eina_Bool live_loop_cb(void *data) {
    appdata_s *ad = data;
    if (!ad->live_running) return ECORE_CALLBACK_CANCEL;
    take_image_capture(ad);
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



static void capture_once_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    ui_log_append(ad, "Capturing single image...");
    take_image_capture(ad);
}


static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (!ACCESS_TOKEN) { ui_log_append(ad, "No ACCESS_TOKEN."); return; }
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);
    ui_log_append(ad, "Fetching device capabilities...");
    char *resp = http_get(url, ACCESS_TOKEN);
    if (resp) {
        ui_log_append(ad, "<b>Capabilities:</b>");
        ui_log_append(ad, resp);
        free(resp);
    } else {
        ui_log_append(ad, "Failed to fetch capabilities.");
    }
}

// ------------------------------


static void create_base_gui(appdata_s *ad) {

    // Window
    ad->win = elm_win_util_standard_add("ST_LIVE","SmartThings Live Capture");
    elm_win_autodel_set(ad->win, EINA_TRUE);
    evas_object_color_set(ad->win, 200,200,200,255);

    // Conformant
    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // Main vertical container
    ad->box = elm_box_add(ad->conform);
    elm_box_horizontal_set(ad->box, EINA_FALSE);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);



    Evas_Object *button_row = elm_box_add(ad->box);
    elm_box_horizontal_set(button_row, EINA_TRUE);

    // Make the row fixed height
    evas_object_size_hint_weight_set(button_row, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(button_row, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, button_row);
    evas_object_show(button_row);

    // BUTTON: Show Capabilities
    Evas_Object *btn_caps = elm_button_add(button_row);
    elm_object_text_set(btn_caps, "Show Capabilities");
    evas_object_smart_callback_add(btn_caps,"clicked",show_caps_clicked,ad);
    evas_object_size_hint_weight_set(btn_caps, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_caps, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(button_row, btn_caps);
    evas_object_show(btn_caps);

    // BUTTON: Capture Once
    Evas_Object *btn_once = elm_button_add(button_row);
    elm_object_text_set(btn_once, "Capture Once");
    evas_object_smart_callback_add(btn_once,"clicked",capture_once_clicked,ad);
    evas_object_size_hint_weight_set(btn_once, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_once, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(button_row, btn_once);
    evas_object_show(btn_once);

    // BUTTON: Start Live Capture
    Evas_Object *btn_live = elm_button_add(button_row);
    elm_object_text_set(btn_live, "Start Live Capture");
    evas_object_smart_callback_add(btn_live,"clicked",live_clicked,ad);
    evas_object_size_hint_weight_set(btn_live, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(btn_live, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(button_row, btn_live);
    evas_object_show(btn_live);


    ad->img_view = elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);

    // Make image the largest area (weight 4)
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, 6.0);
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, ad->img_view);
    evas_object_hide(ad->img_view);  // until first capture

    Evas_Object *scroller = elm_scroller_add(ad->box);
    elm_scroller_policy_set(scroller, ELM_SCROLLER_POLICY_AUTO, ELM_SCROLLER_POLICY_AUTO);

    // Medium amount of space (weight 2)
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, 2.0);
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, scroller);
    evas_object_show(scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Initializing SmartThings app...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);


    ad->entry_output = elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_output, EINA_TRUE);
    elm_entry_editable_set(ad->entry_output, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_output, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_output, "Model Output:");

    // Smallest space (weight 1)
    evas_object_size_hint_weight_set(ad->entry_output, EVAS_HINT_EXPAND, 1.0);
    evas_object_size_hint_align_set(ad->entry_output, EVAS_HINT_FILL, EVAS_HINT_FILL);

    elm_box_pack_end(ad->box, ad->entry_output);
    evas_object_show(ad->entry_output);


    evas_object_show(ad->win);
}

static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    create_base_gui(ad);
    ui_log_append(ad,"Initializing SmartThings Token System...");
    if(initialize_token_file(ad))
        ui_log_append(ad,"Token system ready.");
    else ui_log_append(ad,"Token initialization failed.");
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
