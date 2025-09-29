#include "st_app.h"
#include <system_info.h>
#include <download.h>
#include <samsung_account.h>

#define DOWNLOAD_IMAGE_PATH "/opt/usr/media/Downloads/capture.jpg"

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *image_box;
    Evas_Object *url_entry;
    Evas_Object *account_status_label;
    Evas_Object *device_info_label;
    download_h download;
    samsung_account_h account_handle;
} appdata_s;

static void _load_device_info_cb(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;

    // Simulated API response for visual preview
    const char *raw = "<font_size=26><color=#000000>{\n    \"status\": \"connected\",\n    \"motion\": true,\n    \"camera\": true\n}</color></font_size>";
    elm_object_text_set(ad->device_info_label, raw);

    // Update status field
    elm_object_text_set(ad->account_status_label, "<align=left><font_size=26><color=#27ae60>Status: Device Info Loaded</color></font_size></align>");
}

static void create_base_gui(appdata_s *ad) {
    ad->win = elm_win_util_standard_add(PACKAGE, PACKAGE);
    elm_win_autodel_set(ad->win, EINA_TRUE);

    if (elm_win_wm_rotation_supported_get(ad->win)) {
        int rots[4] = {0, 90, 180, 270};
        elm_win_wm_rotation_available_rotations_set(ad->win, rots, 4);
    }

    evas_object_smart_callback_add(ad->win, "delete,request", NULL, NULL);
    eext_object_event_callback_add(ad->win, EEXT_CALLBACK_BACK, NULL, ad);

    ad->conform = elm_conformant_add(ad->win);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    Evas_Object *box = elm_box_add(ad->conform);
    elm_box_padding_set(box, 0, 10);
    evas_object_size_hint_weight_set(box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, box);
    evas_object_show(box);

    // === Title ===
    Evas_Object *title = elm_label_add(box);
    elm_object_text_set(title, "<align=center><font_size=40><color=#2e86de><b>Smart Thing Client</b></color></font_size></align>");
    elm_box_pack_end(box, title);
    evas_object_show(title);

    // === Device ID ===
    Evas_Object *dev_id = elm_label_add(box);
    char *device_id = NULL;
    system_info_get_platform_string("http://tizen.org/system/tizenid", &device_id);
    if (device_id) {
        char buf[256];
        snprintf(buf, sizeof(buf), "<align=left><font_size=28><color=#000000><b>Device ID:</b> %s</color></font_size></align>", device_id);
        elm_object_text_set(dev_id, buf);
        free(device_id);
    } else {
        elm_object_text_set(dev_id, "<align=left><font_size=28><color=#999999>Device ID: Unknown</color></font_size></align>");
    }
    elm_box_pack_end(box, dev_id);
    evas_object_show(dev_id);

    // === Connect Samsung Account ===
    Evas_Object *sa_btn = elm_button_add(box);
    elm_object_text_set(sa_btn, "<font_size=28><color=#3498db>Connect Samsung Account</color></font_size>");
    elm_box_pack_end(box, sa_btn);
    evas_object_show(sa_btn);

    // === Load Device Info Button ===
    Evas_Object *load_info_btn = elm_button_add(box);
    elm_object_text_set(load_info_btn, "<font_size=28><color=#27ae60>Load Device Info</color></font_size>");
    evas_object_smart_callback_add(load_info_btn, "clicked", _load_device_info_cb, ad);
    elm_box_pack_end(box, load_info_btn);
    evas_object_show(load_info_btn);

    // === Capabilities (Multiline Entry) ===
    Evas_Object *api_label = elm_label_add(box);
    elm_object_text_set(api_label, "<align=left><font_size=28><color=#444444><b>Capabilities:</b></color></font_size></align>");
    elm_box_pack_end(box, api_label);
    evas_object_show(api_label);

    Evas_Object *api_entry = elm_entry_add(box);
    elm_entry_editable_set(api_entry, EINA_FALSE);
    elm_entry_scrollable_set(api_entry, EINA_TRUE);
    elm_entry_line_wrap_set(api_entry, ELM_WRAP_CHAR);
    evas_object_size_hint_weight_set(api_entry, EVAS_HINT_EXPAND, 0.3);
    evas_object_size_hint_align_set(api_entry, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_object_text_set(api_entry, "<font_size=26><color=#888888>Awaiting data...</color></font_size>");
    elm_box_pack_end(box, api_entry);
    evas_object_show(api_entry);
    ad->device_info_label = api_entry;

    // === Status Label ===
    ad->account_status_label = elm_label_add(box);
    elm_object_text_set(ad->account_status_label, "<align=left><font_size=26><color=#888888>Status: Ready</color></font_size></align>");
    elm_box_pack_end(box, ad->account_status_label);
    evas_object_show(ad->account_status_label);

    // === Image Placeholder ===
    ad->image_box = elm_image_add(box);
    elm_image_file_set(ad->image_box, "/opt/usr/apps/org.example.st_app/res/images/placeholder.png", NULL);
    evas_object_size_hint_weight_set(ad->image_box, EVAS_HINT_EXPAND, 0.4);
    evas_object_size_hint_align_set(ad->image_box, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(box, ad->image_box);
    evas_object_show(ad->image_box);
}

static bool app_create(void *data) {
    appdata_s *ad = data;
    create_base_gui(ad);
    return true;
}

int main(int argc, char *argv[]) {
    appdata_s ad = {0,};
    ui_app_lifecycle_callback_s cb = {0,};
    cb.create = app_create;
    return ui_app_main(argc, argv, &cb, &ad);
}
