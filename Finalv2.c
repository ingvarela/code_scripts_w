// ---------- SIMPLE TOKEN STRUCT (ONLY access_token + device_id) ----------
typedef struct {
    char access_token[1024];
    char device_id[256];
} token_data_t;


// ---------- read_kv_file (ONLY reads access_token and device_id) ----------
static bool read_kv_file(const char *path, token_data_t *t) {
    FILE *fp = fopen(path, "r");
    if (!fp) return false;

    char line[512];

    while (fgets(line, sizeof(line), fp)) {
        char *eq = strchr(line, '=');
        if (!eq) continue;

        *eq = '\0';

        char *key = line;
        char *val = eq + 1;

        // Remove CR/LF
        val[strcspn(val, "\r\n")] = '\0';

        if (strcmp(key, "access_token") == 0)
            strncpy(t->access_token, val, sizeof(t->access_token));

        else if (strcmp(key, "device_id") == 0)
            strncpy(t->device_id, val, sizeof(t->device_id));
    }

    fclose(fp);
    return true;
}


// ---------- ensure_token_dir_exists (unchanged) ----------
static void ensure_token_dir_exists(void) {
    struct stat st = {0};
    if (stat(TOKEN_DIR, &st) == -1)
        mkdir(TOKEN_DIR, 0777);
}


// ---------- initialize_token_file (NO REFRESH, ONLY LOAD VALUES) ----------
static bool initialize_token_file(appdata_s *ad) {
    ensure_token_dir_exists();

    const char *res_dir = app_get_resource_path();
    char res_token[512];
    snprintf(res_token, sizeof(res_token), "%stoken.txt", res_dir);

    token_data_t t = {0};
    struct stat st;

    ui_log_append(ad, "Checking for token.txt...");

    // --- CASE 1: token.txt already exists in writable directory ---
    if (stat(TOKEN_FILE, &st) == 0) {
        ui_log_append(ad, "Found token.txt in permanent directory.");

        if (!read_kv_file(TOKEN_FILE, &t)) {
            ui_log_append(ad, "Failed to read token.txt.");
            return false;
        }

        // Set globals
        ACCESS_TOKEN = strdup(t.access_token);
        DEVICE_ID    = strdup(t.device_id);

        ui_log_append(ad, "Loaded access token + device ID.");
        return true;
    }

    // --- CASE 2: No token.txt → copy from resources ---
    ui_log_append(ad, "token.txt not found. Copying from /res...");

    FILE *src = fopen(res_token, "r");
    if (!src) {
        ui_log_append(ad, "Missing token.txt in /res folder.");
        return false;
    }

    FILE *dst = fopen(TOKEN_FILE, "w");
    if (!dst) {
        fclose(src);
        ui_log_append(ad, "Failed to create token.txt in writable folder.");
        return false;
    }

    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), src)) > 0)
        fwrite(buf, 1, n, dst);

    fclose(src);
    fclose(dst);

    ui_log_append(ad, "token.txt copied from /res.");

    // Load copied token
    if (!read_kv_file(TOKEN_FILE, &t)) {
        ui_log_append(ad, "Failed to read newly copied token.txt.");
        return false;
    }

    ACCESS_TOKEN = strdup(t.access_token);
    DEVICE_ID    = strdup(t.device_id);

    ui_log_append(ad, "Loaded access token + device ID.");

    return true;
}