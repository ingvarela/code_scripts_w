// ---------- TOKEN VALIDATION ----------
static bool validate_access_token(const char *token, const char *device_id) {
    if (!token || strlen(token) < 10) return false;

    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, device_id);
    char *resp = http_get(url, token);
    if (!resp) return false;

    bool valid = strstr(resp, "components") != NULL || strstr(resp, "status") != NULL;
    free(resp);
    return valid;
}