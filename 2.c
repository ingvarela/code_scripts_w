static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_save_folder();

    const char *redirect_uri = "https://httpbin.org/get";
    const char *auth_code = "YOUR_6_DIGIT_CODE";  // only used first run

    const char *token = get_valid_access_token(ad, auth_code, redirect_uri);
    if (strlen(token) > 0)
        ui_log_append(ad, "Token system initialized; API ready.");
    else
        ui_log_append(ad, "Token initialization failed.");

    create_base_gui(ad);
    return true;
}