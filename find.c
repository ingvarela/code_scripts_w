// =====================================================
// ADDITION — Base64 encoding, prompt.json, and preview
// =====================================================

// Center image preview in the middle of the window
evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL);
evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE);
evas_object_show(ad->img_view);
ui_log_append(ad, "🖼️ Image preview displayed in the center of the screen.");

// Read image file for Base64 conversion
size_t image_size = 0;
unsigned char* image_data = readImageToBytes(save_path, &image_size);
if (image_data) {
    size_t output_length = 0;
    char* base64_encoded = encode_base64(image_data, image_size, &output_length);
    if (base64_encoded) {
        // Save Base64 to text file
        char base_dir[512];
        strcpy(base_dir, save_path);
        char *slash = strrchr(base_dir, '/');
        if (slash) *slash = '\0'; // Trim to directory

        char txt_path[512];
        snprintf(txt_path, sizeof(txt_path), "%s/base64_img.txt", base_dir);
        FILE *txt_file = fopen(txt_path, "w");
        if (txt_file) {
            fwrite(base64_encoded, 1, output_length, txt_file);
            fclose(txt_file);
            ui_log_append(ad, "💾 Base64-encoded image saved to base64_img.txt");
        } else {
            ui_log_append(ad, "⚠️ Failed to create base64_img.txt");
        }

        // Create prompt.json with the encoded image
        cJSON *json = cJSON_CreateObject();
        if (json) {
            cJSON_AddStringToObject(json, "method", "generate_from_image");
            cJSON *params = cJSON_CreateArray();
            cJSON_AddItemToArray(params, cJSON_CreateString(
                "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
                "<|im_start|>user\n<image> Please identify the layout of the keyboard "
                "on the screen. Return the result as a comma-separated string with "
                "elements from each row.<|im_end|>\n<|im_start|>assistant\n"
            ));
            cJSON_AddItemToArray(params, cJSON_CreateString(base64_encoded));
            cJSON_AddItemToObject(json, "params", params);
            cJSON_AddNumberToObject(json, "id", 42);

            char *json_string = cJSON_Print(json);
            if (json_string) {
                char json_path[512];
                snprintf(json_path, sizeof(json_path), "%s/prompt.json", base_dir);
                FILE *json_file = fopen(json_path, "w");
                if (json_file) {
                    fprintf(json_file, "%s", json_string);
                    fclose(json_file);
                    ui_log_append(ad, "✅ prompt.json created successfully.");
                } else {
                    ui_log_append(ad, "❌ Failed to create prompt.json file.");
                }
                free(json_string);
            } else {
                ui_log_append(ad, "⚠️ Failed to serialize JSON object.");
            }
            cJSON_Delete(json);
        } else {
            ui_log_append(ad, "❌ Failed to create JSON object.");
        }

        free(base64_encoded);
    } else {
        ui_log_append(ad, "Failed to encode image data to Base64.");
    }

    free(image_data);
} else {
    ui_log_append(ad, "Failed to read image data for Base64 conversion.");
}