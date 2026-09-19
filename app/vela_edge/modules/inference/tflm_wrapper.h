/* TFLite Micro C wrapper — isolates NuttX from C++ TFLite headers */
#ifndef TFLM_WRAPPER_H
#define TFLM_WRAPPER_H

#ifdef __cplusplus
extern "C" {
#endif

/* Initialize TFLite interpreter with model data. Returns 0 on success, -1 on bad schema, -2 on alloc failure. */
int tflm_init(const unsigned char *model_data, unsigned int model_len);

/* Run inference: returns 0 on success */
int tflm_invoke(void);

/* Get input tensor raw pointer (cast to int8_t* or float* based on model) */
void *tflm_get_input(int index);

/* Get input tensor size in bytes */
int tflm_get_input_size(int index);

/* Get output tensor raw pointer (cast to int8_t* for INT8 models) */
const void *tflm_get_output(int index);

/* Get output tensor size in bytes */
int tflm_get_output_bytes(int index);

/* Get output quantization params for dequantization: float = (int8 - zp) * scale */
float tflm_get_output_scale(int index);
int tflm_get_output_zero_point(int index);

#ifdef __cplusplus
}
#endif

#endif /* TFLM_WRAPPER_H */
