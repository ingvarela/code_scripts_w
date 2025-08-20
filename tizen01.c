// Tizen Native (EFL) single-file sample: camera capture button + load image from URL into an Elm_Image // - UI: Window -> Box (vertical) //   [Entry: URL] [Button: Load URL] [Image widget] //   [Button: Capture Photo] // - Networking: uses libcurl to download the image to app data, then sets elm_image file. // - Camera: provides a minimal capture flow behind a feature flag. If your target supports camera, //           define USE_TIZEN_CAMERA and add the proper privileges in tizen-manifest. // // Build notes: //   * In your Tizen Studio Native project, add this file as src/main.c (or similar). //   * Project should be a Native UI (C) app using EFL/Elementary. //   * Enable libcurl in your project (Project -> Properties -> C/C++ Build -> Settings -> Linker add -lcurl) //   * Privileges: internet (for URL), mediastorage (if saving), externalstorage (optional), camera (if using camera) //       http://tizen.org/privilege/internet //       http://tizen.org/privilege/mediastorage //       http://tizen.org/privilege/externalstorage.read (optional) //       http://tizen.org/privilege/externalstorage.write (optional) //       http://tizen.org/privilege/camera (if USE_TIZEN_CAMERA) // // Manifest features (if using camera): //   <feature name="http://tizen.org/feature/camera" required="false"/> // // Tested conceptually for Tizen 7–9 APIs; minor function name mismatches may need adjustment per your SDK.

#include <app.h> #include <Elementary.h> #include <efl_extension.h> #include <dlog.h> #include <stdlib.h> #include <stdio.h> #include <string.h> #include <unistd.h> #include <curl/curl.h>

#ifdef USE_TIZEN_CAMERA #include <camera.h> #endif

#define LOG_TAG "efl_cam_url"

typedef struct appdata { Evas_Object *win; Evas_Object *conform; Evas_Object *box; Evas_Object *url_entry; Evas_Object *load_btn; Evas_Object *image; Evas_Object *capture_btn; Evas_Object *status; char        *data_path; #ifdef USE_TIZEN_CAMERA camera_h     cam; #endif } appdata_s;

// ----------- Small helpers ----------- static void status_set(appdata_s *ad, const char *fmt, ...) { if (!ad || !ad->status) return; char buf[512]; va_list ap; va_start(ap, fmt); vsnprintf(buf, sizeof(buf), fmt, ap); va_end(ap); elm_object_text_set(ad->status, buf); }

static void toast(appdata_s *ad, const char *msg) { dlog_print(DLOG_INFO, LOG_TAG, "%s", msg); status_set(ad, "%s", msg); }

// ----------- cURL download ----------- struct dl_buf { FILE *fp; };

static size_t write_file_cb(void *contents, size_t size, size_t nmemb, void *userp) { struct dl_buf ctx = (struct dl_buf)userp; return fwrite(contents, size, nmemb, ctx->fp); }

static Eina_Bool download_to_file(const char *url, const char *dst_path, char *errbuf, size_t errlen) { CURL *curl = NULL; CURLcode res; struct dl_buf ctx = {0}; Eina_Bool ok = EINA_FALSE;

curl = curl_easy_init();
if (!curl) { snprintf(errbuf, errlen, "curl init failed"); return EINA_FALSE; }

ctx.fp = fopen(dst_path, "wb");
if (!ctx.fp) { snprintf(errbuf, errlen, "cannot open %s", dst_path); curl_easy_cleanup(curl); return EINA_FALSE; }

curl_easy_setopt(curl, CURLOPT_URL, url);
curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_file_cb);
curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);
curl_easy_setopt(curl, CURLOPT_USERAGENT, "tizen-efl-sample/1.0");
curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);

res = curl_easy_perform(curl);
if (res == CURLE_OK) {
    long http_code = 0; curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
    if (http_code >= 200 && http_code < 300) {
        ok = EINA_TRUE;
    } else {
        snprintf(errbuf, errlen, "HTTP %ld", http_code);
    }
} else {
    snprintf(errbuf, errlen, "%s", curl_easy_strerror(res));
}

