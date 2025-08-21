// Tizen 9.0 Native (EFL) minimal sample // Simple UI with a picture box and a button to load an image from ANY URL. // No camera. Single-file main.c. // // Privileges (tizen-manifest.xml): //   http://tizen.org/privilege/internet //   http://tizen.org/privilege/mediastorage   (to save downloaded image under app data) // // Build: link libcurl (add -lcurl to the linker settings)

#include <app.h> #include <Elementary.h> #include <dlog.h> #include <curl/curl.h> #include <stdio.h> #include <stdlib.h> #include <string.h> #include <unistd.h>

#define LOG_TAG "efl_url_loader"

typedef struct appdata { Evas_Object *win; Evas_Object *conform; Evas_Object *vbox; Evas_Object *hbox; Evas_Object *entry; Evas_Object *button; Evas_Object *image; Evas_Object *status; char        *data_path; } appdata_s;

static void status_set(appdata_s *ad, const char *fmt, ...) { if (!ad || !ad->status) return; char buf[512]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap); elm_object_text_set(ad->status, buf); }

// ---- cURL download helpers ---- struct dl_buf { FILE *fp; }; static size_t write_file_cb(void *contents, size_t size, size_t nmemb, void *userp) { struct dl_buf ctx = (struct dl_buf)userp; return fwrite(contents, size, nmemb, ctx->fp); }

static Eina_Bool download_to_file(const char *url, const char *dst_path, char *errbuf, size_t errlen) { CURL *curl = curl_easy_init(); if (!curl) { snprintf(errbuf, errlen, "curl init failed"); return EINA_FALSE; }

struct dl_buf ctx = {0};
ctx.fp = fopen(dst_path, "wb");
if (!ctx.fp) { snprintf(errbuf, errlen, "cannot open %s", dst_path); curl_easy_cleanup(curl); return EINA_FALSE; }

curl_easy_setopt(curl, CURLOPT_URL, url);
curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_file_cb);
curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);
curl_easy_setopt(curl, CURLOPT_USERAGENT, "tizen-efl-url-loader/1.0");
curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);

CURLcode res = curl_easy_perform(curl);
int ok = 0;
if (res == CURLE_OK) {
    long http_code = 0; curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    ok = (http_code >= 200 && http_code < 300);
    if (!ok) snprintf(errbuf, errlen, "HTTP %ld", http_code);
} else {
    snprintf(errbuf, errlen, "%s", curl_easy_strerror(res));
}

fclose(ctx.fp);
curl_easy_cleanup(curl);

if (!ok) unlink(dst_path);
return ok ? EINA_TRUE : EINA_FALSE;

}

// ---- UI callbacks ---- static void on_load_clicked(void *data, Evas_Object *obj, void *event_info) { (void)obj; (void)event_info; appdata_s ad = (appdata_s)data; const char *url = elm_object_text_get(ad->entry); if (!url || !*url) { status_set(ad, "Enter an image URL and press Load."); return; }

// Save under app data path
char path[PATH_MAX];
snprintf(path, sizeof(path), "%sdownload.jpg", ad->data_path);

char err[256] = {0};
status_set(ad, "Downloading…");
if (download_to_file(url, path, err, sizeof(err))) {
    if (!elm_image_file_set(ad->image, path, NULL)) {
        status_set(ad, "Failed to display downloaded file.");
    } else {
        evas_object_show(ad->image);
        status_set(ad, "Loaded: %s", url);
    }
} else {
    status_set(ad, "Download failed: %s", err);
}

}

// ---- UI construction ---- static void create_base_gui(appdata_s *ad) { ad->win = elm_win_util_standard_add("url-loader", "URL Image Loader"); elm_win_autodel_set(ad->win, EINA_TRUE);

ad->conform = elm_conformant_add(ad->win);
evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
elm_win_resize_object_add(ad->win, ad->conform);
evas_object_show(ad->conform);

