#include "st_rest.h"
//#include "base64.h"
#include <Elementary.h>
#include <curl/curl.h>
#include <dlog.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <cJSON.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <errno.h>
#include <tizen.h>
#include <libgen.h> // For dirname
#include <time.h>

// Global variable to store the last image URL
//static char last_image_url[512] = "";



//#define LOG_TAG "ST_IMAGE_CAPTURE"

// ---------- CONFIG ----------
static const char* ACCESS_TOKEN = "074cbd3d-b2fa-4230-aa6b-7c58721025f6";


//static const char* ACCESS_TOKEN = "a8488d8b-7676-4997-a2ac-213eb881b06f";  //old Token to test refresh token
//static const char* ACCESS_TOKEN = "8785aad1-0af7-4192-97c8-0976560a1d71";   //current token to test file saving and json generation
static const char* DEVICE_ID    = "95c6572c-6373-41f4-9cba-daf39a38f59c"; //"286bfff3-ad00-4b6b-8c77-6f400dfa99a8";  //
static const char* API_BASE     = "https://api.smartthings.com/v1";
#define REFRESH_INTERVAL_SEC 30
#define SAVE_FOLDER "/opt/usr/home/owner/content/Images"
// ----------------------------

typedef struct appdata {
    Evas_Object *win;
    Evas_Object *conform;
    Evas_Object *box;
    Evas_Object *entry_output;
    Evas_Object *entry_log;
    Evas_Object *img_view;
    bool live_running; // Controls whether live capture is running
    bool live_continuous;    // Controls whether to run continuously or once
} appdata_s;

// ---------- HTTP Helpers ----------
typedef struct { char *buf; size_t len; } mem_t;

static size_t write_cb(void *ptr, size_t size, size_t nmemb, void *userdata) {
    mem_t *m = userdata;
    size_t new_len = m->len + size * nmemb;
    m->buf = realloc(m->buf, new_len + 1);
    memcpy(m->buf + m->len, ptr, size * nmemb);
    m->buf[new_len] = '\0';
    m->len = new_len;
    return size * nmemb;
}

static char* http_get(const char *url, const char *token) {
    CURL *curl = curl_easy_init();
    if (!curl) return NULL;
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    return m.buf;
}

static char* http_post(const char *url, const char *token, const char *payload) {
    CURL *curl = curl_easy_init();
    if (!curl) return NULL;
    mem_t m = { .buf = calloc(1,1), .len = 0 };
    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);
    headers = curl_slist_append(headers, "Content-Type: application/json");
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &m);
    curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    return m.buf;
}

static bool http_download_file(const char *url, const char *token, const char *save_path) {
    CURL *curl = curl_easy_init();
    if (!curl) return false;
    FILE *fp = fopen(save_path, "wb");
    if (!fp) return false;
    struct curl_slist *headers = NULL;
    char auth[512];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", token);
    headers = curl_slist_append(headers, auth);
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, NULL);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, fp);
    CURLcode res = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
    curl_slist_free_all(headers);
    fclose(fp);
    return (res == CURLE_OK);
}
// ----------------------------------

static void ui_log_set(appdata_s *ad, const char *text) {
    elm_entry_entry_set(ad->entry_log, text);
    elm_entry_cursor_end_set(ad->entry_log);
}
static void ui_log_append(appdata_s *ad, const char *text) {
    const char *prev = elm_entry_entry_get(ad->entry_log);
    char *new_txt = malloc(strlen(prev) + strlen(text) + 8);
    sprintf(new_txt, "%s<br>%s", prev, text);
    elm_entry_entry_set(ad->entry_log, new_txt);
    free(new_txt);
    elm_entry_cursor_end_set(ad->entry_log);
}
// ----------------------------------

//Base64 conversions

