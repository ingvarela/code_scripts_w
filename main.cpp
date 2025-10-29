// g++ -std=c++17 main_client.cpp -o st_cam_client \
//   `pkg-config --cflags --libs elementary ewebkit2` \
//   -lcurl -lcjson -lsmartthings-client
//
// Same privileges and manifest as the previous version.
// Purpose: initialize SmartThings Client SDK while still using OAuth + REST for camera capture.

#include <smartthings_client.h>   // from Tizen SmartThings SDK
#include <Elementary.h>
#include <EWebKit2.h>
#include <curl/curl.h>
#include <cjson/cJSON.h>
#include <app_common.h>
#include <dlog.h>

#include <string>
#include <vector>
#include <stdexcept>
#include <fstream>
#include <unistd.h>

#define LOG_TAG "STCLIENT"

// ------------------------------------------------------------
// COPY the same constants/config as in previous version
// ------------------------------------------------------------
static const char* CLIENT_ID     = "YOUR_CLIENT_ID";
static const char* CLIENT_SECRET = "YOUR_CLIENT_SECRET";
static const char* REDIRECT_URI  = "YOUR_REGISTERED_REDIRECT_URI";
static const char* SCOPES        = "r:devices:* x:devices:*";

static const char* AUTH_BASE     = "https://auth-global.api.smartthings.com/oauth/authorize";
static const char* TOKEN_URL     = "https://auth-global.api.smartthings.com/oauth/token";
static const char* API_BASE      = "https://api.smartthings.com/v1";

// (All curl helpers, token save/load, OAuth, SmartThings REST helpers, and EFL UI code
// remain identical to previous version — truncated below for brevity)

// ------------------------------------------------------------
// SmartThings Client SDK minimal scaffolding
// ------------------------------------------------------------
struct STClient {
    smartthings_client_h handle{};
    bool connected = false;
};

static void _client_status_cb(smartthings_client_h, smartthings_client_status_e status, void* user_data) {
    auto* ctx = static_cast<STClient*>(user_data);
    ctx->connected = (status == SMARTTHINGS_CLIENT_STATUS_CONNECTED);
    dlog_print(DLOG_INFO, LOG_TAG, "SmartThings Client status: %d", status);
}

static void _client_connection_cb(smartthings_client_h, bool is_connected, void* user_data) {
    auto* ctx = static_cast<STClient*>(user_data);
    ctx->connected = is_connected;
    dlog_print(DLOG_INFO, LOG_TAG, "Client connection changed: %d", is_connected);
}

static void init_smartthings_client(STClient& ctx) {
    int ret = smartthings_client_initialize(&ctx.handle, _client_status_cb, &ctx);
    if (ret != SMARTTHINGS_CLIENT_ERROR_NONE) {
        dlog_print(DLOG_ERROR, LOG_TAG, "smartthings_client_initialize failed: %d", ret);
        ctx.handle = nullptr;
        return;
    }

    // optional: register connection status callback
    smartthings_client_set_connection_status_cb(ctx.handle, _client_connection_cb, &ctx);

    ret = smartthings_client_start(ctx.handle);
    if (ret == SMARTTHINGS_CLIENT_ERROR_NONE)
        dlog_print(DLOG_INFO, LOG_TAG, "SmartThings Client started");
    else
        dlog_print(DLOG_ERROR, LOG_TAG, "Client start failed: %d", ret);
}

static void deinit_smartthings_client(STClient& ctx) {
    if (!ctx.handle) return;
    smartthings_client_stop(ctx.handle);
    smartthings_client_deinitialize(ctx.handle);
    ctx.handle = nullptr;
}

// ------------------------------------------------------------
// EFL UI app from the previous REST version
// ------------------------------------------------------------
// Copy the complete App struct, OAuth, device listing, take(), preview, and EFL UI setup
// from the previous example — they remain unchanged.
// ------------------------------------------------------------

EAPI_MAIN int elm_main(int, char**) {
    curl_global_init(CURL_GLOBAL_DEFAULT);

    STClient st_ctx;
    init_smartthings_client(st_ctx);

    // create and run same EFL UI from previous version
    extern void run_rest_ui(); // if you split into another file
    // or paste the full UI code here from the previous version
    // (authorize → list cameras → capture → preview)
    // Example minimal:
    dlog_print(DLOG_INFO, LOG_TAG, "Running EFL UI...");
    // --- paste same EFL UI code from previous message here ---
    // (omitted here for brevity; identical to part 1)

    elm_run();

    deinit_smartthings_client(st_ctx);
    curl_global_cleanup();
    return 0;
}
ELM_MAIN()