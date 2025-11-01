static bool app_create(void *data) {
    appdata_s *ad = data;
    ad->live_running = false;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    ensure_save_folder();

    // ---------- TOKEN INIT ----------
    const char *data_path = app_get_data_path();
    char token_file[512];
    snprintf(token_file, sizeof(token_file), "%stokens.txt", data_path);

    if (access(token_file, F_OK) != 0) {  // no tokens yet
        const char *auth_code = "iMqPEd";  // your 6-digit one-time code
        const char *redirect  = "https://httpbin.org/get";

        ui_log_append(ad, "Exchanging authorization code for tokens...");
        if (exchange_authorization_code(auth_code, CLIENT_ID, CLIENT_SECRET,
                                        redirect, ACCESS_TOKEN, REFRESH_TOKEN)) {
            FILE *fp = fopen(token_file, "w");
            if (fp) {
                fprintf(fp, "%s\n%s\n", ACCESS_TOKEN, REFRESH_TOKEN);
                fclose(fp);
            }
            ui_log_append(ad, "Initial tokens obtained and saved.");
        } else {
            ui_log_append(ad, "Failed to exchange authorization code.");
        }
    } else {
        ui_log_append(ad, "Existing tokens found; will refresh as needed.");
    }
    // ---------- END TOKEN INIT ----------

    create_base_gui(ad);
    return true;
}