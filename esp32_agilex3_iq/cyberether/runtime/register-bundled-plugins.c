#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stddef.h>

typedef void (*gst_init_fn)(int *, char ***);
typedef void (*plugin_register_fn)(void);
__attribute__((constructor)) static void register_bundled_plugins(void) {
    gst_init_fn init = (gst_init_fn)dlsym(RTLD_DEFAULT, "gst_init");
    if (!init) { fprintf(stderr, "bundled-plugin-init: gst_init symbol missing\n"); return; }
    init(NULL, NULL);
    const char *names[] = {
        "gst_plugin_dtls_register",
        "gst_plugin_nice_register",
        "gst_plugin_nvcodec_register",
        "gst_plugin_sctp_register",
        "gst_plugin_srtp_register",
        "gst_plugin_v4l2codecs_register",
        "gst_plugin_webrtc_register",
    };
    for (size_t i = 0; i < sizeof(names)/sizeof(names[0]); ++i) {
        plugin_register_fn reg = (plugin_register_fn)dlsym(RTLD_DEFAULT, names[i]);
        if (reg) { reg(); fprintf(stderr, "bundled-plugin-init: registered %s\n", names[i]); }
        else fprintf(stderr, "bundled-plugin-init: missing %s\n", names[i]);
    }
}
