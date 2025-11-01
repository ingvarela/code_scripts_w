// Exchange a one-time SmartThings authorization code for access + refresh tokens
static bool exchange_authorization_code(const char *code,
                                        const char *client_id,
                                        const char *client_secret,
                                        const char *redirect_uri,
                                        char *access_out,
                                        char *refresh_out) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    mem_t m = { .buf = calloc(1,1), .len = 0 };
    char post_fields[2048];
    snprintf(post_fields, sizeof(post_fields),
        "grant_type=authorization_code&client_id=%s&client_secret=%s&code=%s&redirect_uri=%s",
        client_id, client_secret, code, redirect_uri);

    curl_easy_setopt(curl, CURLOPT_URL, "https://auth-global.api.smartthings.com/oauth/token");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_fields);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || !m.buf) { free(m.buf); return false; }

    // Simple parsing (avoid external JSON lib)
    char *acc = strstr(m.buf, "\"access_token\"");
    char *ref = strstr(m.buf, "\"refresh_token\"");
    if (acc) sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", access_out);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%1023[^\"]\"", refresh_out);
    free(m.buf);

    return strlen(access_out) > 0;
}