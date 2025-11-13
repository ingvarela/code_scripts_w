//--------------------------------------------------------------
// 9) SEND TO LOCAL VLM SERVER (192.168.50.108:9090/generate)
//--------------------------------------------------------------

ui_log_append(ad, "📡 Sending prompt to local VLM server...");

// -- Build the query string like Node.js --
const char *vlm_query =
    "<|im_start|>system\n"
    "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>\n"
    "<|im_start|>user\n"
    "<image>\n"
    "Describe the objects in the room in a few sentences.<|im_end|>\n"
    "<|im_start|>assistant\n";

// -- Build JSON payload --
cJSON *vlm_json = cJSON_CreateObject();
cJSON_AddStringToObject(vlm_json, "purpose", "vlm");
cJSON_AddStringToObject(vlm_json, "query", vlm_query);
cJSON_AddStringToObject(vlm_json, "image", base64);
cJSON_AddNumberToObject(vlm_json, "reqid", 0);

char *vlm_payload = cJSON_PrintUnformatted(vlm_json);
cJSON_Delete(vlm_json);

// ---------------- HTTP POST ----------------
CURL *curl_vlm = curl_easy_init();
if (!curl_vlm) {
    ui_log_append(ad, "❌ CURL init failed for VLM request.");
    free(vlm_payload);
    return;
}

mem_t vlm_resp = { .buf = calloc(1,1), .len = 0 };
struct curl_slist *vlm_hdr = NULL;
vlm_hdr = curl_slist_append(vlm_hdr, "Content-Type: application/json");

curl_easy_setopt(curl_vlm, CURLOPT_URL, "http://192.168.50.108:9090/generate");
curl_easy_setopt(curl_vlm, CURLOPT_HTTPHEADER, vlm_hdr);
curl_easy_setopt(curl_vlm, CURLOPT_POSTFIELDS, vlm_payload);
curl_easy_setopt(curl_vlm, CURLOPT_WRITEFUNCTION, write_cb);
curl_easy_setopt(curl_vlm, CURLOPT_WRITEDATA, &vlm_resp);

CURLcode vlm_res = curl_easy_perform(curl_vlm);
curl_easy_cleanup(curl_vlm);
curl_slist_free_all(vlm_hdr);
free(vlm_payload);

if (vlm_res != CURLE_OK) {
    ui_log_append(ad, "❌ VLM request failed.");
    free(vlm_resp.buf);
    return;
}

// --------------------------------------------------------------
// 10) HANDLE RESPONSE
// --------------------------------------------------------------

ui_log_append(ad, "✅ VLM response received.");

char vlm_json_path[512];
snprintf(vlm_json_path, sizeof(vlm_json_path), "%sresponse_%s.json", SAVE_FOLDER, timestamp);

// Save response JSON
FILE *vlf = fopen(vlm_json_path, "w");
if (vlf) {
    fwrite(vlm_resp.buf, 1, vlm_resp.len, vlf);
    fclose(vlf);
}

// Show response in UI
ui_log_append(ad, "📄 Response saved. Parsing...");

cJSON *parsed = cJSON_Parse(vlm_resp.buf);
if (parsed) {
    char *pretty = cJSON_Print(parsed);
    ui_log_append(ad, pretty);
    free(pretty);
    cJSON_Delete(parsed);
} else {
    ui_log_append(ad, "⚠️ Response was not valid JSON.");
}

free(vlm_resp.buf);