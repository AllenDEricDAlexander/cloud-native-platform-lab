// C/C++ 共用无第三方依赖的实验 HTTP 适配；计算内核分别构建和测试。
#ifndef CNPL_HTTP_H
#define CNPL_HTTP_H
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping = 0;
static void stop_server(int value) { (void)value; stopping = 1; }
static int serve(int (*calculate)(int)) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = stop_server;
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    if (listener < 0) return 1;
    int reuse = 1;
    setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(8080);
    if (bind(listener, (struct sockaddr *)&addr, sizeof(addr)) || listen(listener, 16)) { close(listener); return 1; }
    unsigned long good = 0, bad = 0;
    while (!stopping) {
        int client = accept(listener, NULL, NULL);
        if (client < 0) { if (errno == EINTR) continue; close(listener); return 1; }
        struct timeval timeout = {2, 0};
        setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        char request[4096] = {0}, path[256] = {0}, body[1024] = {0}, response[1536];
        ssize_t read_bytes = recv(client, request, sizeof(request)-1, 0);
        if (read_bytes <= 0 || sscanf(request, "GET %255s", path) != 1) { close(client); continue; }
        int status = 200;
        const char *type = "application/json";
        if (!strcmp(path, "/health") || !strcmp(path, "/ready")) snprintf(body, sizeof(body), "{\"status\":\"ok\"}");
        else if (!strcmp(path, "/version")) {
            char revision[64] = {0};
            FILE *file = fopen("/app/revision", "r");
            if (!file || !fgets(revision, sizeof(revision), file)) { status = 503; snprintf(body, sizeof(body), "{}"); }
            else { revision[strcspn(revision, "\r\n")] = 0; snprintf(body, sizeof(body), "{\"revision\":\"%s\"}", revision); }
            if (file) fclose(file);
        } else if (!strcmp(path, "/metrics")) {
            type = "text/plain";
            snprintf(body, sizeof(body), "http_requests_total{status=\"200\"} %lu\nhttp_requests_total{status=\"500\"} %lu\n", good, bad);
        } else if (!strcmp(path, "/compute")) {
            const char *failed = getenv("FAIL_REQUESTS");
            if (failed && !strcmp(failed,"true")) { status = 500; bad++; } else good++;
            snprintf(body, sizeof(body), "{\"value\":%d}", calculate(7));
        } else { status = 404; snprintf(body, sizeof(body), "{}"); }
        int bytes = snprintf(response, sizeof(response), "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s", status, status==200 ? "OK" : "Error", type, strlen(body), body);
        if (bytes > 0 && (size_t)bytes < sizeof(response)) {
            size_t sent = 0;
            while (sent < (size_t)bytes) { ssize_t n=send(client,response+sent,(size_t)bytes-sent,0); if(n<=0) break; sent+=(size_t)n; }
        }
        printf("{\"event\":\"request\",\"status\":%d}\n", status); fflush(stdout);
        close(client);
    }
    close(listener);
    return 0;
}
#endif