fclose(ctx.fp);
curl_easy_cleanup(curl);

if (!ok) unlink(dst_path);
return ok;

}

// ----------- UI Callbacks ----------- static void on_load_url_clicked(void *data, Evas_Object *obj, void *event_info) { appdata_s ad = (appdata_s)data; (void)obj; (void)event_info; const char *url = elm_object_text_get(ad->url_entry); if (!url || !*url) { toast(ad, "Please enter an image URL."); return; }

char path[PATH_MAX];
snprintf(path, sizeof(path), "%simage_download.jpg", ad->data_path);

char err[256] = {0};
toast(ad, "Downloading…");
if (download_to_file(url, path, err, sizeof(err))) {
    // Set file to the Elm_Image
    if (!elm_image_file_set(ad->image, path, NULL)) {
        toast(ad, "Failed to load image file.");
    } else {
        evas_object_show(ad->image);
        toast(ad, "Loaded: %s", url);
    }
} else {
    toast(ad, "Download failed: %s", err);
}

}

#ifdef USE_TIZEN_CAMERA // ---- Camera helpers (minimal flow) ---- static bool camera_supported() { bool supported = false; system_info_get_platform_bool("http://tizen.org/feature/camera", &supported); return supported; }

static int camera_init(appdata_s *ad) { int r; if (!camera_supported()) return -1;

r = camera_create(CAMERA_DEVICE_CAMERA0, &ad->cam);
if (r != CAMERA_ERROR_NONE) return r;

// Optional: attach preview to an evas object (new rectangle placeholder)
// Here we keep it simple and skip embedding preview; we can still capture.

r = camera_start_preview(ad->cam);
return r;

}

static void capture_completed_cb(camera_image_data_s *image, void *user_data) { appdata_s ad = (appdata_s)user_data; if (!image || !image->data || image->size <= 0) { toast(ad, "Capture failed."); return; }

// Persist to file under app data
char path[PATH_MAX];
snprintf(path, sizeof(path), "%scapture.jpg", ad->data_path);
FILE *fp = fopen(path, "wb");
if (!fp) { toast(ad, "Save failed."); return; }
fwrite(image->data, 1, image->size, fp);
fclose(fp);

// Display captured image
if (!elm_image_file_set(ad->image, path, NULL)) {
    toast(ad, "Failed to show capture.");
} else {
    evas_object_show(ad->image);
    toast(ad, "Photo captured.");
}

}

static void on_capture_clicked(void *data, Evas_Object *obj, void *event_info) { appdata_s ad = (appdata_s)data; (void)obj; (void)event_info;

if (!ad->cam) {
    if (camera_init(ad) != CAMERA_ERROR_NONE) {
        toast(ad, "Camera init failed or not supported.");
        return;
    }
}

// Single-shot capture to memory, then our callback saves & shows it.
if (camera_capture(ad->cam, capture_completed_cb, ad) != CAMERA_ERROR_NONE) {
    toast(ad, "Capture API failed.");
} else {
    toast(ad, "Capturing…");
}

} #else static void on_capture_clicked(void *data, Evas_Object *obj, void *event_info) { appdata_s ad = (appdata_s)data; (void)obj; (void)event_info; toast(ad, "Camera disabled in this build. Define USE_TIZEN_CAMERA and add privileges."); } #endif

// ----------- UI Setup ----------- static Evas_Object* create_button(Evas_Object *parent, const char *label, Evas_Smart_Cb cb, void *data) { Evas_Object *btn = elm_button_add(parent); elm_object_text_set(btn, label); evas_object_smart_callback_add(btn, "clicked", cb, data); evas_object_size_hint_weight_set(btn, EVAS_HINT_EXPAND, 0); evas_object_size_hint_align_set(btn, EVAS_HINT_FILL, 0.5); evas_object_show(btn); return btn; }

