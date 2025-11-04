typedef struct {
    char client_id[256];
    char client_secret[256];
    char refresh_token[1024];
    char access_token[4096];
} TokenData;

static TokenData TOKENS;

static void load_tokens(TokenData *toks) {
    memset(toks, 0, sizeof(TokenData));
    const char *path = app_get_data_path();
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "r");
    if (!fp) return;

    char key[256], value[4096];
    while (fscanf(fp, "%255[^=]=%4095s\n", key, value) == 2) {
        if (strcmp(key, "client_id") == 0) strcpy(toks->client_id, value);
        else if (strcmp(key, "client_secret") == 0) strcpy(toks->client_secret, value);
        else if (strcmp(key, "refresh_token") == 0) strcpy(toks->refresh_token, value);
        else if (strcmp(key, "access_token") == 0) strcpy(toks->access_token, value);
    }
    fclose(fp);
}

static void save_tokens(TokenData *toks) {
    const char *path = app_get_data_path();
    char file[512];
    snprintf(file, sizeof(file), "%stokens.txt", path);
    FILE *fp = fopen(file, "w");
    if (!fp) return;
    fprintf(fp, "client_id=%s\n", toks->client_id);
    fprintf(fp, "client_secret=%s\n", toks->client_secret);
    fprintf(fp, "refresh_token=%s\n", toks->refresh_token);
    fprintf(fp, "access_token=%s\n", toks->access_token);
    fclose(fp);
}

/* refresh_token(): exchanges a stored refresh token for a new access token */
static bool refresh_token(TokenData *toks) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    mem_t m = { .buf = calloc(1,1), .len = 0 };
    char post_fields[2048];
    snprintf(post_fields, sizeof(post_fields),
        "grant_type=refresh_token&client_id=%s&client_secret=%s&refresh_token=%s",
        toks->client_id, toks->client_secret, toks->refresh_token);

    curl_easy_setopt(curl, CURLOPT_URL, "https://auth-global.api.smartthings.com/oauth/token");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_fields);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || !m.buf) { free(m.buf); return false; }

    char *acc = strstr(m.buf, "\"access_token\"");
    char *ref = strstr(m.buf, "\"refresh_token\"");
    if (acc) sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", toks->access_token);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%1023[^\"]\"", toks->refresh_token);
    free(m.buf);

    if (strlen(toks->access_token) == 0) return false;
    save_tokens(toks);
    return true;
}

/* exchange_authorization_code(): only used on first run when no tokens yet */
static bool exchange_authorization_code(const char *code,
                                        TokenData *toks,
                                        const char *redirect_uri) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    mem_t m = { .buf = calloc(1,1), .len = 0 };
    char post_fields[2048];
    snprintf(post_fields, sizeof(post_fields),
        "grant_type=authorization_code&client_id=%s&client_secret=%s&code=%s&redirect_uri=%s",
        toks->client_id, toks->client_secret, code, redirect_uri);

    curl_easy_setopt(curl, CURLOPT_URL, "https://auth-global.api.smartthings.com/oauth/token");
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_fields);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);

    if (res != CURLE_OK || !m.buf) { free(m.buf); return false; }

    char *acc = strstr(m.buf, "\"access_token\"");
    char *ref = strstr(m.buf, "\"refresh_token\"");
    if (acc) sscanf(acc, "\"access_token\"%*[^:]:\"%4095[^\"]\"", toks->access_token);
    if (ref) sscanf(ref, "\"refresh_token\"%*[^:]:\"%1023[^\"]\"", toks->refresh_token);
    free(m.buf);

    save_tokens(toks);
    return strlen(toks->access_token) > 0;
}