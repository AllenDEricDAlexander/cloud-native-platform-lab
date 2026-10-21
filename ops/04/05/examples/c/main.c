#define _POSIX_C_SOURCE 200809L
#include "http.h"
static int calculate(int value) { return value * value; }
int main(int argc, char **argv) {
    if (argc==2 && !strcmp(argv[1],"--self-test")) return calculate(7)==49 && calculate(-7)==49 && calculate(0)==0 ? 0 : 1;
    if (argc==2 && !strcmp(argv[1],"--native")) { printf("%d\n",calculate(7)); return 0; }
    return serve(calculate);
}
