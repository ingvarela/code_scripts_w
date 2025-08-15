#include "app.h"

typedef struct appdata_s {
  Evas_Object *win, *bg, *root;

  Evas_Object *url_entry;
  Evas_Object *method_sel;
  Evas_Object *headers_entry;
  Evas_Object *body_entry;
  Evas_Object *send_btn;
  Evas_Object *status_lbl;
  Evas_Object *resp_entry;

  Ecore_Thread *worker;
} appdata;

/* ----- Helpers ----- */

static const char* current_method_get(Evas_Object *hoversel) {
  const char *txt = elm_object_text_get(hoversel);
  return txt ? txt : "GET";
}

static struct curl_slist* build_headers_from_text(const char *multi) {
  if (!multi || !*multi) return NULL;
  struct curl_slist *list = NULL;
  const char *p = multi, *line;
  char buf[2048];

  while (*p) {
    /* read until \n */
    line = p;
    const char *nl = strchr(p, '\n');
    size_t n = nl ? (size_t)(nl - p) : strlen(p);
    /* trim CR and spaces */
    while (n && (line[n-1] == '\r' || line[n-1] == ' ')) n--;
    size_t m = n < sizeof(buf)-1 ? n : sizeof(buf)-1;
    memcpy(buf, line, m); buf[m] = 0;

    if (m > 0) list = curl_slist_append(list, buf);
    p = nl ? nl + 1 : p + n;
  }
  return list;
}

typedef struct {
  char *url;
  char *method;
  char *headers_text;
  char *body;
  long http_code;
  char *resp;
  char  err[CURL_ERROR_SIZE];
} job;

static void free_job(job *j) {
  if (!j) return;
  free(j->url);
  free(j->method);
  free(j->headers_text);
  free(j->body);
  free(j->resp);
  free(j);
}

/* ----- Networking (runs in background thread) ----- */

static void worker_do(void *data, Ecore_Thread *th) {
  job *j = (job*)data;
  CURL *curl = curl_easy_init();
  dynbuf buf; dynbuf_init(&buf);
  j->err[0] = 0;

  if (!curl) {
    snprintf(j->err, sizeof(j->err), "curl_easy_init failed");
    return;
  }

  curl_easy_setopt(curl, CURLOPT_URL, j->url);
  curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
  curl_easy_setopt(curl, CURLOPT_USERAGENT, "TV-API-Tester/1.0");
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, curl_write_cb);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &buf);
  curl_easy_setopt(curl, CURLOPT_ERRORBUFFER, j->err);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);

  /* TLS okay on most TVs; disable only if you test self-signed endpoints
     curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
     curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
  */

  struct curl_slist *headers = build_headers_from_text(j->headers_text);
  if (headers) curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

  /* Method */
  if (!strcasecmp(j->method,"GET")) {
    /* default */
  } else if (!strcasecmp(j->method,"POST")) {
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    if (j->body && *j->body) curl_easy_setopt(curl, CURLOPT_POSTFIELDS, j->body);
  } else if (!strcasecmp(j->method,"PUT")) {
    curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "PUT");
    if (j->body && *j->body) curl_easy_setopt(curl, CURLOPT_POSTFIELDS, j->body);
  } else if (!strcasecmp(j->method,"PATCH")) {
    curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "PATCH");
    if (j->body && *j->body) curl_easy_setopt(curl, CURLOPT_POSTFIELDS, j->body);
  } else if (!strcasecmp(j->method,"DELETE")) {
    curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "DELETE");
    if (j->body && *j->body) curl_easy_setopt(curl, CURLOPT_POSTFIELDS, j->body);
  } else {
    curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, j->method);
  }

  CURLcode rc = curl_easy_perform(curl);
  if (rc != CURLE_OK) {
    if (!j->err[0]) snprintf(j->err, sizeof(j->err), "curl error: %s", curl_easy_strerror(rc));
  } else {
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &j->http_code);
    j->resp = buf.data; /* take ownership */
    buf.data = NULL;
  }

  if (headers) curl_slist_free_all(headers);
  if (buf.data) free(buf.data);
  curl_easy_cleanup(curl);

  (void)th;
}

static void worker_end(void *data, Ecore_Thread *th) {
  job *j = (job*)data;
  appdata *ad = ecore_thread_global_data_find("ad");
  if (!ad) { free_job(j); return; }

  char status[256];
  if (j->err[0]) {
    snprintf(status, sizeof(status), "Error: %s", j->err);
    elm_object_text_set(ad->status_lbl, status);
    elm_object_text_set(ad->resp_entry, j->err);
  } else {
    snprintf(status, sizeof(status), "HTTP %ld", j->http_code);
    elm_object_text_set(ad->status_lbl, status);
    elm_object_text_set(ad->resp_entry, j->resp ? j->resp : "(empty)");
  }

  elm_object_disabled_set(ad->send_btn, EINA_FALSE);
  ad->worker = NULL;

  free_job(j);
  (void)th;
}

