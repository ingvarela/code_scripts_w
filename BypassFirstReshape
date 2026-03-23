import onnx
import onnxruntime as ort
import numpy as np


if __name__ == '__main__':
    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    input_onnx = "./decoder_model.onnx"
    output_onnx = "./decoder_model_bypass_first_reshape.onnx"
    log_file = "./decoder_model_bypass_first_reshape.log.txt"

    # ------------------------------------------------------------------
    # Configure target Reshape
    # ------------------------------------------------------------------
    TARGET_RESHAPE_NAME = None
    new_input_name = "post_embedding_tensor"
    new_input_shape = [1, 256]

    # ------------------------------------------------------------------
    # Load model
    # ------------------------------------------------------------------
    model = onnx.load(input_onnx)
    graph = model.graph

    # ------------------------------------------------------------------
    # Prepare log lines
    # ------------------------------------------------------------------
    log_lines = []
    log_lines.append("=== BYPASS FIRST RESHAPE LOG ===")
    log_lines.append(f"Input model: {input_onnx}")
    log_lines.append(f"Output model: {output_onnx}")
    log_lines.append("")

    # ------------------------------------------------------------------
    # Add new input
    # ------------------------------------------------------------------
    new_input = onnx.helper.make_tensor_value_info(
        new_input_name,
        onnx.TensorProto.FLOAT,
        new_input_shape
    )
    graph.input.append(new_input)

    print(f'Added new input "{new_input_name}" with shape {new_input_shape}')
    log_lines.append(f'ADDED INPUT: name="{new_input_name}", type=FLOAT, shape={new_input_shape}')
    log_lines.append("")

    # ------------------------------------------------------------------
    # Find target Reshape
    # ------------------------------------------------------------------
    target_reshape = None

    for node in graph.node:
        if node.op_type != "Reshape":
            continue

        if TARGET_RESHAPE_NAME is None:
            target_reshape = node
            break

        if node.name == TARGET_RESHAPE_NAME:
            target_reshape = node
            break

    if target_reshape is None:
        raise ValueError("Could not find target Reshape node")

    reshape_name = target_reshape.name if target_reshape.name else "<unnamed_reshape>"
    reshape_input_0 = target_reshape.input[0] if len(target_reshape.input) > 0 else "<none>"
    reshape_input_1 = target_reshape.input[1] if len(target_reshape.input) > 1 else "<none>"
    reshape_output = target_reshape.output[0]

    print(f'Found Reshape node "{reshape_name}"')
    print("Reshape output:", reshape_output)

    log_lines.append("TARGET NODE FOUND:")
    log_lines.append(f'  node_name="{reshape_name}"')
    log_lines.append(f'  op_type="Reshape"')
    log_lines.append(f'  data_input="{reshape_input_0}"')
    log_lines.append(f'  shape_input="{reshape_input_1}"')
    log_lines.append(f'  output_0="{reshape_output}"')
    log_lines.append("")

    # ------------------------------------------------------------------
    # Rewire downstream consumers
    # ------------------------------------------------------------------
    replaced_consumers = []

    for node in graph.node:
        if node is target_reshape:
            continue

        for i in range(len(node.input)):
            if node.input[i] == reshape_output:
                old_input = node.input[i]
                node.input[i] = new_input_name

                consumer_name = node.name if node.name else "<unnamed_node>"
                replaced_consumers.append((consumer_name, node.op_type, i, old_input, new_input_name))

                print(f'Rewired node "{consumer_name}" input index {i}: {old_input} -> {new_input_name}')

    log_lines.append("REWIRED CONSUMERS:")
    if len(replaced_consumers) == 0:
        log_lines.append("  none")
    else:
        for consumer_name, op_type, input_index, old_input, new_input in replaced_consumers:
            log_lines.append(
                f'  node="{consumer_name}", op="{op_type}", input_index={input_index}, '
                f'old_tensor="{old_input}", new_tensor="{new_input}"'
            )
    log_lines.append("")

    # ------------------------------------------------------------------
    # Remove Reshape node
    # ------------------------------------------------------------------
    graph.node.remove(target_reshape)
    print(f'Removed Reshape node "{reshape_name}"')

    log_lines.append("REMOVED NODE:")
    log_lines.append(f'  node_name="{reshape_name}"')
    log_lines.append(f'  op_type="Reshape"')
    log_lines.append("")
    log_lines.append("REPLACEMENT:")
    log_lines.append(f'  removed_output_tensor="{reshape_output}"')
    log_lines.append(f'  replacement_input="{new_input_name}"')
    log_lines.append("")

    # ------------------------------------------------------------------
    # Validate and save
    # ------------------------------------------------------------------
    onnx.checker.check_model(model)
    print("ONNX checker passed")
    log_lines.append("ONNX checker passed")

    onnx.save(model, output_onnx)
    print("Saved modified model to:", output_onnx)
    log_lines.append(f'Saved modified model: "{output_onnx}"')

    # ------------------------------------------------------------------
    # Write log file
    # ------------------------------------------------------------------
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))

    print("Saved log file to:", log_file)

    # ------------------------------------------------------------------
    # Optional ORT load check
    # ------------------------------------------------------------------
    sess = ort.InferenceSession(output_onnx, providers=['CPUExecutionProvider'])
    print("Modified model loaded in ONNX Runtime")
    print("Inputs:")
    for inp in sess.get_inputs():
        print(" ", inp.name, inp.shape, inp.type)

    print("Outputs:")
    for out in sess.get_outputs():
        print(" ", out.name, out.shape, out.type)

    print("finished")