unsigned char* readImageToBytes(const char* filePath, size_t* size) {
    FILE* file = fopen(filePath, "rb");
    if (!file) {
        perror("Error Opening File");
        return NULL;
    }

    // Move to the end of the file to get its size
    fseek(file, 0, SEEK_END);
    *size = ftell(file);
    fseek(file, 0, SEEK_SET);

    // Allocate memory for the image data
    unsigned char* buffer = (unsigned char*)malloc(*size);
    if (!buffer) {
        perror("Error Allocating Memory");
        fclose(file);
        return NULL;
    }

    // Read the file into the buffer
    if (fread(buffer, 1, *size, file) != *size) {
        perror("Error Reading File");
        free(buffer);
        fclose(file);
        return NULL;
    }

    fclose(file);
    return buffer;
}


char* encode_base64(const unsigned char* data, size_t length, size_t* output_length) {
    static const char base64_chars[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789+/";

    // Calculate the maximum possible length of the Base64 string
    *output_length = 4 * ((length + 2) / 3);
    char* result = (char*)malloc(*output_length + 1);
    if (!result) {
        perror("Error Allocating Memory");
        return NULL;
    }

    int i = 0, j = 0;
    unsigned char six_bit_chunks[4];
    unsigned char chunks[3];

    // Process the data in chunks of 3 bytes
    for (size_t in_idx = 0; in_idx < length; in_idx++) {
        chunks[i++] = data[in_idx];
        if (i == 3) {
            result[j++] = base64_chars[(chunks[0] & 0xFC) >> 2];
            result[j++] = base64_chars[((chunks[0] & 0x03) << 4) | (chunks[1] & 0xF0) >> 4];
            result[j++] = base64_chars[((chunks[1] & 0x0F) << 2) | (chunks[2] & 0xC0) >> 6];
            result[j++] = base64_chars[chunks[2] & 0x3F];
            i = 0;
        }
    }

    // Handle remaining bytes (1 or 2 bytes)
    if (i) {
        for (int j = i; j < 3; j++) {
            chunks[j] = '\0';
        }

        six_bit_chunks[0] = (chunks[0] & 0xFC) >> 2;
        six_bit_chunks[1] = ((chunks[0] & 0x03) << 4) | (chunks[1] & 0xF0) >> 4;
        six_bit_chunks[2] = ((chunks[1] & 0x0F) << 2) | (chunks[2] & 0xC0) >> 6;
        six_bit_chunks[3] = chunks[2] & 0x3F;

        for (int j = 0; j < i + 1; j++) {
            result[j] = base64_chars[six_bit_chunks[j]];
        }

        while (i++ < 3) {
            result[j++] = '=';
        }
    }

    result[*output_length] = '\0'; // Null-terminate the string
    *output_length = j; // Update the actual length of the Base64 string
    return result;
}





// Function declarations
unsigned char* readImageToBytes(const char* filePath, size_t* size);
char* encode_base64(const unsigned char* data, size_t length, size_t* output_length);


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

    sleep(1); // Wait for the refresh command to be processed

    // Step 2: Send the image capture command
    const char payload[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"imageCapture\","
        "\"command\":\"take\",\"arguments\":[]}]}";
    free(http_post(url, ACCESS_TOKEN, payload));

    sleep(1); // Wait for SmartThings to process capture

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


        // Extract the directory path from save_path
        char *dir_path = strdup(save_path);
        char *dir = dirname(dir_path);
        // Ensure the directory exists
        if (mkdir(dir, 0777) != 0 && errno != EEXIST) {
            ui_log_append(ad, "Failed to create directory.");
            free(dir_path);
            return;
        }
        free(dir_path);

        // Log the directory path where files will be saved
        char dir_log_message[512];
        snprintf(dir_log_message, sizeof(dir_log_message), "Files will be saved in directory: %s", dir);
        ui_log_append(ad, dir_log_message);

        // Step 5: Read the image file and encode it in Base64
        size_t image_size;
        unsigned char* image_data = readImageToBytes(save_path, &image_size);
        if (image_data) {
            size_t output_length;
            char* base64_encoded = encode_base64(image_data, image_size, &output_length);
            if (base64_encoded) {
                ui_log_append(ad, "Base64 encoded image:");

                // Step 6: Save the Base64-encoded string to a .txt file
                char txt_path[512];
                snprintf(txt_path, sizeof(txt_path), "%s/base64_img.txt", dir);

                FILE *txt_file = fopen(txt_path, "w");
                if (txt_file) {
                    if (fwrite(base64_encoded, 1, output_length, txt_file) != output_length) {
                        ui_log_append(ad, "Failed to write to base64_img.txt.");
                    } else {
                        ui_log_append(ad, "Base64 encoded image saved to base64_img.txt");
                    }
                    fclose(txt_file);
                } else {
                    ui_log_append(ad, ("Failed to create base64_img.txt: %s", strerror(errno)));
                }

                // Log the .txt file path
                char txt_log_message[512];
                snprintf(txt_log_message, sizeof(txt_log_message), "Base64 encoded image saved to: %s", txt_path);
                ui_log_append(ad, txt_log_message);

                // Step 7: Create and save the prompt.json file using cjson
                // Step 7: Create and save the prompt.json file using cjson
                cJSON *json = cJSON_CreateObject();
                if (json) {
                    cJSON_AddStringToObject(json, "method", "generate_from_image");
                    cJSON *params = cJSON_CreateArray();
                    cJSON_AddItemToArray(params, cJSON_CreateString("<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n<image> Analyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc. Answer Yes or No.<|im_end|>\n<|im_start|>assistant\n"));
                    cJSON_AddItemToArray(params, cJSON_CreateString(base64_encoded));
                    cJSON_AddItemToObject(json, "params", params);
                    cJSON_AddNumberToObject(json, "id", 42);
                    char *json_string = cJSON_Print(json);
                    if (json_string) {
                        char json_path[512];
                        snprintf(json_path, sizeof(json_path), "%s/prompt.json", dir);

                        FILE *json_file = fopen(json_path, "w");
                        if (json_file) {
                            if (fprintf(json_file, "%s", json_string) < 0) {
                                ui_log_append(ad, "Failed to write to prompt.json.");

                            } else {
                                ui_log_append(ad, "prompt.json created successfully.");
                            }
                            fclose(json_file);
                        } else {
                            ui_log_append(ad, ("Failed to create prompt.json: %s", strerror(errno)));
                        }
                        free(json_string); // Free the JSON string memory

                        // Log the .json file path
                        char json_log_message[512];
                        snprintf(json_log_message, sizeof(json_log_message), "prompt.json saved to: %s", json_path);
                        ui_log_append(ad, json_log_message);
                    } else {
                        ui_log_append(ad, "Failed to print JSON object.");
                    }
                    cJSON_Delete(json); // Clean up the cJSON object
                } else {
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

    sleep(5); // Wait for the refresh command to be processed

    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");

    if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
        printf("Failed to send refresh command.\n");
    }


}

//COMBINED PAYLOAD
/*static void take_image_capture(appdata_s *ad, const char *save_path) {
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s/commands", API_BASE, DEVICE_ID);

    // Combine the refresh and image capture commands into one payload
    const char payload[] =
        "{\"commands\":["
            "{\"component\":\"main\",\"capability\":\"Refresh\",\"command\":\"refresh\",\"arguments\":[]},"
            "{\"component\":\"main\",\"capability\":\"imageCapture\",\"command\":\"take\",\"arguments\":[]}"
        "]}";

    // Send the combined command
    ui_log_append(ad, "Sending combined refresh and image capture command...");
    if (http_post(url, ACCESS_TOKEN, payload) == NULL) {
        printf("Failed to send combined command.\n");
        return;
    }

    sleep(1); // Wait for the commands to be processed

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

        // Extract the directory path from save_path
        char *dir_path = strdup(save_path);
        char *dir = dirname(dir_path);
        // Ensure the directory exists
        if (mkdir(dir, 0777) != 0 && errno != EEXIST) {
            ui_log_append(ad, "Failed to create directory.");
            free(dir_path);
            return;
        }
        free(dir_path);

        // Log the directory path where files will be saved
        char dir_log_message[512];
        snprintf(dir_log_message, sizeof(dir_log_message), "Files will be saved in directory: %s", dir);
        ui_log_append(ad, dir_log_message);

        // Step 5: Read the image file and encode it in Base64
        size_t image_size;
        unsigned char* image_data = readImageToBytes(save_path, &image_size);
        if (image_data) {
            size_t output_length;
            char* base64_encoded = encode_base64(image_data, image_size, &output_length);
            if (base64_encoded) {
                ui_log_append(ad, "Base64 encoded image:");

                // Step 6: Save the Base64-encoded string to a .txt file
                char txt_path[512];
                snprintf(txt_path, sizeof(txt_path), "%s/base64_img.txt", dir);

                FILE *txt_file = fopen(txt_path, "w");
                if (txt_file) {
                    if (fwrite(base64_encoded, 1, output_length, txt_file) != output_length) {
                        ui_log_append(ad, "Failed to write to base64_img.txt.");
                    } else {
                        ui_log_append(ad, "Base64 encoded image saved to base64_img.txt");
                    }
                    fclose(txt_file);
                } else {
                    ui_log_append(ad, ("Failed to create base64_img.txt: %s", strerror(errno)));
                }

                // Log the .txt file path
                char txt_log_message[512];
                snprintf(txt_log_message, sizeof(txt_log_message), "Base64 encoded image saved to: %s", txt_path);
                ui_log_append(ad, txt_log_message);

                // Step 7: Create and save the prompt.json file using cjson
                cJSON *json = cJSON_CreateObject();
                if (json) {
                    cJSON_AddStringToObject(json, "method", "generate_from_image");
                    cJSON *params = cJSON_CreateArray();
                    cJSON_AddItemToArray(params, cJSON_CreateString("<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n<image> Analyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc. Answer Yes or No.<|im_end|>\n<|im_start|>assistant\n"));
                    cJSON_AddItemToArray(params, cJSON_CreateString(base64_encoded));
                    cJSON_AddItemToObject(json, "params", params);
                    cJSON_AddNumberToObject(json, "id", 42);
                    char *json_string = cJSON_Print(json);
                    if (json_string) {
                        char json_path[512];
                        snprintf(json_path, sizeof(json_path), "%s/prompt.json", dir);

                        FILE *json_file = fopen(json_path, "w");
                        if (json_file) {
                            if (fprintf(json_file, "%s", json_string) < 0) {
                                ui_log_append(ad, "Failed to write to prompt.json.");
                            } else {
                                ui_log_append(ad, "prompt.json created successfully.");
                            }
                            fclose(json_file);
                        } else {
                            ui_log_append(ad, ("Failed to create prompt.json: %s", strerror(errno)));
                        }
                        free(json_string); // Free the JSON string memory

                        // Log the .json file path
                        char json_log_message[512];
                        snprintf(json_log_message, sizeof(json_log_message), "prompt.json saved to: %s", json_path);
                        ui_log_append(ad, json_log_message);
                    } else {
                        ui_log_append(ad, "Failed to print JSON object.");
                    }
                    cJSON_Delete(json); // Clean up the cJSON object
                } else {
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

    sleep(5); // Wait for the refresh command to be processed

    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");

    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";

    if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
        printf("Failed to send refresh command.\n");
    }
}

static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);


    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";

        if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
            printf("Failed to send refresh command.\n");
        }

    sleep(3); // Wait for the refresh command to be processed


    ui_log_set(ad, "Fetching device capabilities...");
    char *resp = http_get(url, ACCESS_TOKEN);
    if (resp) {
        ui_log_append(ad, "<b>Capabilities:</b>");
        ui_log_append(ad, resp);
        free(resp);
    } else {
        ui_log_append(ad, "Failed to fetch capabilities.");
    }
}

static Eina_Bool live_loop_cb(void *data) {
    appdata_s *ad = data;
    if (!ad->live_running) return ECORE_CALLBACK_CANCEL;

    const char *data_path = app_get_data_path(); // Get the data directory path
    char save_path[512];
    snprintf(save_path, sizeof(save_path), "%scaptured_image.jpg", data_path); // Construct the save path

    take_image_capture(ad, save_path); // Save the image in the data directory
    return ad->live_running ? ECORE_CALLBACK_RENEW : ECORE_CALLBACK_CANCEL;
}

static void live_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (!ad->live_running) {
        ad->live_running = true;
        elm_object_text_set(obj, "Stop Live Capture");
        ui_log_append(ad, "Starting live capture...");
        ecore_timer_add(REFRESH_INTERVAL_SEC, live_loop_cb, ad); // Start live capture
    } else {
        ad->live_running = false;
        elm_object_text_set(obj, "Start Live Capture");
        ui_log_append(ad, "Live capture stopped.");
    }
}*/

static void show_caps_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    char url[512];
    snprintf(url, sizeof(url), "%s/devices/%s", API_BASE, DEVICE_ID);


    // Step 1: Send the refresh command
    ui_log_append(ad, "Sending refresh command...");
    const char payload_refresh[] =
        "{\"commands\":[{\"component\":\"main\",\"capability\":\"Refresh\","
        "\"command\":\"refresh\",\"arguments\":[]}]}";

        if (http_post(url, ACCESS_TOKEN, payload_refresh) == NULL) {
            printf("Failed to send refresh command.\n");
        }

    sleep(3); // Wait for the refresh command to be processed



    ui_log_set(ad, "Fetching device capabilities...");
    char *resp = http_get(url, ACCESS_TOKEN);
    if (resp) {
        ui_log_append(ad, "<b>Capabilities:</b>");
        ui_log_append(ad, resp);
        free(resp);
    } else {
        ui_log_append(ad, "Failed to fetch capabilities.");
    }
}

static Eina_Bool live_loop_cb(void *data) {
    appdata_s *ad = data;
    if (!ad->live_running) return ECORE_CALLBACK_CANCEL;

    const char *data_path = app_get_data_path(); // Get the data directory path
    char save_path[512];
    snprintf(save_path, sizeof(save_path), "%scaptured_image.jpg", data_path); // Construct the save path

    take_image_capture(ad, save_path); // Save the image in the data directory
    return ad->live_running ? ECORE_CALLBACK_RENEW : ECORE_CALLBACK_CANCEL;
}

static void live_clicked(void *data, Evas_Object *obj, void *event_info) {
    appdata_s *ad = data;
    if (!ad->live_running) {
        ad->live_running = true;
        elm_object_text_set(obj, "Stop Live Capture");
        ui_log_append(ad, "Starting live capture...");
        ecore_timer_add(REFRESH_INTERVAL_SEC, live_loop_cb, ad); // Start live capture
    } else {
        ad->live_running = false;
        elm_object_text_set(obj, "Start Live Capture");
        ui_log_append(ad, "Live capture stopped.");
    }
}

// ----------------------------------


static void create_base_gui(appdata_s *ad) {
    // Window setup
    ad->win = elm_win_util_standard_add("ST_LIVE", "SmartThings Live Capture");
    elm_win_autodel_set(ad->win, EINA_TRUE);
    evas_object_color_set(ad->win, 200, 200, 200, 255); // Set background color to gray
    // evas_object_color_set(ad->win, 173, 216, 230, 255); // Set background color to clear blue

    // Conformant layout
    ad->conform = elm_conformant_add(ad->win);
    evas_object_size_hint_weight_set(ad->conform, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(ad->win, ad->conform);
    evas_object_show(ad->conform);

    // Main box for content
    ad->box = elm_box_add(ad->conform);
    evas_object_size_hint_weight_set(ad->box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_object_content_set(ad->conform, ad->box);
    evas_object_show(ad->box);

    // Set homogeneous spacing for the box (optional)
    elm_box_homogeneous_set(ad->box, EINA_TRUE); // Makes all elements have equal spacing

    // Buttons section (added directly to main box)
    Evas_Object *btn_caps = elm_button_add(ad->box);
    elm_object_text_set(btn_caps, "Show Capabilities");
    evas_object_smart_callback_add(btn_caps, "clicked", show_caps_clicked, ad);
    evas_object_size_hint_weight_set(btn_caps, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box, btn_caps);
    evas_object_show(btn_caps);

    // Image view section (added directly to main box, placed after "Show Capabilities" and over "Start Live Capture")
    ad->img_view = elm_image_add(ad->box);
    elm_image_resizable_set(ad->img_view, EINA_TRUE, EINA_TRUE);
    elm_image_aspect_fixed_set(ad->img_view, EINA_FALSE); // Preserve aspect ratio
    evas_object_size_hint_weight_set(ad->img_view, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND); // Fill available space
    evas_object_size_hint_align_set(ad->img_view, EVAS_HINT_FILL, EVAS_HINT_FILL); // Center the image
    evas_object_size_hint_min_set(ad->img_view, 0, 200); // Set minimum height to 200 pixels
    elm_box_pack_end(ad->box, ad->img_view); // Place image after "Show Capabilities"
    evas_object_raise(ad->img_view); // Ensure image is on top of other elements
    evas_object_hide(ad->img_view); // Hide image by default

    // Button: Start Live Capture (added directly to main box)
    Evas_Object *btn_live = elm_button_add(ad->box);
    elm_object_text_set(btn_live, "Start Live Capture");
    evas_object_smart_callback_add(btn_live, "clicked", live_clicked, ad);
    evas_object_size_hint_weight_set(btn_live, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_box_pack_end(ad->box, btn_live); // Place button after image
    evas_object_show(btn_live);

    // Log section (added directly to main box)
    Evas_Object *scroller = elm_scroller_add(ad->box);
    evas_object_size_hint_weight_set(scroller, EVAS_HINT_EXPAND, 0.4); // Adjust height for log
    evas_object_size_hint_align_set(scroller, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, scroller);

    ad->entry_log = elm_entry_add(scroller);
    elm_entry_scrollable_set(ad->entry_log, EINA_TRUE);
    elm_entry_editable_set(ad->entry_log, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_log, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_log, "Press 'Show Capabilities' or 'Start Live Capture'...");
    elm_object_content_set(scroller, ad->entry_log);
    evas_object_show(ad->entry_log);
    evas_object_show(scroller);

    // Model Output section (added directly to main box)
    ad->entry_output = elm_entry_add(ad->box);
    elm_entry_scrollable_set(ad->entry_output, EINA_TRUE);
    elm_entry_editable_set(ad->entry_output, EINA_FALSE);
    elm_entry_line_wrap_set(ad->entry_output, ELM_WRAP_CHAR);
    elm_object_text_set(ad->entry_output, "Model Output:");
    evas_object_size_hint_weight_set(ad->entry_output, EVAS_HINT_EXPAND, 0.1); // Adjust height for output
    evas_object_size_hint_align_set(ad->entry_output, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_box_pack_end(ad->box, ad->entry_output);
    evas_object_show(ad->entry_output);

    // Show window
    evas_object_show(ad->win);
}





// ----------------------------------

static bool app_create(void *data) {
    appdata_s *ad = data;
    curl_global_init(CURL_GLOBAL_DEFAULT);
    create_base_gui(ad);
    return true;
}
static void app_terminate(void *data) {
    curl_global_cleanup();
}
static void app_control(app_control_h app_control, void *data) {}
static void app_pause(void *data) {}
static void app_resume(void *data) {}
// ----------------------------------

int main(int argc, char *argv[]) {
    appdata_s ad = {0,};
    ui_app_lifecycle_callback_s event_callback = {0,};
    event_callback.create = app_create;
    event_callback.terminate = app_terminate;
	event_callback.pause = app_pause;
	event_callback.resume = app_resume;
	event_callback.app_control = app_control;
	return ui_app_main(argc, argv, &event_callback, &ad); // Start the application
}
