import onnx
import onnxruntime as ort
import numpy as np


if __name__ == '__main__':
    input_onnx = "./decoder_model.onnx"
    output_onnx = "./decoder_model_logits_only.onnx"
    log_file = "./decoder_model_logits_only.log.txt"

    model = onnx.load(input_onnx)
    graph = model.graph

    log_lines = []
    log_lines.append("=== LOGITS-ONLY EXPORT LOG ===")
    log_lines.append(f"Input model: {input_onnx}")
    log_lines.append(f"Output model: {output_onnx}")
    log_lines.append("")

    print("Original outputs:")
    log_lines.append("ORIGINAL OUTPUTS:")
    for out in graph.output:
        print(" ", out.name)
        log_lines.append(f'  name="{out.name}"')

    if len(graph.output) == 0:
        raise ValueError("Model has no outputs")

    first_output = graph.output[0]
    kept_output_name = first_output.name

    removed_outputs = []
    for out in graph.output[1:]:
        removed_outputs.append(out.name)

    while len(graph.output) > 0:
        graph.output.pop()

    graph.output.append(first_output)

    print("New outputs:")
    log_lines.append("")
    log_lines.append("NEW OUTPUTS:")
    for out in graph.output:
        print(" ", out.name)
        log_lines.append(f'  name="{out.name}"')

    log_lines.append("")
    log_lines.append("CHANGES:")
    log_lines.append(f'  kept_output="{kept_output_name}"')
    if len(removed_outputs) == 0:
        log_lines.append("  removed_outputs=none")
    else:
        for name in removed_outputs:
            log_lines.append(f'  removed_output="{name}"')

    onnx.checker.check_model(model)
    print("ONNX checker passed")
    log_lines.append("ONNX checker passed")

    onnx.save(model, output_onnx)
    print("Saved modified model to:", output_onnx)
    log_lines.append(f'Saved modified model: "{output_onnx}"')

    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print("Saved log file to:", log_file)

    sess = ort.InferenceSession(output_onnx, providers=['CPUExecutionProvider'])
    print("Modified model loaded in ONNX Runtime")
    print("finished")
