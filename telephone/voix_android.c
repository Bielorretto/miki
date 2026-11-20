/*
 * voix_android : micro + haut-parleur Android en mode « appel » (VOICE_COMMUNICATION).
 *
 * Dans ce mode, Android applique SON anti-écho (celui des appels WhatsApp) : il connaît le délai exact
 * entre le haut-parleur et le micro, ce que notre anti-écho logiciel doit deviner.
 *
 *   stdout ← micro    : PCM 16 bits, mono, 48 kHz (déjà débarrassé de l'écho par Android)
 *   stdin  → haut-parleur : PCM 16 bits, mono, 48 kHz
 *
 * Compilation (dans Termux) :  clang -O2 -o voix_android voix_android.c -laaudio -lpthread
 * Options : --usage media|appel  (usage du haut-parleur, défaut appel)
 */
#include <aaudio/AAudio.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define RATE 48000
#define BLOC 480 /* 10 ms */

static AAudioStream *entree, *sortie;
static volatile int fini = 0;

static void verifier(aaudio_result_t r, const char *quoi) {
    if (r != AAUDIO_OK) {
        fprintf(stderr, "voix_android : %s : %s\n", quoi, AAudio_convertResultToText(r));
        exit(1);
    }
}

static void *lire_micro(void *arg) {
    (void)arg;
    int16_t buf[BLOC];
    while (!fini) {
        aaudio_result_t n = AAudioStream_read(entree, buf, BLOC, 1000000000LL);
        if (n < 0) {
            fprintf(stderr, "voix_android : lecture micro : %s\n", AAudio_convertResultToText(n));
            break;
        }
        if (n > 0 && fwrite(buf, sizeof(int16_t), (size_t)n, stdout) != (size_t)n) break;
        fflush(stdout);
    }
    fini = 1;
    return NULL;
}

int main(int argc, char **argv) {
    int usage_appel = 1;
    for (int i = 1; i < argc; i++)
        if (!strcmp(argv[i], "--usage") && i + 1 < argc) usage_appel = strcmp(argv[++i], "media") != 0;
    signal(SIGPIPE, SIG_IGN);

    AAudioStreamBuilder *b;
    /* Haut-parleur d'abord : sa session sert de référence à l'anti-écho. */
    verifier(AAudio_createStreamBuilder(&b), "builder");
    AAudioStreamBuilder_setDirection(b, AAUDIO_DIRECTION_OUTPUT);
    AAudioStreamBuilder_setSampleRate(b, RATE);
    AAudioStreamBuilder_setChannelCount(b, 1);
    AAudioStreamBuilder_setFormat(b, AAUDIO_FORMAT_PCM_I16);
    AAudioStreamBuilder_setUsage(b, usage_appel ? AAUDIO_USAGE_VOICE_COMMUNICATION : AAUDIO_USAGE_MEDIA);
    AAudioStreamBuilder_setContentType(b, AAUDIO_CONTENT_TYPE_SPEECH);
    AAudioStreamBuilder_setSessionId(b, AAUDIO_SESSION_ID_ALLOCATE);
    verifier(AAudioStreamBuilder_openStream(b, &sortie), "ouverture haut-parleur");
    AAudioStreamBuilder_delete(b);

    verifier(AAudio_createStreamBuilder(&b), "builder");
    AAudioStreamBuilder_setDirection(b, AAUDIO_DIRECTION_INPUT);
    AAudioStreamBuilder_setSampleRate(b, RATE);
    AAudioStreamBuilder_setChannelCount(b, 1);
    AAudioStreamBuilder_setFormat(b, AAUDIO_FORMAT_PCM_I16);
    /* Le mode qui active l'anti-écho, l'anti-bruit et le gain automatique d'Android. */
    AAudioStreamBuilder_setInputPreset(b, AAUDIO_INPUT_PRESET_VOICE_COMMUNICATION);
    AAudioStreamBuilder_setSessionId(b, AAUDIO_SESSION_ID_ALLOCATE);
    verifier(AAudioStreamBuilder_openStream(b, &entree), "ouverture micro");
    AAudioStreamBuilder_delete(b);

    fprintf(stderr, "voix_android : micro %d Hz (preset %d, session %d) · haut-parleur %d Hz (usage %s)\n",
            AAudioStream_getSampleRate(entree), AAudioStream_getInputPreset(entree), AAudioStream_getSessionId(entree),
            AAudioStream_getSampleRate(sortie), usage_appel ? "appel" : "media");

    verifier(AAudioStream_requestStart(sortie), "démarrage haut-parleur");
    verifier(AAudioStream_requestStart(entree), "démarrage micro");

    pthread_t t;
    pthread_create(&t, NULL, lire_micro, NULL);

    int16_t buf[BLOC];
    while (!fini) {
        size_t n = fread(buf, sizeof(int16_t), BLOC, stdin);
        if (n == 0) break;
        aaudio_result_t r = AAudioStream_write(sortie, buf, (int32_t)n, 1000000000LL);
        if (r < 0) {
            fprintf(stderr, "voix_android : écriture haut-parleur : %s\n", AAudio_convertResultToText(r));
            break;
        }
    }
    fini = 1;
    AAudioStream_requestStop(entree);
    AAudioStream_requestStop(sortie);
    pthread_join(t, NULL);
    AAudioStream_close(entree);
    AAudioStream_close(sortie);
    return 0;
}
