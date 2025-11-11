static void take_image_capture(appdata_s *ad, const char *save_path) {
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);

    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";

    if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
        printf("Failed to send refresh command.\n");
    }

    sleep(5); // Wait for the refresh command to be processed

    // Step 2: Send the image capture command
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    free(http_post(url, ACCESS_TOKEN, payload));

    sleep(5); // Wait for SmartThings to process capture

    // Step 3: Fetch the device status to get the image URL
    snprintf(url, sizeof(url), "%s/devices/%s/status", API_BASE, DEVICE_ID);
    char *status = http_get(url, ACCESS_TOKEN);
    if (!status) {
        ui_log_append(ad, "Failed to fetch device status.");
        return;
    }

    char *found = strstr(status, "https://");
    if (!found) {
        ui_log_append(ad, "No image URL found in status.");
        free(status);
        return;
    }

    char image_url[512];
    sscanf(found, "%511[^\"]", image_url);
    free(status);

    // Step 4: Download the captured image
    ui_log_append(ad, "Downloading captured image...");
    if (http_download_file(image_url, ACCESS_TOKEN, save_path)) {
        ui_log_append(ad, "Image updated.");
        elm_image_file_set(ad->img_view, save_path, NULL);
        evas_object_show(ad->img_view);

        // Log the full path where the image is saved
        char log_message[512];
        snprintf(log_message, sizeof(log_message), "Image saved at: %s", save_path);
        ui_log_append(ad, log_message);

        // Step 5: Read the image file and encode it in Base64
        size_t image_size;
        unsigned char* image_data = readImageToBytes(save_path, &image_size);
        if (image_data) {
            size_t output_length;
            char* base64_encoded = encode_base64(image_data, image_size, &output_length);
            if (base64_encoded) {
                ui_log_append(ad, "Base64 encoded image:");
                //ui_log_append(ad, base64_encoded);


                // Step 6: Save the Base64-encoded string to a .txt file
                char txt_path[512];
                snprintf(txt_path, sizeof(txt_path), "%s/base64_img.txt", save_path);
                FILE *txt_file = fopen(txt_path, "w");
                if (txt_file) {
                    fprintf(txt_file, "%s", base64_encoded);
                    fclose(txt_file);
                    ui_log_append(ad, "Base64 encoded image saved to base64_img.txt");
                } else {
                    ui_log_append(ad, "Failed to create base64_img.txt");
                }

                // Step 6: Save the Base64-encoded string to a .txt file
                /*char txt_path[512];
                snprintf(txt_path, sizeof(txt_path), "%s/base64_img.txt", save_path);

                // Open the file in write mode
                FILE *txt_file = fopen(txt_path, "w");
                if (txt_file) {
                    // Write the Base64-encoded string directly to the file
                    fwrite(base64_encoded, 1, output_length, txt_file);
                    fclose(txt_file);

                    // Log success after closing the file
                    ui_log_append(ad, "Base64 encoded image saved to base64_img.txt");
                } else {
                    // Log error if file creation fails
                    ui_log_append(ad, "Failed to create base64_img.txt");
                }*/

                // Step 7: Create and save the prompt.json file using cjson
                cJSON *json = cJSON_CreateObject();
                if (json) {
                    cJSON_AddStringToObject(json, "method", "generate_from_image");
                    cJSON *params = cJSON_CreateArray();
                    cJSON_AddItemToArray(params, cJSON_CreateString("<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n<image> Please identify the layout of the keyboard on the screen. Return the result as a comma separated string with elements from each row.<|im_end|>\n<|im_start|>assistant\n"));
                    cJSON_AddItemToArray(params, cJSON_CreateString(base64_encoded));
                    cJSON_AddItemToObject(json, "params", params);
                    cJSON_AddNumberToObject(json, "id", 42);
                    char *json_string = cJSON_Print(json);
                    if (json_string) {
                    	char json_path[512];
                    	snprintf(json_path, sizeof(json_path), "%s/prompt.json", save_path);
                    	FILE *json_file = fopen(json_path, "w");
                    	if (json_file) {
                    		fprintf(json_file, "%s", json_string);
                    		fclose(json_file);
                    		ui_log_append(ad, "prompt.json created successfully.");
                    	} else {
                    		ui_log_append(ad, "Failed to create prompt.json.");
                    	}
                    	free(json_string);
                    } else {
                    	ui_log_append(ad, "Failed to print JSON object.");
                    }
                    cJSON_Delete(json);
                	}
                else {
                	ui_log_append(ad, "Failed to create JSON object.");
                                                    }




                // Free the Base64-encoded string
                free(base64_encoded);
            } else {
                ui_log_append(ad, "Failed to encode image data to Base64.");
            }

            // Free the image data
            free(image_data);
        } else {
            ui_log_append(ad, "Failed to read image data.");
        }
    } else {
        ui_log_append(ad, "Failed to download image.");
    }

    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");

    if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
        printf("Failed to send refresh command.\n");
    }

    sleep(3); // Wait for the refresh command to be processed
}