static void create_base_gui(appdata_s *ad) { // Window ad->win = elm_win_util_standard_add("cam-url", "Camera + URL Image"); elm_win_autodel_set(ad->win, EINA_TRUE);

// Conformant
ad->conform = elm_conformant_add(ad->win);
evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
elm_win_resize_object_add(ad->win, ad->conform);
evas_object_show(ad->conform);

// Box
ad->box = elm_box_add(ad->conform);
elm_box_padding_set(ad->box, 0, 8);
evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
evas_object_size_hint_align_set(ad->box, EVAS_HINT_FILL, EVAS_HINT_FILL);
elm_object_content_set(ad->conform, ad->box);
evas_object_show(ad->box);

// URL Entry + Load Button (row)
Evas_Object *hbox = elm_box_add(ad->box);
elm_box_horizontal_set(hbox, EINA_TRUE);
evas_object_size_hint_weight_set(hbox, EVAS_HINT_EXPAND, 0);
evas_object_size_hint_align_set(hbox, EVAS_HINT_FILL, 0.5);
elm_box_pack_end(ad->box, hbox);
evas_object_show(hbox);

ad->url_entry = elm_entry_add(hbox);
elm_entry_single_line_set(ad->url_entry, EINA_TRUE);
elm_object_part_text_set(ad->url_entry, "guide", "https://example.com/image.jpg");
evas_object_size_hint_weight_set(ad->url_entry, EVAS_HINT_EXPAND, 0);
evas_object_size_hint_align_set(ad->url_entry, EVAS_HINT_FILL, 0.5);
evas_object_size_hint_min_set(ad->url_entry, 0, 80);
elm_box_pack_end(hbox, ad->url_entry);
evas_object_show(ad->url_entry);

ad->load_btn = create_button(hbox, "Load URL", on_load_url_clicked, ad);

// Image display
ad->image = elm_image_add(ad->box);
elm_image_resizable_set(ad->image, EINA_TRUE, EINA_TRUE);
elm_image_aspect_fixed_set(ad->image, EINA_TRUE);
evas_object_size_hint_weight_set(ad->image, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
evas_object_size_hint_align_set(ad->image, EVAS_HINT_FILL, EVAS_HINT_FILL);
elm_box_pack_end(ad->box, ad->image);
evas_object_show(ad->image);

// Capture button
ad->capture_btn = create_button(ad->box, "Capture Photo", on_capture_clicked, ad);

// Status label
ad->status = elm_label_add(ad->box);
elm_object_text_set(ad->status, "Ready.");
evas_object_size_hint_weight_set(ad->status, EVAS_HINT_EXPAND, 0);
evas_object_size_hint_align_set(ad->status, 0.0, 0.5);
elm_box_pack_end(ad->box, ad->status);
evas_object_show(ad->status);

evas_object_resize(ad->win, 720, 1280);
evas_object_show(ad->win);

}

// ----------- App lifecycle ----------- static bool app_create(void *data) { appdata_s ad = (appdata_s)data; ad->data_path = app_get_data_path(); create_base_gui(ad); return true; }

static void app_control(app_control_h app_control, void *data) { (void)app_control; (void)data; }

static void app_pause(void *data) { (void)data; }

static void app_resume(void *data) { (void)data; }

static void app_terminate(void *data) { appdata_s ad = (appdata_s)data; #ifdef USE_TIZEN_CAMERA if (ad->cam) { camera_stop_preview(ad->cam); camera_destroy(ad->cam); ad->cam = NULL; } #endif if (ad->data_path) free(ad->data_path); }

static void ui_app_lang_changed(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; elm_language_set("en_US"); }

static void ui_app_orient_changed(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; }

static void ui_app_region_changed(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; }

static void ui_app_low_memory(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; }

static void ui_app_low_battery(app_event_info_h event_info, void *user_data) { (void)event_info; (void)user_data; }

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

