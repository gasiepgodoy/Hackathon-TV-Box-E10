#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>
#include <cjson/cJSON.h>
#include <time.h>
#include <stdbool.h>

#define USER_INPUT_SIZE 1024 // renamed from MAX_INPUT to avoid conflict
#define END_SENTINEL "<<END>>\n"
#define MAX_EMOTION_LINE 256
#define CURL_TIMEOUT_MS 30000L
#define CURL_CONNECT_TIMEOUT_MS 8000L
#define CURL_LOW_SPEED_LIMIT 10L
#define CURL_LOW_SPEED_TIME 10L

struct buffer
{
    char *data;
    size_t len;
    char *emotion_buf;
    size_t emotion_len;
    int emotion_done;
    char *response_accum;
    size_t response_accum_len;
};

#define MAX_HISTORY 10
#define MAX_SYSTEM_PROMPT 4096
#define DEFAULT_CHAT_MODEL "zai-glm-4.7"

char *history_roles[MAX_HISTORY];
char *history_contents[MAX_HISTORY];
int history_count = 0;

void add_to_history(const char *role, const char *content)
{
    if (history_count < MAX_HISTORY)
    {
        history_roles[history_count] = strdup(role);
        history_contents[history_count] = strdup(content);
        history_count++;
    }
    else
    {
        free(history_roles[0]);
        free(history_contents[0]);
        for (int i = 0; i < MAX_HISTORY - 1; i++)
        {
            history_roles[i] = history_roles[i + 1];
            history_contents[i] = history_contents[i + 1];
        }
        history_roles[MAX_HISTORY - 1] = strdup(role);
        history_contents[MAX_HISTORY - 1] = strdup(content);
    }
}

// Callback for streaming chunks; keeps partial lines intact between calls
size_t stream_cb(char *ptr, size_t size, size_t nmemb, void *userdata)
{
    struct buffer *buf = (struct buffer *)userdata;
    size_t chunk_size = size * nmemb;
    size_t new_len = buf->len + chunk_size;
    char *new_data = realloc(buf->data, new_len + 1);
    if (!new_data)
    {
        return 0; // abort on OOM
    }
    buf->data = new_data;
    memcpy(buf->data + buf->len, ptr, chunk_size);
    buf->len = new_len;
    buf->data[buf->len] = '\0';

    size_t processed = 0;
    while (processed < buf->len)
    {
        char *newline = memchr(buf->data + processed, '\n', buf->len - processed);
        if (!newline)
        {
            break; // keep partial line for next chunk
        }

        size_t line_len = (size_t)(newline - (buf->data + processed));
        char saved = buf->data[processed + line_len];
        buf->data[processed + line_len] = '\0';

        char *line = buf->data + processed;
        if (strncmp(line, "data: ", 6) == 0 && strcmp(line + 6, "[DONE]") != 0)
        {
            cJSON *obj = cJSON_Parse(line + 6);
            if (obj)
            {
                cJSON *choices = cJSON_GetObjectItem(obj, "choices");
                if (cJSON_IsArray(choices) && cJSON_GetArraySize(choices) > 0)
                {
                    cJSON *delta = cJSON_GetObjectItem(cJSON_GetArrayItem(choices, 0), "delta");
                    if (delta)
                    {
                        cJSON *content = cJSON_GetObjectItem(delta, "content");
                        if (cJSON_IsString(content))
                        {
                            const char *text = content->valuestring;

                            // Accumulate full response for memory
                            size_t text_len = strlen(text);
                            char *new_accum = realloc(buf->response_accum, buf->response_accum_len + text_len + 1);
                            if (new_accum)
                            {
                                buf->response_accum = new_accum;
                                strcpy(buf->response_accum + buf->response_accum_len, text);
                                buf->response_accum_len += text_len;
                            }

                            // If we haven't resolved emotion yet, accumulate until newline
                            if (!buf->emotion_done)
                            {
                                size_t text_len = strlen(text);
                                size_t new_len = buf->emotion_len + text_len;
                                if (new_len > MAX_EMOTION_LINE)
                                {
                                    // too long without newline; treat as normal text
                                    if (buf->emotion_buf && buf->emotion_len)
                                    {
                                        printf("%s", buf->emotion_buf);
                                        fflush(stdout);
                                    }
                                    buf->emotion_done = 1;
                                    buf->emotion_len = 0;
                                    free(buf->emotion_buf);
                                    buf->emotion_buf = NULL;
                                    printf("%s", text);
                                    fflush(stdout);
                                }
                                else
                                {
                                    char *new_emotion = realloc(buf->emotion_buf, new_len + 1);
                                    if (!new_emotion)
                                    {
                                        return 0;
                                    }
                                    buf->emotion_buf = new_emotion;
                                    memcpy(buf->emotion_buf + buf->emotion_len, text, text_len);
                                    buf->emotion_len = new_len;
                                    buf->emotion_buf[buf->emotion_len] = '\0';
                                }

                                char *nl = strchr(buf->emotion_buf, '\n');
                                if (nl)
                                {
                                    *nl = '\0';
                                    if (strncmp(buf->emotion_buf, "EMOTION:", 8) == 0)
                                    {
                                        const char *emo = buf->emotion_buf + 8;
                                        while (*emo == ' ')
                                            emo++;
                                        if (*emo)
                                        {
                                            printf("EMOTION:%s\n", emo);
                                            fflush(stdout);
                                        }
                                        // print remaining after newline (if any)
                                        const char *rest = nl + 1;
                                        if (*rest)
                                        {
                                            printf("%s", rest);
                                            fflush(stdout);
                                        }
                                    }
                                    else
                                    {
                                        // No emotion line; print what we have as text
                                        printf("%s\n", buf->emotion_buf);
                                        fflush(stdout);
                                    }

                                    buf->emotion_done = 1;
                                    buf->emotion_len = 0;
                                    free(buf->emotion_buf);
                                    buf->emotion_buf = NULL;
                                }
                            }
                            else
                            {
                                printf("%s", text);
                                fflush(stdout);
                            }
                        }
                    }
                }
                cJSON_Delete(obj);
            }
        }

        buf->data[processed + line_len] = saved;
        processed += line_len + 1; // move past the newline
    }

    // Preserve any partial line by shifting it to the start
    if (processed < buf->len)
    {
        size_t remaining = buf->len - processed;
        memmove(buf->data, buf->data + processed, remaining);
        buf->len = remaining;
    }
    else
    {
        buf->len = 0;
    }

    return chunk_size;
}

