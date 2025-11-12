// ------------------------------------------------------
//  Check if token.txt exists in data path
// ------------------------------------------------------
static bool token_file_exists_in_data(void) {
    const char *data_dir = app_get_data_path();
    char token_path[512];
    snprintf(token_path, sizeof(token_path), "%stoken.txt", data_dir);
    struct stat st;
    return (stat(token_path, &st) == 0);
}

// ------------------------------------------------------
//  Validate access token by calling a simple SmartThings GET
// ------------------------------------------------------
static bool validate_access_token(const char *token) {
    if (!token || strlen(token) < 10) return false;
    const char *test_device_endpoint = "https://api.smartthings.com/v1/devices";
    char *resp = http_get(test_device_endpoint, token);
    if (!resp) return false;

    bool valid = strstr(resp, "items") != NULL; // crude validation: look for valid response field
    free(resp);
    return valid;
}

// ------------------------------------------------------
//  Initialize token logic at startup
// ------------------------------------------------------
static bool initialize_token_file(appdata_s *ad) {
    const char *data_dir = app_get_data_path();
    const char *res_dir = app_get_resource_path();
    char data_token[512], res_token[512];
    snprintf(data_token, sizeof(data_token), "%stoken.txt", data_dir);
    snprintf(res_token, sizeof(res_token), "%stoken.txt", res_dir);

    token_data_t t = {0};

    // 1️⃣ If file exists in data path
    if (token_file_exists_in_data()) {
        ui_log_append(ad, "🔍 Found existing token.txt in data path.");
        if (!read_kv_file(data_token, &t)) {
            ui_log_append(ad, "⚠️ Failed to read existing token.txt — trying refresh.");
        } else if (validate_access_token(t.access_token)) {
            ui_log_append(ad, "✅ Access token is valid. Using existing token.");
            ACCESS_TOKEN = strdup(t.access_token);
            return true;
        } else {
            ui_log_append(ad, "🔁 Access token invalid or expired. Attempting refresh...");
            if (refresh_token_c(&t)) {
                write_kv_file(data_token, &t);
                ACCESS_TOKEN = strdup(t.access_token);
                ui_log_append(ad, "✅ Token refreshed successfully.");
                return true;
            } else {
                ui_log_append(ad, "❌ Failed to refresh token. Please verify credentials.");
                return false;
            }
        }
    }

    // 2️⃣ If no token.txt exists in data path → copy from res
    ui_log_append(ad, "📁 No token.txt found in data path. Copying from res...");
    FILE *src = fopen(res_token, "r");
    if (!src) {
        ui_log_append(ad, "❌ No token.txt found in res folder either!");
        return false;
    }

    FILE *dst = fopen(data_token, "w");
    if (!dst) {
        fclose(src);
        ui_log_append(ad, "❌ Failed to create token.txt in data path.");
        return false;
    }

    char buf[1024]; size_t n;
    while ((n = fread(buf, 1, sizeof(buf), src)) > 0)
        fwrite(buf, 1, n, dst);
    fclose(src); fclose(dst);
    ui_log_append(ad, "✅ token.txt copied from res → data.");

    // After copying, try refreshing immediately
    if (read_kv_file(data_token, &t) && refresh_token_c(&t)) {
        write_kv_file(data_token, &t);
        ACCESS_TOKEN = strdup(t.access_token);
        ui_log_append(ad, "✅ Token refreshed successfully after copy.");
        return true;
    } else {
        ui_log_append(ad, "⚠️ Failed to refresh new token file.");
        return false;
    }
}