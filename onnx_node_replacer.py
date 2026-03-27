import onnx
import onnxruntime as ort
import numpy as np


if __name__ == '__main__':
    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------
    input_onnx = "./best_eval_epoch_49_decoder_single_legalized_DeleteExpandConstant_GemmToMatMul_surgeon_int64_modi.onnx"
    output_onnx = "./best_eval_epoch_49_decoder_single_legalized_DeleteExpandConstant_GemmToMatMul_surgeon_int64_modi_gather_replaced.onnx"
    log_file = "./best_eval_epoch_49_decoder_single_legalized_DeleteExpandConstant_GemmToMatMul_surgeon_int64_modi_gather_replaced.log.txt"

    # ------------------------------------------------------------------
    # Replacement input information
    #
    # This new input replaces the output of Gather_11.
    # From your description, the Gather output shape is [1,1,256]
    # and dtype is float32.
    # ------------------------------------------------------------------
    new_input_name = "embedded_token"
    new_input_shape = [1, 1, 256]
    new_input_dtype = onnx.TensorProto.FLOAT

    # ------------------------------------------------------------------
    # Target Gather node information
    #
    # We try by exact node name first.
    # If your model uses a slightly different name, you can adjust it.
    # ------------------------------------------------------------------
    target_gather_name = "Gather_11"

    # ------------------------------------------------------------------
    # Load model
    # ------------------------------------------------------------------
    model = onnx.load(input_onnx)
    graph = model.graph

    # ------------------------------------------------------------------
    # Prepare log
    # ------------------------------------------------------------------
    log_lines = []
    log_lines.append("=== GATHER REPLACEMENT LOG ===")
    log_lines.append(f"Input model: {input_onnx}")
    log_lines.append(f"Output model: {output_onnx}")
    log_lines.append(f"Target Gather node: {target_gather_name}")
    log_lines.append("")

    # ------------------------------------------------------------------
    # Add the new graph input
    # ------------------------------------------------------------------
    new_input = onnx.helper.make_tensor_value_info(
        new_input_name,
        new_input_dtype,
        new_input_shape
    )
    graph.input.append(new_input)

    print(f'Added new input "{new_input_name}" with shape {new_input_shape}')
    log_lines.append(
        f'ADDED INPUT: name="{new_input_name}", dtype=FLOAT, shape={new_input_shape}'
    )
    log_lines.append("")

    # ------------------------------------------------------------------
    # Find the target Gather node
    # ------------------------------------------------------------------
    target_gather = None

    for node in graph.node:
        if node.op_type == "Gather" and node.name == target_gather_name:
            target_gather = node
            break

    # ------------------------------------------------------------------
    # Fallback: if exact node name was not found, try to locate the Gather
    # by its known inputs/outputs from your description.
    # ------------------------------------------------------------------
    if target_gather is None:
        for node in graph.node:
            if node.op_type != "Gather":
                continue

            input_0 = node.input[0] if len(node.input) > 0 else ""
            input_1 = node.input[1] if len(node.input) > 1 else ""
            output_0 = node.output[0] if len(node.output) > 0 else ""

            if input_0 == "decoder.emb.weight" and output_0 == "onnx::Reshape_29":
                target_gather = node
                break

    if target_gather is None:
        raise ValueError(
            'Could not find target Gather node. '
            'Tried exact name "Gather_11" and fallback match '
            '(decoder.emb.weight -> onnx::Reshape_29).'
        )

    gather_name = target_gather.name if target_gather.name else "<unnamed_gather>"
    gather_input_0 = target_gather.input[0] if len(target_gather.input) > 0 else "<none>"
    gather_input_1 = target_gather.input[1] if len(target_gather.input) > 1 else "<none>"
    gather_output = target_gather.output[0] if len(target_gather.output) > 0 else "<none>"

    print(f'Found Gather node "{gather_name}"')
    print("  input[0]:", gather_input_0)
    print("  input[1]:", gather_input_1)
    print("  output[0]:", gather_output)

    log_lines.append("TARGET NODE FOUND:")
    log_lines.append(f'  node_name="{gather_name}"')
    log_lines.append(f'  op_type="Gather"')
    log_lines.append(f'  input_0="{gather_input_0}"')
    log_lines.append(f'  input_1="{gather_input_1}"')
    log_lines.append(f'  output_0="{gather_output}"')
    log_lines.append("")

    # ------------------------------------------------------------------
    # Rewire all downstream consumers:
    # Any node that used the Gather output will now use embedded_token.
    # ------------------------------------------------------------------
    rewired_consumers = []

    for node in graph.node:
        if node is target_gather:
            continue

        for i in range(len(node.input)):
            if node.input[i] == gather_output:
                old_input = node.input[i]
                node.input[i] = new_input_name

                consumer_name = node.name if node.name else "<unnamed_node>"
                rewired_consumers.append(
                    (consumer_name, node.op_type, i, old_input, new_input_name)
                )

                print(
                    f'Rewired node "{consumer_name}" input index {i}: '
                    f'{old_input} -> {new_input_name}'
                )

    log_lines.append("REWIRED CONSUMERS:")
    if len(rewired_consumers) == 0:
        log_lines.append("  none")
    else:
        for consumer_name, op_type, input_index, old_input, new_input_used in rewired_consumers:
            log_lines.append(
                f'  node="{consumer_name}", op="{op_type}", input_index={input_index}, '
                f'old_tensor="{old_input}", new_tensor="{new_input_used}"'
            )
    log_lines.append("")

    # ------------------------------------------------------------------
    # Remove the Gather node
    # ------------------------------------------------------------------
    graph.node.remove(target_gather)

    print(f'Removed Gather node "{gather_name}"')

    log_lines.append("REMOVED NODE:")
    log_lines.append(f'  node_name="{gather_name}"')
    log_lines.append(f'  op_type="Gather"')
    log_lines.append("")
    log_lines.append("REPLACEMENT:")
    log_lines.append(f'  removed_output_tensor="{gather_output}"')
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
    # Optional: try loading in ONNX Runtime
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