int main()
{
    CURL *curl;
    CURLcode res;
    struct curl_slist *headers = NULL;
    struct buffer buf = {NULL, 0, NULL, 0, 0, NULL, 0};

    const char *api_key = getenv("CEREBRAS_API_KEY");
    if (!api_key)
    {
        fprintf(stderr, "Set CEREBRAS_API_KEY environment variable!\n");
        return 1;
    }

    // Load optimized prompt
    char system_prompt_text[MAX_SYSTEM_PROMPT] = "Você é a Mina AI.";
    FILE *pf = fopen("config/prompts.txt", "r");
    if (pf)
    {
        size_t n = fread(system_prompt_text, 1, sizeof(system_prompt_text) - 1, pf);
        system_prompt_text[n] = '\0';
        fclose(pf);
    }

    curl_global_init(CURL_GLOBAL_DEFAULT);
    curl = curl_easy_init();
    if (!curl)
        return 1;

    headers = curl_slist_append(headers, "Content-Type: application/json");
    char auth[256];
    snprintf(auth, sizeof(auth), "Authorization: Bearer %s", api_key);
    headers = curl_slist_append(headers, auth);

    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, stream_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &buf);
    curl_easy_setopt(curl, CURLOPT_TCP_NODELAY, 1L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, CURL_CONNECT_TIMEOUT_MS);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, CURL_TIMEOUT_MS);

    char input[USER_INPUT_SIZE];

    while (1)
    {
        if (!fgets(input, USER_INPUT_SIZE, stdin))
        {
            break;
        }

        input[strcspn(input, "\n")] = 0;
        if (strlen(input) == 0)
            continue;

        add_to_history("user", input);

        const char *chat_model = getenv("CEREBRAS_CHAT_MODEL");
        if (!chat_model || !*chat_model)
        {
            chat_model = DEFAULT_CHAT_MODEL;
        }

        cJSON *root = cJSON_CreateObject();
        cJSON_AddStringToObject(root, "model", chat_model);
        cJSON_AddBoolToObject(root, "stream", true);
        cJSON_AddNumberToObject(root, "temperature", 0.7);
        cJSON_AddNumberToObject(root, "max_tokens", 2048);

        cJSON *messages = cJSON_CreateArray();

        cJSON *sys_msg = cJSON_CreateObject();
        cJSON_AddStringToObject(sys_msg, "role", "system");
        cJSON_AddStringToObject(sys_msg, "content", system_prompt_text);
        cJSON_AddItemToArray(messages, sys_msg);

        for (int i = 0; i < history_count; i++)
        {
            cJSON *msg = cJSON_CreateObject();
            cJSON_AddStringToObject(msg, "role", history_roles[i]);
            cJSON_AddStringToObject(msg, "content", history_contents[i]);
            cJSON_AddItemToArray(messages, msg);
        }
        cJSON_AddItemToObject(root, "messages", messages);

        char *json_body = cJSON_PrintUnformatted(root);

        curl_easy_setopt(curl, CURLOPT_URL, "https://api.cerebras.ai/v1/chat/completions");
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body);

        buf.len = 0;
        free(buf.data);
        buf.data = NULL;
        buf.emotion_done = 0;
        buf.emotion_len = 0;
        free(buf.emotion_buf);
        buf.emotion_buf = NULL;
        free(buf.response_accum);
        buf.response_accum = NULL;
        buf.response_accum_len = 0;

        res = curl_easy_perform(curl);
        if (res != CURLE_OK)
        {
            fprintf(stderr, "Request failed: %s\n", curl_easy_strerror(res));
        }
        else if (buf.response_accum)
        {
            add_to_history("assistant", buf.response_accum);
        }

        printf("\n%s", END_SENTINEL);
        fflush(stdout);

        cJSON_Delete(root);
        free(json_body);
    }

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    curl_global_cleanup();
    free(buf.data);
    free(buf.emotion_buf);

    return 0;
}
