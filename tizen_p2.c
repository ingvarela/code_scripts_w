static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_save_folder();

    load_tokens(&TOKENS);

    // If tokens are empty, obtain the first pair with an authorization code
    if (strlen(TOKENS.access_token) == 0 || strlen(TOKENS.refresh_token) == 0) {
        const char *redirect_uri = "https://httpbin.org/get";
        const char *auth_code = "YOUR_6_DIGIT_CODE"; // one-time SmartThings code

        ui_log_append(ad, "Obtaining initial tokens...");
        if (exchange_authorization_code(auth_code, &TOKENS, redirect_uri))
            ui_log_append(ad, "Initial tokens obtained and saved.");
        else
            ui_log_append(ad, "Authorization code exchange failed.");
    } else {
        ui_log_append(ad, "Tokens loaded; will refresh automatically.");
    }

    create_base_gui(ad);
    return true;
}