ad->vbox = elm_box_add(ad->conform);
elm_box_padding_set(ad->vbox, 0, 8);
evas_object_size_hint_weight_set(ad->vbox, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
evas_object_size_hint_align_set(ad->vbox, EVAS_HINT_FILL, EVAS_HINT_FILL);
elm_object_content_set(ad->conform, ad->vbox);
evas_object_show(ad->vbox);

// Row: Entry + Button
ad->hbox = elm_box_add(ad->vbox);
elm_box_horizontal_set(ad->hbox, EINA_TRUE);
evas_object_size_hint_weight_set(ad->hbox, EVAS_HINT_EXPAND, 0);
evas_object_size_hint_align_set(ad->hbox, EVAS_HINT_FILL, 0.5);
elm_box_pack_end(ad->vbox, ad->hbox);
evas_object_show(ad->hbox);

ad->entry = elm_entry_add(ad->hbox);
elm_entry_single_line_set(ad->entry, EINA_TRUE);
elm_object_part_text_set(ad->entry, "guide", "https://example.com/image.jpg");
evas_object_size_hint_weight_set(ad->entry, EVAS_HINT_EXPAND, 0);
evas_object_size_hint_align_set(ad->entry, EVAS_HINT_FILL, 0.5);
evas_object_size_hint_min_set(ad->entry, 0, 80);
elm_box_pack_end(ad->hbox, ad->entry);
evas_object_show(ad->entry);

ad->button = elm_button_add(ad->hbox);
elm_object_text_set(ad->button, "Load");
evas_object_smart_callback_add(ad->button, "clicked", on_load_clicked, ad);
evas_object_size_hint_weight_set(ad->button, 0, 0);
evas_object_size_hint_align_set(ad->button, 0.0, 0.5);
elm_box_pack_end(ad->hbox, ad->button);
evas_object_show(ad->button);

// Image area
ad->image = elm_image_add(ad->vbox);
elm_image_resizable_set(ad->image, EINA_TRUE, EINA_TRUE);
elm_image_aspect_fixed_set(ad->image, EINA_TRUE);
evas_object_size_hint_weight_set(ad->image, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
evas_object_size_hint_align_set(ad->image, EVAS_HINT_FILL, EVAS_HINT_FILL);
elm_box_pack_end(ad->vbox, ad->image);
evas_object_show(ad->image);

// Status
ad->status = elm_label_add(ad->vbox);
elm_object_text_set(ad->status, "Enter a URL and tap Load.");
evas_object_size_hint_weight_set(ad->status, EVAS_HINT_EXPAND, 0);
evas_object_size_hint_align_set(ad->status, 0.0, 0.5);
elm_box_pack_end(ad->vbox, ad->status);
evas_object_show(ad->status);

evas_object_resize(ad->win, 720, 1280);
evas_object_show(ad->win);

}

// ---- App lifecycle ---- static bool app_create(void *data) { appdata_s ad = (appdata_s)data; ad->data_path = app_get_data_path(); create_base_gui(ad); return true; }

static void app_control(app_control_h app_control, void *data) { (void)app_control; (void)data; } static void app_pause(void *data) { (void)data; } static void app_resume(void *data) { (void)data; } static void app_terminate(void *data) { appdata_s ad = (appdata_s)data; if (ad->data_path) free(ad->data_path); } static void ui_app_lang_changed(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; } static void ui_app_orient_changed(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; } static void ui_app_region_changed(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; } static void ui_app_low_memory(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; } static void ui_app_low_battery(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; }

int main(int argc, char *argv[]) { appdata_s ad = {0}; ui_app_lifecycle_callback_s event_callback = {0}; app_event_handler_h handlers[5] = {NULL,};

event_callback.create = app_create;
event_callback.terminate = app_terminate;
event_callback.pause = app_pause;
event_callback.resume = app_resume;
event_callback.app_control = app_control;

ui_app_add_event_handler(&handlers[APP_EVENT_LOW_MEMORY], APP_EVENT_LOW_MEMORY, ui_app_low_memory, &ad);
ui_app_add_event_handler(&handlers[APP_EVENT_LOW_BATTERY], APP_EVENT_LOW_BATTERY, ui_app_low_battery, &ad);
ui_app_add_event_handler(&handlers[APP_EVENT_LANGUAGE_CHANGED], APP_EVENT_LANGUAGE_CHANGED, ui_app_lang_changed, &ad);
ui_app_add_event_handler(&handlers[APP_EVENT_REGION_FORMAT_CHANGED], APP_EVENT_REGION_FORMAT_CHANGED, ui_app_region_changed, &ad);
ui_app_add_event_handler(&handlers[APP_EVENT_DEVICE_ORIENTATION_CHANGED], APP_EVENT_DEVICE_ORIENTATION_CHANGED, ui_app_orient_changed, &ad);

int ret = ui_app_main(argc, argv, &event_callback, &ad);
if (ret != APP_ERROR_NONE) {
    dlog_print(DLOG_ERROR, LOG_TAG, "ui_app_main() failed. err = %d", ret);
}
return ret;

}

