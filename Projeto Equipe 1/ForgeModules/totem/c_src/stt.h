#ifndef STT_H
#define STT_H

#ifdef __cplusplus
extern "C"
{
#endif

#ifndef STT_API
#ifdef _WIN32
#define STT_API __declspec(dllexport)
#else
#define STT_API
#endif
#endif

    STT_API int stt_initialize(void);
    STT_API int stt_start_recording(void);
    STT_API char *stt_stop_recording_and_transcribe(void);
    STT_API void stt_free_transcription(char *value);
    STT_API int stt_is_recording(void);
    STT_API void stt_shutdown(void);

#ifdef __cplusplus
}
#endif

#endif // STT_H
