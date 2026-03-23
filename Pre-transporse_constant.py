import onnx
import onnxruntime as ort
import numpy as np


if __name__ == '__main__':
    input_onnx = "./decoder_model.onnx"
    output_onnx = "./decoder_model_pretransposed_weights.onnx"
    log_file = "./decoder_model_pretransposed_weights.log.txt"

    model = onnx.load(input_onnx)
    graph = model.graph

    initializer_map = {}
    for init in graph.initializer:
        initializer_map[init.name] = init

    new_initializers = []
    nodes_to_remove = []

    rewired_matmuls = 0
    created_initializers = 0

    log_lines = []
    log_lines.append("=== PRE-TRANSPOSE WEIGHTS LOG ===")
    log_lines.append(f"Input model: {input_onnx}")
    log_lines.append(f"Output model: {output_onnx}")
    log_lines.append("")

    for transpose_node in graph.node:
        if transpose_node.op_type != "Transpose":
            continue

        if len(transpose_node.input) != 1 or len(transpose_node.output) != 1:
            continue

        input_name = transpose_node.input[0]
        output_name = transpose_node.output[0]
        transpose_name = transpose_node.name if transpose_node.name else "<unnamed_transpose>"

        if input_name not in initializer_map:
            continue

        perm = None
        for attr in transpose_node.attribute:
            if attr.name == "perm":
                perm = list(attr.ints)
                break

        weight_array = onnx.numpy_helper.to_array(initializer_map[input_name])

        if perm is None:
            perm = list(range(len(weight_array.shape) - 1, -1, -1))

        try:
            transposed_array = np.transpose(weight_array, axes=perm)
        except Exception as e:
            print(f'Skipping Transpose node "{transpose_name}": {e}')
            log_lines.append(f'SKIPPED TRANSPOSE: node="{transpose_name}", reason="{e}"')
            continue

        new_weight_name = input_name + "_pretransposed"

        if new_weight_name not in initializer_map:
            new_init = onnx.numpy_helper.from_array(transposed_array, name=new_weight_name)
            new_initializers.append(new_init)
            initializer_map[new_weight_name] = new_init
            created_initializers += 1

        rewired_users = []

        for node in graph.node:
            if node.op_type != "MatMul":
                continue

            for i in range(len(node.input)):
                if node.input[i] == output_name:
                    old_input = node.input[i]
                    node.input[i] = new_weight_name
                    rewired_matmuls += 1

                    consumer_name = node.name if node.name else "<unnamed_matmul>"
                    rewired_users.append((consumer_name, i, old_input, new_weight_name))

        if len(rewired_users) > 0:
            nodes_to_remove.append(transpose_node)

            print(f'Rewired MatMul users of Transpose node "{transpose_name}"')

            log_lines.append("TARGET NODE FOUND:")
            log_lines.append(f'  node_name="{transpose_name}"')
            log_lines.append(f'  op_type="Transpose"')
            log_lines.append(f'  input_0="{input_name}"')
            log_lines.append(f'  output_0="{output_name}"')
            log_lines.append(f'  perm={perm}')
            log_lines.append("")
            log_lines.append("REPLACEMENT:")
            log_lines.append(f'  replacement_initializer="{new_weight_name}"')
            log_lines.append(f'  replacement_shape={list(transposed_array.shape)}')
            log_lines.append(f'  replacement_dtype="{transposed_array.dtype}"')
            log_lines.append("")
            log_lines.append("REWIRED CONSUMERS:")
            for consumer_name, input_index, old_input, new_input in rewired_users:
                log_lines.append(
                    f'  node="{consumer_name}", op="MatMul", input_index={input_index}, '
                    f'old_tensor="{old_input}", new_tensor="{new_input}"'
                )
            log_lines.append("")
            log_lines.append("REMOVED NODE:")
            log_lines.append(f'  node_name="{transpose_name}"')
            log_lines.append(f'  op_type="Transpose"')
            log_lines.append("")

    for init in new_initializers:
        graph.initializer.append(init)

    for node in nodes_to_remove:
        graph.node.remove(node)

    print("Created initializers:", created_initializers)
    print("Rewired MatMuls:", rewired_matmuls)

    log_lines.append(f"Created initializers: {created_initializers}")
    log_lines.append(f"Rewired MatMuls: {rewired_matmuls}")

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
