#include <tizen.h>
#include <dlog.h>
#include <smartthings_client.h>
#include <ses_account.h>

#define LOG_TAG "CameraCapabilities"

static smartthings_client_h g_client = nullptr;

// ---- Callback: When we receive device status (capabilities/attributes)
void device_status_cb(smartthings_client_h handle,
                      const char *device_id,
                      const char *capability,
                      const char *attribute,
                      const char *value,
                      void *user_data)
{
    dlog_print(DLOG_INFO, LOG_TAG, "Device: %s", device_id);
    dlog_print(DLOG_INFO, LOG_TAG, "Capability: %s", capability);
    dlog_print(DLOG_INFO, LOG_TAG, " └─ %s = %s", attribute, value);
}

// ---- Callback: When device list is received
void device_list_cb(smartthings_client_h handle,
                    const char **device_id_list,
                    int device_count,
                    void *user_data)
{
    dlog_print(DLOG_INFO, LOG_TAG, "Received %d device(s)", device_count);

    for (int i = 0; i < device_count; ++i) {
        const char *id = device_id_list[i];
        dlog_print(DLOG_INFO, LOG_TAG, "[%d] Requesting capabilities for: %s", i, id);
        // Query the full status (capability list) of each device
        smartthings_client_get_device_status(handle, id);
    }
}

// ---- Callback: Connection state
void connection_status_cb(smartthings_client_h handle,
                          smartthings_client_connection_status_e status,
                          void *user_data)
{
    if (status == SMARTTHINGS_CLIENT_CONNECTION_STATUS_CONNECTED) {
        dlog_print(DLOG_INFO, LOG_TAG, "Connected to SmartThings Cloud");
        smartthings_client_get_device_list(handle);
    } else if (status == SMARTTHINGS_CLIENT_CONNECTION_STATUS_DISCONNECTED) {
        dlog_print(DLOG_INFO, LOG_TAG, "Disconnected from SmartThings");
    }
}

// ---- SES login result
void login_result_cb(ses_account_error_e result, void *user_data)
{
    if (result != SES_ACCOUNT_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Samsung Account login failed: %d", result);
        return;
    }

    dlog_print(DLOG_INFO, LOG_TAG, "Login successful. Initializing SmartThings Client...");

    if (!g_client) {
        int r = smartthings_client_initialize(&g_client);
        if (r != SMARTTHINGS_CLIENT_ERROR_NONE) {
            dlog_print(DLOG_ERROR, LOG_TAG, "Initialize failed: %d", r);
            return;
        }

        smartthings_client_set_connection_status_changed_cb(g_client, connection_status_cb, nullptr);
        smartthings_client_set_device_list_updated_cb(g_client, device_list_cb, nullptr);
        smartthings_client_set_device_status_changed_cb(g_client, device_status_cb, nullptr);
    }

    int rc = smartthings_client_connect(g_client);
    if (rc == SMARTTHINGS_CLIENT_ERROR_NONE)
        dlog_print(DLOG_INFO, LOG_TAG, "Connecting to SmartThings Cloud...");
    else
        dlog_print(DLOG_ERROR, LOG_TAG, "Connect failed: %d", rc);
}

// ---- Login or connect
void ensure_login()
{
    bool logged_in = false;
    int ret = ses_account_is_logged_in(&logged_in);
    if (ret != SES_ACCOUNT_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "ses_account_is_logged_in failed: %d", ret);
        return;
    }

    if (logged_in) {
        dlog_print(DLOG_INFO, LOG_TAG, "Already logged in; proceeding to connect...");
        login_result_cb(SES_ACCOUNT_ERROR_NONE, nullptr);
    } else {
        dlog_print(DLOG_INFO, LOG_TAG, "Requesting Samsung Account login...");
        ses_account_request_login(nullptr, login_result_cb, nullptr);
    }
}

// ---- App lifecycle
static bool app_create(void *data)
{
    dlog_print(DLOG_INFO, LOG_TAG, "App starting...");
    ensure_login();
    return true;
}

static void app_terminate(void *data)
{
    if (g_client) {
        smartthings_client_disconnect(g_client);
        smartthings_client_deinitialize(g_client);
        g_client = nullptr;
    }
}

int main(int argc, char *argv[])
{
    ui_app_lifecycle_callback_s event_cb = {0};
    event_cb.create = app_create;
    event_cb.terminate = app_terminate;

    return ui_app_main(argc, argv, &event_cb, nullptr);
}