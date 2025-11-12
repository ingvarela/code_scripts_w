static bool http_download_file_smart(const char *url, const char *token, const char *save_path) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;
    FILE *fp = fopen(save_path, "wb");
    if (!fp) { curl_easy_cleanup(curl); return false; }

    struct curl_slist *headers = NULL;
    bool needs_auth = true;

    // Detect signed URLs (S3, Azure, SmartThings CDN)
    if (strstr(url, "X-Amz-") || strstr(url, "?token=") || strstr(url, "sig=") || strstr(url, "aws")) {
        needs_auth = false;
    }

    if (needs_auth && token) {
        char auth[512];
        snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
        headers = curl_slist_append(headers, auth);
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);   // follow redirect if needed
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, NULL);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, fp);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);

    if (headers)
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

    CURLcode res = curl_easy_perform(curl);

    if (headers) curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    fclose(fp);

    if (res != CURLE_OK) {
        remove(save_path); // delete corrupted file
        return false;
    }

    return true;
}