#pragma once
#include <Elementary.h>
#include <curl/curl.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static inline Eina_Bool is_back_key(const char *keyname) {
  return keyname && (!strcmp(keyname,"XF86Back") || !strcmp(keyname,"Back") || !strcmp(keyname,"Escape"));
}

/* Simple growing buffer for CURL writes */
typedef struct {
  char *data;
  size_t len;
} dynbuf;

static inline void dynbuf_init(dynbuf *b) { b->data = NULL; b->len = 0; }

static size_t curl_write_cb(char *ptr, size_t size, size_t nmemb, void *userdata) {
  size_t total = size * nmemb;
  dynbuf *b = (dynbuf *)userdata;
  char *p = realloc(b->data, b->len + total + 1);
  if (!p) return 0;
  b->data = p;
  memcpy(b->data + b->len, ptr, total);
  b->len += total;
  b->data[b->len] = '\0';
  return total;
}
