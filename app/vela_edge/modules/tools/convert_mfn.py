"""
MobileFaceNet Keras .pb → TFLite INT8 → C array
Converts pre-trained model for ESP32-S3 deployment.
"""
import tensorflow as tf
import numpy as np
import os

PB_PATH = r"C:\Users\Fly费\Documents\Downloads\新建文件夹-260518-180245691\MobileFaceNet_TF\arch\pretrained_model\MobileFaceNet_9925_9680.pb"
OUT_DIR = r"C:\Users\Fly费\Documents\Downloads\新建文件夹-260518-180245691\face_embedding_app"

def main():
    # 1. Load frozen graph
    print("[1/4] Loading frozen graph...")
    with tf.io.gfile.GFile(PB_PATH, 'rb') as f:
        graph_def = tf.compat.v1.GraphDef()
        graph_def.ParseFromString(f.read())
    
    with tf.Graph().as_default() as graph:
        tf.import_graph_def(graph_def, name='')
    
    print(f"  Graph loaded. Operations: {len(graph.get_operations())}")
    
    # Print input/output nodes
    for op in graph.get_operations():
        if 'input' in op.name.lower() or 'output' in op.name.lower() or 'embedding' in op.name.lower():
            print(f"  Op: {op.name} ({op.type})")
    
    # 2. Convert to TFLite (float32 first, then quantize)
    print("\n[2/4] Converting to TFLite...")
    converter = tf.compat.v1.lite.TFLiteConverter.from_frozen_graph(
        PB_PATH,
        input_arrays=['input'],          # MobileFaceNet input layer
        output_arrays=['embeddings'],    # MobileFaceNet output layer (128-d)
        input_shapes={'input': [1, 112, 112, 3]}
    )
    
    # Enable optimizations (INT8 quantization)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.target_spec.supported_types = [tf.int8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    
    # Representative dataset for calibration
    def representative_dataset():
        for _ in range(100):
            data = np.random.randn(1, 112, 112, 3).astype(np.float32)
            yield [data]
    converter.representative_dataset = representative_dataset
    
    tflite_model = converter.convert()
    print(f"  TFLite model: {len(tflite_model)} bytes ({len(tflite_model)/1024:.1f} KB)")
    
    # Save
    tflite_path = os.path.join(OUT_DIR, "mobilefacenet_int8.tflite")
    with open(tflite_path, 'wb') as f:
        f.write(tflite_model)
    print(f"  Saved: {tflite_path}")
    
    # 3. Generate C array (xxd -i equivalent)
    print("\n[3/4] Generating C array...")
    lines = []
    lines.append('/* Auto-generated from MobileFaceNet INT8 quantized model */\n')
    lines.append('#include <stdint.h>\n\n')
    lines.append('alignas(16) const unsigned char g_model_data[] = {')
    
    for i in range(0, len(tflite_model), 12):
        chunk = tflite_model[i:i+12]
        hex_str = ', '.join(f'0x{b:02x}' for b in chunk)
        if i + 12 < len(tflite_model):
            lines.append(f'  {hex_str},')
        else:
            lines.append(f'  {hex_str}')
    
    lines.append('};\n')
    lines.append(f'const unsigned int g_model_data_len = {len(tflite_model)};\n')
    
    cc_content = ''.join(lines)
    cc_path = os.path.join(OUT_DIR, "model_data.cc")
    with open(cc_path, 'w') as f:
        f.write(cc_content)
    
    print(f"  C array: {len(cc_content)} chars")
    print(f"  Saved: {cc_path}")
    
    # 4. Verify
    print("\n[4/4] Verifying model...")
    interpreter = tf.lite.Interpreter(model_content=tflite_model)
    interpreter.allocate_tensors()
    
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    
    print(f"  Input:  {input_details[0]['shape']} ({input_details[0]['dtype']})")
    print(f"  Output: {output_details[0]['shape']} ({output_details[0]['dtype']})")
    
    # Check output is 128-d
    out_shape = output_details[0]['shape']
    if out_shape[-1] == 128:
        print("  ✅ Output is 128-d embedding — correct for MobileFaceNet!")
    else:
        print(f"  ⚠️  Output dim is {out_shape[-1]}, expected 128")
    
    print("\n✅ Conversion complete!")

if __name__ == '__main__':
    main()
