/**
 * Desktop unit tests for flipper-app/protocol.c
 *
 * Build & run:
 *   cd flipper-app/tests && make
 *
 * Requires only gcc (no external test framework).
 * Compiled with -fsanitize=address,undefined to catch buffer overflows / UB.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Provide the mock device name used by furi_hal_version_get_name_ptr() stub. */
const char* furi_mock_device_name = "TestFlipper";

#include "protocol.h"

/* ---------------------------------------------------------------------------
 * Minimal test harness
 * ------------------------------------------------------------------------- */

static int pass_count = 0;
static int fail_count = 0;

#define CHECK(expr) \
    do { \
        if(expr) { \
            pass_count++; \
        } else { \
            fail_count++; \
            fprintf(stderr, "  FAIL [%s:%d]: %s\n", __FILE__, __LINE__, #expr); \
        } \
    } while(0)

static void run_test(const char* name, void (*fn)(void)) {
    int before = fail_count;
    fn();
    printf("  %s %s\n", fail_count == before ? "PASS" : "FAIL", name);
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypeNotify
 * ------------------------------------------------------------------------- */

static void test_parse_notify_basic(void) {
    const char* json =
        "{\"v\":1,\"t\":\"notify\","
        "\"d\":{\"sound\":\"success\",\"vibro\":true,"
        "\"text\":\"Done\",\"sub\":\"2 files\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypeNotify);
    CHECK(strcmp(msg.sound, "success") == 0);
    CHECK(msg.vibro == true);
    CHECK(strcmp(msg.text, "Done") == 0);
    CHECK(strcmp(msg.text2, "2 files") == 0);
}

static void test_parse_notify_vibro_false(void) {
    const char* json =
        "{\"v\":1,\"t\":\"notify\","
        "\"d\":{\"sound\":\"alert\",\"vibro\":false,\"text\":\"\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.vibro == false);
    CHECK(msg.type == MsgTypeNotify);
}

static void test_parse_notify_missing_vibro_defaults_false(void) {
    /* vibro field absent → zero-initialised → false */
    const char* json =
        "{\"v\":1,\"t\":\"notify\",\"d\":{\"sound\":\"ping\",\"text\":\"hi\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.vibro == false);
}

static void test_parse_notify_sound_truncated(void) {
    /* sound field in ProtocolMessage is char[32] */
    char json[256];
    /* 31 chars fit exactly; 32nd would be NUL */
    snprintf(json, sizeof(json),
        "{\"v\":1,\"t\":\"notify\",\"d\":{\"sound\":\"%031d\",\"vibro\":false,\"text\":\"\"}}",
        0);
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(strlen(msg.sound) == 31);
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypeStatus
 * ------------------------------------------------------------------------- */

static void test_parse_status_both_lines(void) {
    const char* json =
        "{\"v\":1,\"t\":\"status\",\"d\":{\"line1\":\"Running\",\"line2\":\"step 2\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypeStatus);
    CHECK(strcmp(msg.text, "Running") == 0);
    CHECK(strcmp(msg.text2, "step 2") == 0);
}

static void test_parse_status_line2_absent(void) {
    const char* json =
        "{\"v\":1,\"t\":\"status\",\"d\":{\"line1\":\"Idle\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(strcmp(msg.text, "Idle") == 0);
    CHECK(msg.text2[0] == '\0');
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypeMenu
 * ------------------------------------------------------------------------- */

static void test_parse_menu(void) {
    const char* json =
        "{\"v\":1,\"t\":\"menu\","
        "\"d\":{\"items\":\"/commit|/review|/build\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypeMenu);
    CHECK(strcmp(msg.menu_data, "/commit|/review|/build") == 0);
}

static void test_parse_menu_empty(void) {
    const char* json =
        "{\"v\":1,\"t\":\"menu\",\"d\":{\"items\":\"\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.menu_data[0] == '\0');
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypeUsage
 * ------------------------------------------------------------------------- */

static void test_parse_usage(void) {
    const char* json =
        "{\"v\":1,\"t\":\"usage\","
        "\"d\":{\"ctx\":82,\"sess\":45,\"clvl\":2}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypeUsage);
    CHECK(msg.has_usage_ctx == true);
    CHECK(msg.usage_ctx == 82);
    CHECK(msg.has_usage_sess == true);
    CHECK(msg.usage_sess == 45);
    CHECK(msg.has_usage_compact == true);
    CHECK(msg.usage_compact == 2);
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypeState
 * ------------------------------------------------------------------------- */

static void test_parse_state_true(void) {
    const char* json =
        "{\"v\":1,\"t\":\"state\",\"d\":{\"claude\":true}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypeState);
    CHECK(msg.claude_connected == true);
}

static void test_parse_state_false(void) {
    const char* json =
        "{\"v\":1,\"t\":\"state\",\"d\":{\"claude\":false}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.claude_connected == false);
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypePerm
 * ------------------------------------------------------------------------- */

static void test_parse_perm_tool_and_detail(void) {
    const char* json =
        "{\"v\":1,\"t\":\"perm\","
        "\"d\":{\"tool\":\"Bash\",\"detail\":\"rm -rf /\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypePerm);
    CHECK(strcmp(msg.text, "Bash") == 0);
    CHECK(strcmp(msg.text2, "rm -rf /") == 0);
}

static void test_parse_perm_detail_absent(void) {
    const char* json =
        "{\"v\":1,\"t\":\"perm\",\"d\":{\"tool\":\"Edit\"}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(strcmp(msg.text, "Edit") == 0);
    CHECK(msg.text2[0] == '\0');
}

/* ---------------------------------------------------------------------------
 * protocol_parse — MsgTypePing
 * ------------------------------------------------------------------------- */

static void test_parse_ping_with_rssi(void) {
    const char* json =
        "{\"v\":1,\"t\":\"ping\",\"d\":{\"rssi\":-72}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.type == MsgTypePing);
    CHECK(msg.has_rssi == true);
    CHECK(msg.rssi == -72);
}

static void test_parse_ping_without_rssi(void) {
    const char* json =
        "{\"v\":1,\"t\":\"ping\",\"d\":{}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(msg.has_rssi == false);
}

/* ---------------------------------------------------------------------------
 * protocol_parse — field length boundary (PROTOCOL_MAX_FIELD_LEN = 64)
 * ------------------------------------------------------------------------- */

static void test_parse_text_exactly_63_chars(void) {
    char json[256];
    /* 63 'a' chars */
    snprintf(json, sizeof(json),
        "{\"v\":1,\"t\":\"status\",\"d\":{\"line1\":\"%063d\"}}", 0);
    /* replace digits with 'a' */
    char* p = strstr(json, "line1\":\"");
    if(p) { p += 8; for(int i = 0; i < 63; i++) p[i] = 'a'; }
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK(strlen(msg.text) == 63);
}

static void test_parse_text_64_chars_truncated_to_63(void) {
    /* 64 'b' chars should be truncated to 63 (out_size=64, max index=63) */
    char json[300];
    snprintf(json, sizeof(json),
        "{\"v\":1,\"t\":\"status\",\"d\":{\"line1\":\"%064d\"}}", 0);
    char* p = strstr(json, "line1\":\"");
    if(p) { p += 8; for(int i = 0; i < 64; i++) p[i] = 'b'; }
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == true);
    CHECK((int)strlen(msg.text) <= PROTOCOL_MAX_FIELD_LEN - 1);
}

/* ---------------------------------------------------------------------------
 * protocol_parse — error / null inputs
 * ------------------------------------------------------------------------- */

static void test_parse_null_json_returns_false(void) {
    ProtocolMessage msg;
    CHECK(protocol_parse(NULL, &msg) == false);
}

static void test_parse_null_msg_returns_false(void) {
    CHECK(protocol_parse("{\"v\":1,\"t\":\"ping\",\"d\":{}}", NULL) == false);
}

static void test_parse_unknown_type_returns_false(void) {
    const char* json = "{\"v\":1,\"t\":\"unknown_type\",\"d\":{}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == false);
}

static void test_parse_missing_t_field_returns_false(void) {
    const char* json = "{\"v\":1,\"d\":{}}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == false);
}

static void test_parse_missing_d_field_returns_false(void) {
    const char* json = "{\"v\":1,\"t\":\"notify\"}";
    ProtocolMessage msg;
    CHECK(protocol_parse(json, &msg) == false);
}

static void test_parse_garbage_does_not_crash(void) {
    const char* json = "not json at all!!!";
    ProtocolMessage msg;
    /* must not crash; return value may be false */
    protocol_parse(json, &msg);
    CHECK(1); /* just reaching here = pass */
}

static void test_parse_empty_string_returns_false(void) {
    ProtocolMessage msg;
    CHECK(protocol_parse("", &msg) == false);
}

/* ---------------------------------------------------------------------------
 * protocol_build_hello
 * ------------------------------------------------------------------------- */

static void test_build_hello_normal_name(void) {
    furi_mock_device_name = "MyFlipper";
    char buf[256];
    int n = protocol_build_hello(buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(strstr(buf, "\"t\":\"hello\"") != NULL);
    CHECK(strstr(buf, "\"bt\":\"MyFlipper\"") != NULL);
    CHECK(buf[n - 1] == '\n');
    CHECK(n == (int)strlen(buf));
}

static void test_build_hello_escapes_double_quote(void) {
    furi_mock_device_name = "Flip\"er";
    char buf[256];
    int n = protocol_build_hello(buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(strstr(buf, "\\\"") != NULL);   /* escaped quote present */
    CHECK(strstr(buf, "Flip\"er") == NULL); /* raw unescaped quote absent */
}

static void test_build_hello_escapes_backslash(void) {
    furi_mock_device_name = "Flip\\er";
    char buf[256];
    int n = protocol_build_hello(buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(strstr(buf, "\\\\") != NULL);   /* escaped backslash present */
}

static void test_build_hello_null_name_gives_empty_bt(void) {
    furi_mock_device_name = NULL;
    char buf[256];
    int n = protocol_build_hello(buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(strstr(buf, "\"bt\":\"\"") != NULL);
    /* restore */
    furi_mock_device_name = "TestFlipper";
}

static void test_build_hello_buf_too_small_returns_zero(void) {
    furi_mock_device_name = "TestFlipper";
    char buf[5];
    int n = protocol_build_hello(buf, sizeof(buf));
    CHECK(n == 0);
}

/* ---------------------------------------------------------------------------
 * protocol_build_cmd
 * ------------------------------------------------------------------------- */

static void test_build_cmd_normal(void) {
    char buf[256];
    int n = protocol_build_cmd(buf, sizeof(buf), "/commit");
    CHECK(n > 0);
    CHECK(strstr(buf, "\"t\":\"cmd\"") != NULL);
    CHECK(strstr(buf, "\"/commit\"") != NULL);
    CHECK(buf[n - 1] == '\n');
    CHECK(n == (int)strlen(buf));
}

static void test_build_cmd_escapes_special_chars(void) {
    char buf[256];
    int n = protocol_build_cmd(buf, sizeof(buf), "say \"hello\\world\"");
    CHECK(n > 0);
    CHECK(strstr(buf, "\\\"") != NULL);
    CHECK(strstr(buf, "\\\\") != NULL);
}

static void test_build_cmd_null_text_gives_empty(void) {
    char buf[256];
    int n = protocol_build_cmd(buf, sizeof(buf), NULL);
    CHECK(n > 0);
    CHECK(strstr(buf, "\"text\":\"\"") != NULL);
}

static void test_build_cmd_buf_too_small_returns_zero(void) {
    char buf[5];
    int n = protocol_build_cmd(buf, sizeof(buf), "hello");
    CHECK(n == 0);
}

static void test_build_cmd_return_value_equals_strlen(void) {
    char buf[256];
    int n = protocol_build_cmd(buf, sizeof(buf), "test");
    CHECK(n == (int)strlen(buf));
}

/* ---------------------------------------------------------------------------
 * protocol_build_perm_resp
 * ------------------------------------------------------------------------- */

static void test_build_perm_resp_all_true(void) {
    char buf[256];
    int n = protocol_build_perm_resp(buf, sizeof(buf), true, true, true);
    CHECK(n > 0);
    CHECK(strstr(buf, "\"t\":\"perm_resp\"") != NULL);
    CHECK(strstr(buf, "\"allow\":true") != NULL);
    CHECK(strstr(buf, "\"always\":true") != NULL);
    CHECK(strstr(buf, "\"esc\":true") != NULL);
}

static void test_build_perm_resp_all_false(void) {
    char buf[256];
    int n = protocol_build_perm_resp(buf, sizeof(buf), false, false, false);
    CHECK(n > 0);
    CHECK(strstr(buf, "\"allow\":false") != NULL);
    CHECK(strstr(buf, "\"always\":false") != NULL);
    CHECK(strstr(buf, "\"esc\":false") != NULL);
}

static void test_build_perm_resp_mixed(void) {
    char buf[256];
    int n = protocol_build_perm_resp(buf, sizeof(buf), true, false, true);
    CHECK(n > 0);
    CHECK(strstr(buf, "\"allow\":true") != NULL);
    CHECK(strstr(buf, "\"always\":false") != NULL);
    CHECK(strstr(buf, "\"esc\":true") != NULL);
}

static void test_build_perm_resp_null_buf_returns_zero(void) {
    int n = protocol_build_perm_resp(NULL, 256, true, false, false);
    CHECK(n == 0);
}

/* ---------------------------------------------------------------------------
 * Simple builder functions (build_simple wrappers)
 * Each builder must:
 *   1. Embed the correct "t" value
 *   2. End with '\n'
 *   3. Return strlen(buf) bytes
 * ------------------------------------------------------------------------- */

#define TEST_SIMPLE_BUILDER(fn, type_str) \
    static void test_build_##fn(void) { \
        char buf[256]; \
        int n = protocol_build_##fn(buf, sizeof(buf)); \
        CHECK(n > 0); \
        CHECK(strstr(buf, "\"t\":\"" type_str "\"") != NULL); \
        CHECK(buf[n - 1] == '\n'); \
        CHECK(n == (int)strlen(buf)); \
    }

TEST_SIMPLE_BUILDER(enter,      "enter")
TEST_SIMPLE_BUILDER(esc,        "esc")
TEST_SIMPLE_BUILDER(pong,       "pong")
TEST_SIMPLE_BUILDER(down,       "down")
TEST_SIMPLE_BUILDER(voice,      "voice")
TEST_SIMPLE_BUILDER(interrupt,  "interrupt")
TEST_SIMPLE_BUILDER(backspace,  "backspace")
TEST_SIMPLE_BUILDER(yes,        "yes")
TEST_SIMPLE_BUILDER(pgup,       "pgup")
TEST_SIMPLE_BUILDER(pgdown,     "pgdown")
TEST_SIMPLE_BUILDER(ctrl_o,     "ctrl_o")
TEST_SIMPLE_BUILDER(ctrl_e,     "ctrl_e")
TEST_SIMPLE_BUILDER(shift_tab,  "shift_tab")

#define TEST_SIMPLE_BUILDER_SMALL_BUF(fn) \
    static void test_build_##fn##_small_buf(void) { \
        char buf[3]; \
        int n = protocol_build_##fn(buf, sizeof(buf)); \
        /* snprintf truncates and returns would-be length; just no crash */ \
        (void)n; \
        CHECK(1); \
    }

/* snprintf truncates gracefully — test that small buffers don't crash */
TEST_SIMPLE_BUILDER_SMALL_BUF(enter)
TEST_SIMPLE_BUILDER_SMALL_BUF(pong)

static void test_build_space_down(void) {
    char buf[256];
    int n = protocol_build_space_down(buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(strstr(buf, "\"t\":\"space_down\"") != NULL);
    CHECK(buf[n - 1] == '\n');
}

static void test_build_space_up(void) {
    char buf[256];
    int n = protocol_build_space_up(buf, sizeof(buf));
    CHECK(n > 0);
    CHECK(strstr(buf, "\"t\":\"space_up\"") != NULL);
    CHECK(buf[n - 1] == '\n');
}

/* ---------------------------------------------------------------------------
 * main
 * ------------------------------------------------------------------------- */

int main(void) {
    printf("protocol.c unit tests\n");
    printf("=====================\n");

    /* protocol_parse — notify */
    run_test("parse_notify_basic",                    test_parse_notify_basic);
    run_test("parse_notify_vibro_false",              test_parse_notify_vibro_false);
    run_test("parse_notify_missing_vibro_defaults",   test_parse_notify_missing_vibro_defaults_false);
    run_test("parse_notify_sound_truncated",          test_parse_notify_sound_truncated);

    /* protocol_parse — status */
    run_test("parse_status_both_lines",               test_parse_status_both_lines);
    run_test("parse_status_line2_absent",             test_parse_status_line2_absent);

    /* protocol_parse — menu */
    run_test("parse_menu",                            test_parse_menu);
    run_test("parse_menu_empty",                      test_parse_menu_empty);

    /* protocol_parse — state */
    run_test("parse_usage",                           test_parse_usage);
    run_test("parse_state_true",                      test_parse_state_true);
    run_test("parse_state_false",                     test_parse_state_false);

    /* protocol_parse — perm */
    run_test("parse_perm_tool_and_detail",            test_parse_perm_tool_and_detail);
    run_test("parse_perm_detail_absent",              test_parse_perm_detail_absent);

    /* protocol_parse — ping */
    run_test("parse_ping_with_rssi",                  test_parse_ping_with_rssi);
    run_test("parse_ping_without_rssi",               test_parse_ping_without_rssi);

    /* protocol_parse — field length boundary */
    run_test("parse_text_63_chars",                   test_parse_text_exactly_63_chars);
    run_test("parse_text_64_chars_truncated",         test_parse_text_64_chars_truncated_to_63);

    /* protocol_parse — error cases */
    run_test("parse_null_json",                       test_parse_null_json_returns_false);
    run_test("parse_null_msg",                        test_parse_null_msg_returns_false);
    run_test("parse_unknown_type",                    test_parse_unknown_type_returns_false);
    run_test("parse_missing_t_field",                 test_parse_missing_t_field_returns_false);
    run_test("parse_missing_d_field",                 test_parse_missing_d_field_returns_false);
    run_test("parse_garbage_no_crash",                test_parse_garbage_does_not_crash);
    run_test("parse_empty_string",                    test_parse_empty_string_returns_false);

    /* protocol_build_hello */
    run_test("build_hello_normal_name",               test_build_hello_normal_name);
    run_test("build_hello_escapes_double_quote",      test_build_hello_escapes_double_quote);
    run_test("build_hello_escapes_backslash",         test_build_hello_escapes_backslash);
    run_test("build_hello_null_name_empty_bt",        test_build_hello_null_name_gives_empty_bt);
    run_test("build_hello_buf_too_small",             test_build_hello_buf_too_small_returns_zero);

    /* protocol_build_cmd */
    run_test("build_cmd_normal",                      test_build_cmd_normal);
    run_test("build_cmd_escapes_special_chars",       test_build_cmd_escapes_special_chars);
    run_test("build_cmd_null_text",                   test_build_cmd_null_text_gives_empty);
    run_test("build_cmd_buf_too_small",               test_build_cmd_buf_too_small_returns_zero);
    run_test("build_cmd_return_value_strlen",         test_build_cmd_return_value_equals_strlen);

    /* protocol_build_perm_resp */
    run_test("build_perm_resp_all_true",              test_build_perm_resp_all_true);
    run_test("build_perm_resp_all_false",             test_build_perm_resp_all_false);
    run_test("build_perm_resp_mixed",                 test_build_perm_resp_mixed);
    run_test("build_perm_resp_null_buf",              test_build_perm_resp_null_buf_returns_zero);

    /* simple builders */
    run_test("build_enter",      test_build_enter);
    run_test("build_esc",        test_build_esc);
    run_test("build_pong",       test_build_pong);
    run_test("build_down",       test_build_down);
    run_test("build_voice",      test_build_voice);
    run_test("build_interrupt",  test_build_interrupt);
    run_test("build_backspace",  test_build_backspace);
    run_test("build_yes",        test_build_yes);
    run_test("build_pgup",       test_build_pgup);
    run_test("build_pgdown",     test_build_pgdown);
    run_test("build_ctrl_o",     test_build_ctrl_o);
    run_test("build_ctrl_e",     test_build_ctrl_e);
    run_test("build_shift_tab",  test_build_shift_tab);
    run_test("build_space_down", test_build_space_down);
    run_test("build_space_up",   test_build_space_up);
    run_test("build_enter_small_buf", test_build_enter_small_buf);
    run_test("build_pong_small_buf",  test_build_pong_small_buf);

    printf("\n%d passed, %d failed\n", pass_count, fail_count);
    return fail_count ? 1 : 0;
}
