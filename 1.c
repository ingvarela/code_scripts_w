typedef struct {
    char client_id[256];
    char client_secret[256];
    char refresh_token[1024];
    char access_token[4096];
    bool loaded;
} TokenData;

static TokenData TOKENS;

/* ----- internal helpers ----- */

static void token_load(TokenData *t) {
    if (t->loaded) return;
    memset(t, 0, sizeof(TokenData));
    const char *path = app_get_data_path();
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "r");
    if (!fp) return;
    char key[256], value[4096];
    while (fscanf(fp, "%255[^=]=%4095s\n", key, value) == 2) {
        if (strcmp(key, "client_id") == 0) strcpy(t->client_id, value);
        else if (strcmp(key, "client_secret") == 0) strcpy(t->client_secret, value);
        else if (strcmp(key, "refresh_token") == 0) strcpy(t->refresh_token, value);
        else if (strcmp(key, "access_token") == 0) strcpy(t->access_token, value);
    }
    fclose(fp);
    t->loaded = true;
}

static void token_save(TokenData *t) {
    const char *path = app_get_data_path();
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "w");
    if (!fp) return;
    fprintf(fp, "client_id=%s\n", t->client_id);
    fprintf(fp, "client_secret=%s\n", t->client_secret);
    fprintf(fp, "refresh_token=%s\n", t->refresh_token);
    fprintf(fp, "access_token=%s\n", t->access_token);
    fclose(fp);
}

/* POST to SmartThings OAuth endpoint and parse new tokens */
static bool token_request(TokenData *t, const char *body) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    curl_easy_setopt(curl, CURLOPT_URL, "https://auth-global.api.smartthings.com/oauth/token");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    if (res != CURLE_OK || !m.buf) { free(m.buf); return false; }
    char *acc = strstr(m.buf, "\"access_token\"");
    char *ref = strstr(m.buf, "\"refresh_token\"");
    if (acc) sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", t->access_token);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%1023[^\"]\"", t->refresh_token);
    free(m.buf);
    token_save(t);
    return strlen(t->access_token) > 0;
}

/* Refresh flow */
static bool token_refresh(TokenData *t) {
    char body[2048];
    snprintf(body, sizeof(body),
        "grant_type=refresh_token&client_id=%s&client_secret=%s&refresh_token=%s",
        t->client_id, t->client_secret, t->refresh_token);
    return token_request(t, body);
}

/* First-time authorization_code flow */
static bool token_exchange_code(TokenData *t, const char *code, const char *redirect_uri) {
    char body[2048];
    snprintf(body, sizeof(body),
        "grant_type=authorization_code&client_id=%s&client_secret=%s&code=%s&redirect_uri=%s",
        t->client_id, t->client_secret, code, redirect_uri);
    return token_request(t, body);
}

/* ----- single public entry point ----- */
static const char* get_valid_access_token(appdata_s *ad, const char *auth_code, const char *redirect_uri) {
    token_load(&TOKENS);

    if (strlen(TOKENS.access_token) == 0) {
        ui_log_append(ad, "No access token — attempting first exchange...");
        if (token_exchange_code(&TOKENS, auth_code, redirect_uri))
            ui_log_append(ad, "Access token obtained from authorization code.");
        else
            ui_log_append(ad, "Authorization code exchange failed.");
    }
    return TOKENS.access_token;
}