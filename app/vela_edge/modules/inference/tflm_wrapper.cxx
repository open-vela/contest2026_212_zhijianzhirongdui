/* TFLite Micro C wrapper v4 — fixed resolver (9 ops matching model), 2MB arena, diagnostics */
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tflm_wrapper.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>

#include <cstdarg>

extern "C" void DebugLog(const char* format, va_list args) { /* no-op */ }
extern "C" void MicroPrintf(const char* format, ...) { /* no-op stub */ }

/* 2MB arena from PSRAM heap — model has 404 tensors, INT8 dequant pattern needs space */
#define ARENA_SIZE (2048 * 1024)
static const tflite::Model *g_model = nullptr;
static tflite::MicroInterpreter *g_interpreter = nullptr;
static uint8_t *g_arena = nullptr;

extern "C" {
__attribute__((used)) int tflm_init(const unsigned char *model_data, unsigned int model_len) {
    if (g_arena) { free(g_arena); g_arena = nullptr; }

    /* Step 1: alloc arena */
    g_arena = (uint8_t *)malloc(ARENA_SIZE);
    if (!g_arena) {
        printf("TFLM: arena malloc(%d) FAILED\n", ARENA_SIZE);
        return -3;
    }
    printf("TFLM: arena=%p size=%d\n", (void*)g_arena, ARENA_SIZE);

    /* Step 2: parse model */
    g_model = tflite::GetModel(model_data);
    if (!g_model) {
        printf("TFLM: GetModel returned NULL\n");
        return -4;
    }
    printf("TFLM: model version=%d (schema=%d)\n",
           (int)g_model->version(), TFLITE_SCHEMA_VERSION);

    if (g_model->version() != TFLITE_SCHEMA_VERSION) {
        printf("TFLM: schema version mismatch!\n");
        return -1;
    }

    /* Step 3: register ops — model uses CONV_2D, DEPTHWISE_CONV_2D, RELU, MUL, ADD,
               RESHAPE, ABS, SUB, L2_NORMALIZATION (9 ops) */
    tflite::MicroMutableOpResolver<9> *resolver = new tflite::MicroMutableOpResolver<9>();
    printf("TFLM: registering ops...\n");

    resolver->AddConv2D();
    resolver->AddDepthwiseConv2D();
    resolver->AddRelu();
    resolver->AddMul();
    resolver->AddAdd();
    resolver->AddReshape();
    resolver->AddAbs();
    resolver->AddSub();
    resolver->AddL2Normalization();

    /* Step 4: init interpreter */
    printf("TFLM: creating interpreter (arena=%d bytes)...\n", ARENA_SIZE);
    tflite::MicroInterpreter *interpreter = new tflite::MicroInterpreter(g_model, *resolver, g_arena, ARENA_SIZE);
    g_interpreter = interpreter;

    /* Step 5: allocate tensors */
    printf("TFLM: AllocateTensors...\n");
    TfLiteStatus alloc_ret = g_interpreter->AllocateTensors();
    printf("TFLM: AllocateTensors returned %d (kTfLiteOk=%d, kTfLiteError=%d)\n",
           alloc_ret, kTfLiteOk, kTfLiteError);

    if (alloc_ret != kTfLiteOk) {
        printf("TFLM: AllocateTensors FAILED\n");
        return -2;
    }

    printf("TFLM: MobileFaceNet init OK\n");
    return 0;
}

__attribute__((used)) int tflm_invoke(void) {
    if (!g_interpreter) return -1;
    return (g_interpreter->Invoke() == kTfLiteOk) ? 0 : -2;
}

__attribute__((used)) void *tflm_get_input(int index) {
    if (!g_interpreter) return nullptr;
    TfLiteTensor* t = g_interpreter->input(index);
    return (t) ? t->data.data : nullptr;
}

__attribute__((used)) int tflm_get_input_size(int index) {
    if (!g_interpreter) return 0;
    TfLiteTensor* t = g_interpreter->input(index);
    return (t) ? t->bytes : 0;
}

__attribute__((used)) const void *tflm_get_output(int index) {
    if (!g_interpreter) return nullptr;
    TfLiteTensor* t = g_interpreter->output(index);
    return (t) ? t->data.data : nullptr;
}

__attribute__((used)) int tflm_get_output_bytes(int index) {
    if (!g_interpreter) return 0;
    TfLiteTensor* t = g_interpreter->output(index);
    return (t) ? t->bytes : 0;
}

__attribute__((used)) float tflm_get_output_scale(int index) {
    if (!g_interpreter) return 1.0f;
    TfLiteTensor* t = g_interpreter->output(index);
    return (t) ? t->params.scale : 1.0f;
}

__attribute__((used)) int tflm_get_output_zero_point(int index) {
    if (!g_interpreter) return 0;
    TfLiteTensor* t = g_interpreter->output(index);
    return (t) ? t->params.zero_point : 0;
}
}
