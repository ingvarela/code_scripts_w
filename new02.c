static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);

    create_base_gui(ad);  // UI first for visible feedback
    ui_log_append(ad, "🚀 Initializing SmartThings Token System...");

    if (initialize_token_file(ad)) {
        ui_log_append(ad, "✅ Token system ready. SmartThings API available.");
    } else {
        ui_log_append(ad, "❌ Token initialization failed. Please check credentials or token.txt.");
    }

    return true;
}