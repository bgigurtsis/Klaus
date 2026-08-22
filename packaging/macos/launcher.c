#include <errno.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void show_start_error(void) {
    const char *script =
        "display alert \"Klaus could not start\" "
        "message \"Its Python environment is missing. Reinstall the app from "
        "the Klaus checkout.\" as critical";
    execl("/usr/bin/osascript", "osascript", "-e", script, NULL);
}

static int path_from_format(char *destination, size_t size, const char *format,
                            const char *value) {
    int written = snprintf(destination, size, format, value);
    return written >= 0 && (size_t)written < size;
}

int main(void) {
    char executable_path[PATH_MAX];
    uint32_t executable_size = sizeof(executable_path);
    if (_NSGetExecutablePath(executable_path, &executable_size) != 0) {
        show_start_error();
        return 1;
    }

    char *bundle_suffix = strstr(executable_path, "/Contents/MacOS/");
    if (bundle_suffix == NULL) {
        show_start_error();
        return 1;
    }
    *bundle_suffix = '\0';

    char source_file[PATH_MAX];
    if (!path_from_format(source_file, sizeof(source_file),
                          "%s/Contents/Resources/source-root", executable_path)) {
        show_start_error();
        return 1;
    }

    FILE *source_handle = fopen(source_file, "r");
    char source_root[PATH_MAX];
    if (source_handle == NULL ||
        fgets(source_root, sizeof(source_root), source_handle) == NULL) {
        if (source_handle != NULL) {
            fclose(source_handle);
        }
        show_start_error();
        return 1;
    }
    fclose(source_handle);
    source_root[strcspn(source_root, "\r\n")] = '\0';

    char klaus_executable[PATH_MAX];
    if (!path_from_format(klaus_executable, sizeof(klaus_executable),
                          "%s/.venv/bin/klaus", source_root) ||
        access(klaus_executable, X_OK) != 0) {
        show_start_error();
        return 1;
    }

    const char *home = getenv("HOME");
    if (home != NULL) {
        char log_dir[PATH_MAX];
        char log_file[PATH_MAX];
        if (path_from_format(log_dir, sizeof(log_dir),
                             "%s/Library/Logs/Klaus", home) &&
            path_from_format(log_file, sizeof(log_file),
                             "%s/Library/Logs/Klaus/Klaus.log", home)) {
            if (mkdir(log_dir, 0700) == 0 || errno == EEXIST) {
                FILE *log_handle = fopen(log_file, "a");
                if (log_handle != NULL) {
                    dup2(fileno(log_handle), STDOUT_FILENO);
                    dup2(fileno(log_handle), STDERR_FILENO);
                    fclose(log_handle);
                }
            }
        }
    }

    if (chdir(source_root) != 0) {
        perror("Could not open the Klaus checkout");
        show_start_error();
        return 1;
    }

    char *const arguments[] = {klaus_executable, NULL};
    execv(klaus_executable, arguments);
    perror("Could not launch Klaus");
    show_start_error();
    return 1;
}
