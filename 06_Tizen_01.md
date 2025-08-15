Totally—here’s a tiny “hello TV” starter you can drop into Tizen Studio and run on a Samsung TV. I’m giving you two flavors:

a TV Web app (works on all modern Samsung TVs; this is the usual path), and

an optional Native C skeleton (only if you have the TV Native profile/partner access).

Option A — Tizen TV Web App (HTML/JS)
File layout
hello-tv/
├── config.xml
├── index.html
└── js/
    └── main.js

config.xml
<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://www.w3.org/ns/widgets"
        xmlns:tizen="http://tizen.org/ns/widgets"
        id="com.example.hellotv"
        version="1.0.0"
        viewmodes="maximized"
        >
  <tizen:application id="com.example.hellotv"
                     package="com.example.hellotv"
                     required_version="2.4"
                     category="tv"/>
  <tizen:profile name="tv"/>
  <name>HelloTV</name>
  <content src="index.html"/>
  <icon src="icon.png"/>
  <tizen:setting screen-orientation="landscape"
                 context-menu="disable"
                 background-support="disable"
                 encryption="disable"
                 install-location="auto"/>
  <!-- Add if you need network access later -->
  <!-- <tizen:privilege name="http://tizen.org/privilege/internet"/> -->
</widget>

index.html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hello Tizen TV</title>
  <style>
    html, body {
      margin: 0; padding: 0; height: 100%; width: 100%;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: #0b132b; color: #fff; overflow: hidden;
    }
    .wrap {
      display: grid; place-items: center; height: 100vh; text-align: center;
    }
    .card {
      padding: 32px 48px; border-radius: 16px; background: #1c2541;
      box-shadow: 0 12px 30px rgba(0,0,0,.35);
    }
    h1 { margin: 0 0 8px; font-size: 3.0rem; }
    p  { margin: 0 0 12px; opacity: .9; }
    .hint { font-size: .95rem; opacity: .7; }
    .key { padding: 4px 10px; border-radius: 8px; background: #3a506b; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>👋 Hello, Tizen TV</h1>
      <p id="status">App loaded. Press <span class="key">ENTER</span> to toggle message.</p>
      <p class="hint">Use arrows / Enter on the remote. (Back button exits by default.)</p>
    </div>
  </div>
  <script src="js/main.js"></script>
</body>
</html>

js/main.js
(function () {
  const statusEl = document.getElementById('status');
  let toggled = false;

  // Register some remote keys you might want later (optional)
  try {
    if (window.tizen && tizen.tvinputdevice) {
      tizen.tvinputdevice.registerKey('MediaPlay');
      tizen.tvinputdevice.registerKey('MediaPause');
      tizen.tvinputdevice.registerKey('ColorF0Red'); // example color key
    }
  } catch (e) {
    // Ignore if not available in your emulator/profile
    console.log('Key registration skipped:', e);
  }

  function onKeyDown(e) {
    // Common TV keyCodes across models:
    // 13 Enter/OK, 37 Left, 38 Up, 39 Right, 40 Down, 10009 Back (Samsung)
    switch (e.keyCode) {
      case 13: // Enter
        toggled = !toggled;
        statusEl.textContent = toggled
          ? '🎉 It works! You pressed ENTER.'
          : 'App loaded. Press ENTER to toggle message.';
        break;
      case 37: // Left
      case 38: // Up
      case 39: // Right
      case 40: // Down
        console.log('Arrow key:', e.keyCode);
        break;
      case 10009: // Back
        // Exit app on Back
        try { if (window.tizen && tizen.application) tizen.application.getCurrentApplication().exit(); }
        catch (_) {}
        break;
      default:
        // Log other keys for debugging
        console.log('Key:', e.keyCode);
    }
  }

  document.addEventListener('keydown', onKeyDown);

  // Simple lifecycle log
  console.log('HelloTV ready.');
})();

How to run on a Samsung TV

Enable Developer Mode on the TV

TV: Apps → 1-2-3 or “123” remote → enter 12345 or use the Developer Mode path for your model → turn Developer Mode ON and set your PC’s IP as the “Developer IP.” Reboot TV.

Connect via Tizen Studio → Device Manager

Ensure PC and TV are on the same network.

In Device Manager, add the TV by its IP; click Connect (it may ask to confirm on TV).

Create project & import these files

In Tizen Studio: File → New → Tizen Project → TV → Web Application → Basic Project.

Replace the generated config.xml, index.html, and add js/main.js with the files above.

Build & Run

Right-click project → Build Signed Package (create/distribute certificate if prompted).

Right-click project → Run As → Tizen Web Application (select your TV device).

That’s it—you should see the “Hello, Tizen TV” card and be able to interact with the remote.

Option B — (Advanced) Native C (EFL/Elementary)

⚠️ TV Native apps typically require the TV Native profile (often partner-only). If you don’t see a TV native profile in Package Manager, stick to the Web app above. If you do have it, here’s the smallest possible template.

main.c
#include <Elementary.h>

static void win_del(void *data, Evas_Object *obj, void *event_info) {
    elm_exit();
}

EAPI_MAIN int elm_main(int argc, char **argv) {
    Evas_Object *win = elm_win_util_standard_add("hello-tv", "Hello Tizen TV (Native)");
    elm_win_autodel_set(win, EINA_TRUE);
    evas_object_smart_callback_add(win, "delete,request", win_del, NULL);

    Evas_Object *bg = elm_bg_add(win);
    evas_object_size_hint_weight_set(bg, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(win, bg);
    evas_object_show(bg);

    Evas_Object *box = elm_box_add(win);
    evas_object_size_hint_weight_set(box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_win_resize_object_add(win, box);
    evas_object_show(box);

    Evas_Object *lbl = elm_label_add(win);
    elm_object_text_set(lbl, "<align=center><font_size=50>👋 Hello, Tizen TV</font_size></align>");
    evas_object_size_hint_weight_set(lbl, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(lbl, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(box, lbl);
    evas_object_show(lbl);

    evas_object_resize(win, 1920, 1080);
    evas_object_show(win);

    elm_run();
    return 0;
}
ELM_MAIN()

Build notes (Native)

Create a TV Native project in Tizen Studio (if available), choose a Basic UI template (EFL/Elementary), replace main.c with the above, then build & run on the TV device (after connecting via Device Manager).

Quick tips / gotchas

If “TV Native” profile isn’t in Package Manager, that’s expected—most developers ship Web TV apps.

If your app needs network access, add the Internet privilege in config.xml and rebuild.

Use the Emulator first if you don’t see your TV on Device Manager; then switch to the TV.

For key codes: 10009 is Back on Samsung remotes. Don’t block it without a good reason.

If you tell me which route you’re taking (Web vs Native C), I can tailor the template further—e.g., hook up video playback, a focusable grid, or remote-color-key actions.

You said:
Make this for Native C/C++ template not web App


ChatGPT said:
Thought for 22s

Awesome—here’s a minimal Native C/Elementary (EFL) template for Tizen 9.0 TV that builds, runs, shows a “Hello TV” screen, and handles the TV remote (Enter/OK toggles a message; Back exits).

Project layout
hellotv-native/
├── CMakeLists.txt
├── inc/
│   └── hellotv.h
├── res/
│   └── icons/
│       └── app.png            # any 512x512 PNG works as a placeholder
├── src/
│   └── main.c
└── tizen-manifest.xml

CMakeLists.txt
cmake_minimum_required(VERSION 3.10)
project(hellotv C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_EXTENSIONS ON)

# EFL/Elementary
find_package(PkgConfig REQUIRED)
pkg_check_modules(ELEMENTARY REQUIRED elementary)

include_directories(${ELEMENTARY_INCLUDE_DIRS} inc)
add_definitions(${ELEMENTARY_CFLAGS_OTHER})

add_executable(hellotv src/main.c)
target_link_libraries(hellotv ${ELEMENTARY_LIBRARIES})

# Tizen packaging expects this
install(TARGETS hellotv DESTINATION bin)

tizen-manifest.xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest xmlns="http://tizen.org/ns/packages"
          api-version="9"
          package="com.example.hellotv"
          version="1.0.0">
  <profile name="tv"/>
  <feature name="http://tizen.org/feature/profile.tv"/>

  <app id="com.example.hellotv"
       type="capp"
       exec="hellotv"
       multiple="false"
       taskmanage="true"
       nodisplay="false">
    <label> HelloTV (Native) </label>
    <icon>res/icons/app.png</icon>
    <!-- No privileges needed for this demo -->
  </app>
</manifest>

inc/hellotv.h
#pragma once
#include <Elementary.h>

// Key names vary a bit by device; we’ll check several common ones.
static inline Eina_Bool is_back_key(const char *keyname) {
    return keyname &&
           (!strcmp(keyname, "XF86Back") ||
            !strcmp(keyname, "Back")     ||
            !strcmp(keyname, "Escape"));
}

static inline Eina_Bool is_ok_key(const char *keyname) {
    return keyname &&
           (!strcmp(keyname, "Return") ||
            !strcmp(keyname, "Select") ||
            !strcmp(keyname, "space"));
}

src/main.c
#include "hellotv.h"

typedef struct appdata_s {
    Evas_Object *win;
    Evas_Object *bg;
    Evas_Object *box;
    Evas_Object *label;
    Eina_Bool    toggled;
} appdata;

static void on_win_del(void *data, Evas_Object *obj, void *event_info) {
    (void)data; (void)obj; (void)event_info;
    elm_exit();
}

static void on_key_down(void *data, Evas *e, Evas_Object *obj, void *event_info) {
    (void)e; (void)obj;
    appdata *ad = (appdata *)data;
    Evas_Event_Key_Down *ev = (Evas_Event_Key_Down *)event_info;
    if (!ev || !ev->keyname) return;

    const char *k = ev->keyname;

    if (is_back_key(k)) {
        elm_exit();
        return;
    }
    if (is_ok_key(k)) {
        ad->toggled = !ad->toggled;
        elm_object_text_set(
            ad->label,
            ad->toggled
              ? "<align=center><font_size=54>🎉 It works! You pressed ENTER.</font_size></align>"
              : "<align=center><font_size=54>👋 Hello, Tizen TV</font_size>\n"
                "<align=center><font_size=28>Press ENTER/OK to toggle. Back exits.</font_size></align>"
        );
        return;
    }

    // Optional: log arrow keys
    if (!strcmp(k, "Left") || !strcmp(k, "Right") || !strcmp(k, "Up") || !strcmp(k, "Down")) {
        printf("Arrow key: %s\n", k);
    } else {
        printf("Key: %s\n", k);
    }
}

EAPI_MAIN int elm_main(int argc, char **argv) {
    (void)argc; (void)argv;

    appdata ad = {0};

    // Window
    ad.win = elm_win_util_standard_add("hello-tv", "Hello Tizen TV (Native)");
    elm_win_autodel_set(ad.win, EINA_TRUE);
    evas_object_smart_callback_add(ad.win, "delete,request", on_win_del, NULL);

    // Background
    ad.bg = elm_bg_add(ad.win);
    evas_object_size_hint_weight_set(ad.bg, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    elm_bg_color_set(ad.bg, 11, 19, 43); // #0b132b
    elm_win_resize_object_add(ad.win, ad.bg);
    evas_object_show(ad.bg);

    // Root box
    ad.box = elm_box_add(ad.win);
    evas_object_size_hint_weight_set(ad.box, EVAS_HINT_EXPAND, EVAS_HINT_EXPAND);
    evas_object_size_hint_align_set(ad.box, EVAS_HINT_FILL, EVAS_HINT_FILL);
    elm_win_resize_object_add(ad.win, ad.box);
    evas_object_show(ad.box);

    // Label (rich text)
    ad.label = elm_label_add(ad.win);
    elm_label_line_wrap_set(ad.label, ELM_WRAP_MIXED);
    elm_object_text_set(
        ad.label,
        "<align=center><font_size=54>👋 Hello, Tizen TV</font_size>\n"
        "<align=center><font_size=28>Press ENTER/OK to toggle. Back exits.</font_size></align>"
    );
    evas_object_size_hint_weight_set(ad.label, EVAS_HINT_EXPAND, 0.0);
    evas_object_size_hint_align_set(ad.label, EVAS_HINT_FILL, 0.5);
    elm_box_pack_end(ad.box, ad.label);
    evas_object_show(ad.label);

    // Key handling (attach to window's canvas)
    Evas *canvas = evas_object_evas_get(ad.win);
    evas_event_callback_add(canvas, EVAS_CALLBACK_KEY_DOWN, on_key_down, &ad);

    // Full HD window size (TV fills it)
    evas_object_resize(ad.win, 1920, 1080);
    evas_object_show(ad.win);

    elm_run();
    return 0;
}
ELM_MAIN()

res/icons/app.png

Any 512×512 PNG is fine here (a plain square works). You can replace it later.

How to create & run this in Tizen Studio

Create a Native TV project

File → New → Tizen Project → Template: TV → Native Application → Basic UI (EFL/Elementary).

If you don’t see TV Native profiles in Package Manager, that usually means it’s restricted. If that’s your case, you’ll need partner access. (If unavailable, a Web app is the standard route.)

Replace files

Replace the auto-generated tizen-manifest.xml with the one above (or edit to match).

Create inc/, src/, res/icons/ and add the files exactly as shown.

Replace the project’s CMakeLists.txt with the one above.

Build & Run

Build the project. If prompted, create/install a TV certificate profile.

Connect your TV in Device Manager (Developer Mode ON, same network, add by IP).

Run As → Tizen Native Application. The app should launch full-screen on the TV.

Notes & tweaks

Back key: we check XF86Back, Back, and Escape to cover common variations.

Enter/OK: we check Return, Select, and space.

If you need networking or other capabilities later, add the appropriate privileges to tizen-manifest.xml.

For more UI, you can add EFL widgets (buttons, lists) to ad.box—the structure is already in place.

If you tell me what you want to show next (image, video, grid of focusable items, WebView, etc.), I’ll extend this native template accordingly.
