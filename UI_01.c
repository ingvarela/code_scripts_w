// Tizen 9.0 Native (EFL) — ultra-minimal URL → Image loader
// Single-file main.c. UI = Entry + Button + Image. No camera.
// Privileges: http://tizen.org/privilege/internet  (and mediastorage if you keep saving to file)
// Build: link with -lcurl

#include <app.h>
#include <Elementary.h>
#include <dlog.h>
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h> // PATH_MAX

#define LOG_TAG "url_img_min"
#define DEFAULT_URL "https://upload.wikimedia.org/wikipedia/commons/3/3f/Fronalpstock_big.jpg"

typedef struct {
    Evas_Object *win, *box, *entry, *btn, *img;
    char *data_path;
} App;

// --- tiny cURL helper ---
static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *stream) {
    return fwrite(ptr, size, nmemb, (FILE*)stream);
}
static int download(const char *url, const char *path) {
    CURL *c = curl_easy_init(); if (!c) return 0;
    FILE *f = fopen(path, "wb"); if (!f) { curl_easy_cleanup(c); return 0; }
    curl_easy_setopt(c, CURLOPT_URL, url);
    curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, f);
    curl_easy_setopt(c, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 30L);
    // For demo simplicity: skip SSL verification (use proper CA in production)
    curl_easy_setopt(c, CURLOPT_SSL_VERIFYPEER, 0L);
    curl_easy_setopt(c, CURLOPT_SSL_VERIFYHOST, 0L);
    int ok = (curl_easy_perform(c) == CURLE_OK);
    fclose(f); curl_easy_cleanup(c);
    if (!ok) remove(path);
    return ok;
}

// --- UI callbacks ---
static void on_load(void *data, Evas_Object *obj, void *ev) {
    (void)obj; (void)ev; App *a = data;
    const char *markup = elm_entry_entry_get(a->entry); // Entry returns markup
    char *url_utf8 = elm_entry_markup_to_utf8(markup ? markup : "");
    const char *url = (url_utf8 && *url_utf8) ? url_utf8 : DEFAULT_URL;

    char path[PATH_MAX]; snprintf(path, sizeof(path), "%simg.jpg", a->data_path);
    if (download(url, path)) {
        if (!elm_image_file_set(a->img, path, NULL)) {
            dlog_print(DLOG_ERROR, LOG_TAG, "elm_image_file_set failed for %s", path);
        } else {
            evas_object_show(a->img);
        }
    } else {
        dlog_print(DLOG_ERROR, LOG_TAG, "download failed: %s", url);
    }
    if (url_utf8) free(url_utf8);
}

// --- UI setup ---
static void ui_build(App *a) {
    a->win = elm_win_util_standard_add("u", "URL → Image");
    elm_win_autodel_set(a->win, EINA_TRUE);

    a->box = elm_box_add(a->win);
    evas_object_size_hint_weight_set(a->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(a->win, a->box);
    evas_object_show(a->box);

    a->entry = elm_entry_add(a->box);
    elm_entry_single_line_set(a->entry, EINA_TRUE);
    elm_entry_entry_set(a->entry, DEFAULT_URL);
    evas_object_size_hint_weight_set(a->entry, EVAS_HINT_EXPAND, 0);
    evas_object_size_hint_align_set(a->entry, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(a->box, a->entry);
    evas_object_show(a->entry);

    a->btn = elm_button_add(a->box);
    elm_object_text_set(a->btn, "Load");
    evas_object_smart_callback_add(a->btn, "clicked", on_load, a);
    elm_box_pack_end(a->box, a->btn);
    evas_object_show(a->btn);

    a->img = elm_image_add(a->box);
    elm_image_resizable_set(a->img, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(a->img, EINA_TRUE);
    evas_object_size_hint_weight_set(a->img, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(a->img, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(a->box, a->img);
    evas_object_show(a->img);

    evas_object_resize(a->win, 720, 1280);
    evas_object_show(a->win);
}

// --- Lifecycle ---
static bool app_create(void *data) {
    App *a = data; a->data_path = app_get_data_path(); ui_build(a); return true;
}
static void app_terminate(void *data) { App *a = data; if (a->data_path) free(a->data_path); }
static void noop(app_event_info_h e, void *u) {(void)e;(void)u;}

int main(int argc, char *argv[]) {
    App a = {0}; ui_app_lifecycle_callback_s cb = {0};
    cb.create = app_create; cb.terminate = app_terminate;
    app_event_handler_h h1,h2,h3,h4,h5;
    ui_app_add_event_handler(&h1, APP_EVENT_LOW_MEMORY, noop, NULL);
    ui_app_add_event_handler(&h2, APP_EVENT_LOW_BATTERY, noop, NULL);
    ui_app_add_event_handler(&h3, APP_EVENT_LANGUAGE_CHANGED, noop, NULL);
    ui_app_add_event_handler(&h4, APP_EVENT_REGION_FORMAT_CHANGED, noop, NULL);
    ui_app_add_event_handler(&h5, APP_EVENT_DEVICE_ORIENTATION_CHANGED, noop, NULL);
    int r = ui_app_main(argc, argv, &cb, &a);
    if (r != APP_ERROR_NONE) dlog_print(DLOG_ERROR, LOG_TAG, "ui_app_main failed: %d", r);
    return r;
}
