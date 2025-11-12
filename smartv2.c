static bool http_download_file_smart(const char *url, const char *token, const char *save_path) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;

    FILE *fp = fopen(save_path, "wb");
    if (!fp) {
        curl_easy_cleanup(curl);
        return false;
    }

    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);

    // Always use the same authentication logic as other SmartThings calls
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);  // handle redirects
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, NULL);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, fp);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);  // skip cert verify (Tizen TV)
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);

    CURLcode res = curl_easy_perform(curl);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    fclose(fp);

    if (res != CURLE_OK) {
        remove(save_path); // delete corrupted file
        return false;
    }

    return true;
}