static void worker_cancel(void *data, Ecore_Thread *th) {
  /* If you add cancellation, update UI here. */
  job *j = (job*)data;
  free_job(j);
  (void)th;
}

/* ----- UI callbacks ----- */

static void send_clicked_cb(void *data, Evas_Object *obj, void *event_info) {
  appdata *ad = (appdata*)data;
  if (ad->worker) return; /* already running */

  const char *url = elm_object_text_get(ad->url_entry);
  if (!url || !*url) {
    elm_object_text_set(ad->status_lbl, "Please enter a URL.");
    return;
  }

  job *j = calloc(1, sizeof(job));
  j->url = strdup(url);
  j->method = strdup(current_method_get(ad->method_sel));
  j->headers_text = strdup(elm_object_text_get(ad->headers_entry) ?: "");
  j->body = strdup(elm_object_text_get(ad->body_entry) ?: "");

  elm_object_text_set(ad->status_lbl, "Sending...");
  elm_object_text_set(ad->resp_entry, "");
  elm_object_disabled_set(ad->send_btn, EINA_TRUE);

  /* Share appdata pointer via a global key for end callback */
  ecore_thread_global_data_add("ad", ad, NULL, EINA_TRUE);

  ad->worker = ecore_thread_run(worker_do, worker_end, worker_cancel, j);
  (void)obj; (void)event_info;
}

static void method_item_selected_cb(void *data, Evas_Object *obj, void *event_info) {
  (void)data; (void)obj; (void)event_info;
  /* The hoversel will update its label automatically */
}

static void keydown_cb(void *data, Evas *e, Evas_Object *obj, void *event_info) {
  (void)e; (void)obj;
  appdata *ad = (appdata*)data;
  Evas_Event_Key_Down *ev = (Evas_Event_Key_Down*)event_info;
  if (!ev || !ev->keyname) return;
  if (is_back_key(ev->keyname)) {
    if (ad->worker) ecore_thread_cancel(ad->worker);
    elm_exit();
  }
}

/* ----- UI build ----- */

static Evas_Object* titled_frame(Evas_Object *parent, const char *title) {
  Evas_Object *fr = elm_frame_add(parent);
  elm_object_text_set(fr, title);
  evas_object_size_hint_weight_set(fr, EVAS_HINT_EXPAND, 0.0);
  evas_object_size_hint_align_set(fr, EVAS_HINT_FILL, 0.0);
  evas_object_show(fr);
  return fr;
}

