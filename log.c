#include <sys/stat.h>
#include <dlog.h>
#include <errno.h>

#define LOG_TAG "TOKEN_COPY"

// Copies /res/tokens.txt → /data/tokens.txt if missing
// Logs full paths and verifies successful readability afterward
static void ensure_token_file_exists(void) {
    const char *res_path = app_get_resource_path();
    const char *data_path = app_get_data_path();

    // Log resolved paths
    dlog_print(DLOG_INFO, LOG_TAG, "Resource path: %s", res_path);
    dlog_print(DLOG_INFO, LOG_TAG, "Data path: %s", data_path);

    // Construct source and destination paths
    char src[512], dst[512];
    snprintf(src, sizeof(src), "%stokens.txt", res_path);
    snprintf(dst, sizeof(dst), "%stokens.txt", data_path);

    // Check if file already exists in /data
    struct stat st;
    if (stat(dst, &st) == 0) {
        dlog_print(DLOG_INFO, LOG_TAG, "tokens.txt already exists in data, skipping copy.");
    } else {
        // Copy from /res to /data
        FILE *in = fopen(src, "r");
        if (!in) {
            dlog_print(DLOG_ERROR, LOG_TAG, "Failed to open %s for reading (errno=%d)", src, errno);
            return;
        }

        FILE *out = fopen(dst, "w");
        if (!out) {
            dlog_print(DLOG_ERROR, LOG_TAG, "Failed to open %s for writing (errno=%d)", dst, errno);
            fclose(in);
            return;
        }

        char buf[1024];
        size_t n;
        while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
            fwrite(buf, 1, n, out);
        }

        fclose(in);
        fclose(out);
        dlog_print(DLOG_INFO, LOG_TAG, "Copied tokens.txt from res to data successfully.");
    }

    // --- Verification step ---
    FILE *verify = fopen(dst, "r");
    if (!verify) {
        dlog_print(DLOG_ERROR, LOG_TAG, "Verification failed: cannot open %s (errno=%d)", dst, errno);
        return;
    }

    char preview[128] = {0};
    if (fgets(preview, sizeof(preview), verify)) {
        // Trim newline for cleaner output
        preview[strcspn(preview, "\r\n")] = 0;
        dlog_print(DLOG_INFO, LOG_TAG, "Verification OK: first line of tokens.txt = '%s'", preview);
    } else {
        dlog_print(DLOG_WARN, LOG_TAG, "Verification warning: tokens.txt is empty or unreadable.");
    }

    fclose(verify);
}