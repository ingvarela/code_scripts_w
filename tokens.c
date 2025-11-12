static bool initialize_token_file(appdata_s *ad) {
    ensure_token_dir_exists();

    const char *res_dir = app_get_resource_path();
    char res_token[512];
    snprintf(res_token, sizeof(res_token), "%stoken.txt", res_dir);

    token_data_t t = {0};
    struct stat st;

    ui_log_append(ad, "🔍 Checking for token.txt...");

    // 1️⃣ If token.txt exists in permanent directory
    if (stat(TOKEN_FILE, &st) == 0) {
        ui_log_append(ad, "📄 Found existing token.txt in permanent directory.");

        if (!read_kv_file(TOKEN_FILE, &t)) {
            ui_log_append(ad, "⚠️ Failed to read token.txt contents.");
            return false;
        }

        ui_log_append(ad, "🔐 Verifying access token validity...");
        if (validate_access_token(t.access_token, DEVICE_ID)) {
            ui_log_append(ad, "✅ Access token is valid.");
            ACCESS_TOKEN = strdup(t.access_token);
            return true;
        }

        ui_log_append(ad, "⚠️ Access token invalid. Attempting refresh...");
        if (refresh_token_c(&t)) {
            if (write_kv_file(TOKEN_FILE, &t)) {
                ACCESS_TOKEN = strdup(t.access_token);
                ui_log_append(ad, "✅ Token refreshed and saved successfully.");
                return true;
            } else {
                ui_log_append(ad, "❌ Failed to save refreshed token.");
                return false;
            }
        } else {
            ui_log_append(ad, "❌ Token refresh failed.");
            return false;
        }
    }

    // 2️⃣ If token.txt does NOT exist → copy from res, do NOT refresh
    ui_log_append(ad, "📁 No token.txt found. Copying from /res...");

    FILE *src = fopen(res_token, "r");
    if (!src) {
        ui_log_append(ad, "❌ Missing token.txt in resources.");
        return false;
    }

    FILE *dst = fopen(TOKEN_FILE, "w");
    if (!dst) {
        fclose(src);
        ui_log_append(ad, "❌ Failed to create token.txt in permanent folder.");
        return false;
    }

    char buf[1024];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), src)) > 0)
        fwrite(buf, 1, n, dst);
    fclose(src);
    fclose(dst);

    ui_log_append(ad, "✅ token.txt copied from resources (no refresh performed).");

    // Optionally load into memory for ACCESS_TOKEN use later
    if (read_kv_file(TOKEN_FILE, &t)) {
        ACCESS_TOKEN = strdup(t.access_token);
        ui_log_append(ad, "ℹ️ Loaded copied access token for future validation.");
    }

    return true;
}