EAPI_MAIN int elm_main(int argc, char **argv) {
  (void)argc; (void)argv;
  curl_global_init(CURL_GLOBAL_DEFAULT);

  appdata ad = {0};

  /* Window */
  ad.win = elm_win_util_standard_add("tv-api-tester", "TV API Tester");
  elm_win_autodel_set(ad.win, EINA_TRUE);
  evas_object_smart_callback_add(ad.win, "delete,request", NULL, NULL);
  Evas *canvas = evas_object_evas_get(ad.win);
  evas_event_callback_add(canvas, EVAS_CALLBACK_KEY_DOWN, keydown_cb, &ad);

  /* Background */
  ad.bg = elm_bg_add(ad.win);
  elm_bg_color_set(ad.bg, 11, 19, 43);
  evas_object_size_hint_weight_set(ad.bg, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
  elm_win_resize_object_add(ad.win, ad.bg);
  evas_object_show(ad.bg);

  /* Root box (vertical) */
  ad.root = elm_box_add(ad.win);
  elm_box_padding_set(ad.root, 12, 12);
  evas_object_size_hint_weight_set(ad.root, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
  evas_object_size_hint_align_set(ad.root, EVAS_HINT_FILL, EVAS_HINT_FILL);
  elm_win_resize_object_add(ad.win, ad.root);
  evas_object_show(ad.root);

  /* URL + Method + Send row */
  Evas_Object *row = elm_box_add(ad.root);
  elm_box_horizontal_set(row, EINA_TRUE);
  elm_box_padding_set(row, 12, 0);
  evas_object_size_hint_weight_set(row, EVAS_HINT_EXPAND, 0.0);
  evas_object_size_hint_align_set(row, EVAS_HINT_FILL, 0.0);
  elm_box_pack_end(ad.root, row);
  evas_object_show(row);

  /* Method selector */
  ad.method_sel = elm_hoversel_add(row);
  elm_object_text_set(ad.method_sel, "GET");
  elm_hoversel_item_add(ad.method_sel, "GET", NULL, ELM_ICON_NONE, method_item_selected_cb, NULL);
  elm_hoversel_item_add(ad.method_sel, "POST", NULL, ELM_ICON_NONE, method_item_selected_cb, NULL);
  elm_hoversel_item_add(ad.method_sel, "PUT", NULL, ELM_ICON_NONE, method_item_selected_cb, NULL);
  elm_hoversel_item_add(ad.method_sel, "PATCH", NULL, ELM_ICON_NONE, method_item_selected_cb, NULL);
  elm_hoversel_item_add(ad.method_sel, "DELETE", NULL, ELM_ICON_NONE, method_item_selected_cb, NULL);
  evas_object_size_hint_weight_set(ad.method_sel, 0.0, 0.0);
  evas_object_size_hint_align_set(ad.method_sel, 0.0, 0.5);
  elm_box_pack_end(row, ad.method_sel);
  evas_object_show(ad.method_sel);

  /* URL entry */
  ad.url_entry = elm_entry_add(row);
  elm_entry_single_line_set(ad.url_entry, EINA_TRUE);
  elm_entry_scrollable_set(ad.url_entry, EINA_TRUE);
  elm_object_part_text_set(ad.url_entry, "guide", "https://postman-echo.com/get?foo=bar");
  elm_object_text_set(ad.url_entry, "https://postman-echo.com/get?foo=bar");
  evas_object_size_hint_weight_set(ad.url_entry, EVAS_HINT_EXPAND, 0.0);
  evas_object_size_hint_align_set(ad.url_entry, EVAS_HINT_FILL, 0.5);
  elm_box_pack_end(row, ad.url_entry);
  evas_object_show(ad.url_entry);

  /* Send button */
  ad.send_btn = elm_button_add(row);
  elm_object_text_set(ad.send_btn, "Send");
  evas_object_smart_callback_add(ad.send_btn, "clicked", send_clicked_cb, &ad);
  evas_object_size_hint_weight_set(ad.send_btn, 0.0, 0.0);
  evas_object_size_hint_align_set(ad.send_btn, 1.0, 0.5);
  elm_box_pack_end(row, ad.send_btn);
  evas_object_show(ad.send_btn);

  /* Headers frame + entry */
  Evas_Object *hdr_fr = titled_frame(ad.root, "Headers (one per line: Name: Value)");
  elm_box_pack_end(ad.root, hdr_fr);

  Evas_Object *hdr_entry = elm_entry_add(hdr_fr);
  elm_entry_scrollable_set(hdr_entry, EINA_TRUE);
  elm_entry_line_wrap_set(hdr_entry, ELM_WRAP_CHAR);
  elm_object_text_set(hdr_entry, "Content-Type: application/json\n");
  ad.headers_entry = hdr_entry;
  evas_object_size_hint_weight_set(hdr_entry, EVAS_HINT_EXPAND, 0.0);
  evas_object_size_hint_align_set(hdr_entry, EVAS_HINT_FILL, 0.0);
  elm_object_content_set(hdr_fr, hdr_entry);
  evas_object_show(hdr_entry);

  /* Body frame + entry */
  Evas_Object *body_fr = titled_frame(ad.root, "Body (for POST/PUT/PATCH)");
  elm_box_pack_end(ad.root, body_fr);

  ad.body_entry = elm_entry_add(body_fr);
  elm_entry_scrollable_set(ad.body_entry, EINA_TRUE);
  elm_entry_line_wrap_set(ad.body_entry, ELM_WRAP_CHAR);
  elm_object_text_set(ad.body_entry, "{\n  \"hello\": \"tv\"\n}\n");
  evas_object_size_hint_weight_set(ad.body_entry, EVAS_HINT_EXPAND, 0.0);
  evas_object_size_hint_align_set(ad.body_entry, EVAS_HINT_FILL, 0.0);
  elm_object_content_set(body_fr, ad.body_entry);
  evas_object_show(ad.body_entry);

  /* Status label */
  ad.status_lbl = elm_label_add(ad.root);
  elm_object_text_set(ad.status_lbl, "<align=left>Status: idle</align>");
  evas_object_size_hint_weight_set(ad.status_lbl, EVAS_HINT_EXPAND, 0.0);
  evas_object_size_hint_align_set(ad.status_lbl, EVAS_HINT_FILL, 0.0);
  elm_box_pack_end(ad.root, ad.status_lbl);
  evas_object_show(ad.status_lbl);

  /* Response frame + entry (read-only) */
  Evas_Object *resp_fr = titled_frame(ad.root, "Response");
  elm_box_pack_end(ad.root, resp_fr);

  ad.resp_entry = elm_entry_add(resp_fr);
  elm_entry_editable_set(ad.resp_entry, EINA_FALSE);
  elm_entry_scrollable_set(ad.resp_entry, EINA_TRUE);
  elm_entry_line_wrap_set(ad.resp_entry, ELM_WRAP_MIXED);
  elm_object_text_set(ad.resp_entry, "");
  evas_object_size_hint_weight_set(ad.resp_entry, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
  evas_object_size_hint_align_set(ad.resp_entry, EVAS_HINT_FILL, EVAS_HINT_FILL);
  elm_object_content_set(resp_fr, ad.resp_entry);
  evas_object_show(ad.resp_entry);

  /* Show */
  evas_object_resize(ad.win, 1920, 1080);
  evas_object_show(ad.win);

  elm_run();

  if (ad.worker) ecore_thread_cancel(ad.worker);
  curl_global_cleanup();
  return 0;
}
ELM_MAIN()
