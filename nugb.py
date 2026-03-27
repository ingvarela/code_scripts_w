import onnx
from onnx import shape_inference, numpy_helper, TensorProto


if __name__ == '__main__':
    # ============================================================
    # CONFIGURATION
    # ============================================================
    onnx_file = "./best_eval_epoch_49_decoder_single_legalized_DeleteExpandConstant_GemmToMatMul_surgeon_int64_modi.onnx"
    start_tensor_name = "input:1"
    report_file = "./token_path_verifier_report.txt"

    # If True, traversal continues through many layout/helper ops.
    # If False, it stops earlier at "terminal" semantic ops.
    follow_layout_ops = True

    # ============================================================
    # HELPERS
    # ============================================================
    def dtype_name(dtype):
        if dtype is None:
            return "unknown"
        try:
            return TensorProto.DataType.Name(dtype)
        except Exception:
            return str(dtype)

    def shape_to_str(shape):
        if shape is None:
            return "unknown"
        return "[" + ", ".join(str(x) for x in shape) + "]"

    def get_vi_shape(vi):
        t = vi.type.tensor_type
        shape = []
        for d in t.shape.dim:
            if d.HasField("dim_value"):
                shape.append(d.dim_value)
            elif d.HasField("dim_param"):
                shape.append(d.dim_param)
            else:
                shape.append("?")
        return shape

    def get_vi_dtype(vi):
        return vi.type.tensor_type.elem_type

    def collect_tensor_info(model):
        info = {}
        for vi in list(model.graph.input) + list(model.graph.output) + list(model.graph.value_info):
            info[vi.name] = {
                "shape": get_vi_shape(vi),
                "dtype": get_vi_dtype(vi),
                "source": "value_info",
            }
        for init in model.graph.initializer:
            arr = numpy_helper.to_array(init)
            info[init.name] = {
                "shape": list(arr.shape),
                "dtype": init.data_type,
                "source": "initializer",
            }
        return info

    def get_attr(node, name, default=None):
        for a in node.attribute:
            if a.name != name:
                continue
            if a.type == onnx.AttributeProto.INT:
                return a.i
            if a.type == onnx.AttributeProto.INTS:
                return list(a.ints)
            if a.type == onnx.AttributeProto.FLOAT:
                return a.f
            if a.type == onnx.AttributeProto.STRING:
                return a.s
            if a.type == onnx.AttributeProto.TENSOR:
                return numpy_helper.to_array(a.t)
        return default

    def is_integer_dtype(dtype):
        return dtype in {
            TensorProto.INT8, TensorProto.INT16, TensorProto.INT32, TensorProto.INT64,
            TensorProto.UINT8, TensorProto.UINT16, TensorProto.UINT32, TensorProto.UINT64
        }

    def load_initializer_array(name, init_map):
        if name not in init_map:
            return None
        return numpy_helper.to_array(init_map[name])

    # ============================================================
    # LOAD MODEL + SHAPE INFERENCE
    # ============================================================
    model = onnx.load(onnx_file)

    try:
        inferred = shape_inference.infer_shapes(model)
        print("Shape inference: PASS")
    except Exception as e:
        inferred = model
        print("Shape inference: FAIL")
        print(e)

    tensor_info = collect_tensor_info(inferred)
    init_map = {x.name: x for x in inferred.graph.initializer}

    # ============================================================
    # BUILD CONSUMER MAP
    # ============================================================
    consumers = {}
    for node in inferred.graph.node:
        for inp in node.input:
            if inp not in consumers:
                consumers[inp] = []
            consumers[inp].append(node)

    # ============================================================
    # DEFINE WHICH OPS TO FOLLOW
    # ============================================================
    passthrough_ops = {
        "Cast",
        "Identity",
        "Reshape",
        "Squeeze",
        "Unsqueeze",
        "Flatten",
        "Transpose",
        "Concat",
        "Split",
        "Slice",
        "Expand",
        "Tile",
        "ConstantOfShape",
        "Shape",
    }

    terminal_ops = {
        "Gather",
        "GatherElements",
        "GatherND",
        "MatMul",
        "Gemm",
        "Add",
        "Mul",
        "Softmax",
        "Sigmoid",
        "Tanh",
    }

    # ============================================================
    # TOKEN PATH TRAVERSAL
    # ============================================================
    visited_tensors = set()
    visited_nodes = set()
    queue = [start_tensor_name]

    report_lines = []
    report_lines.append("=== TOKEN PATH VERIFIER REPORT ===")
    report_lines.append(f"Model: {onnx_file}")
    report_lines.append(f"Start tensor: {start_tensor_name}")
    report_lines.append("")

    if start_tensor_name in tensor_info:
        ti = tensor_info[start_tensor_name]
        start_line = (
            f'START: {start_tensor_name} '
            f'dtype={dtype_name(ti["dtype"])} '
            f'shape={shape_to_str(ti["shape"])}'
        )
    else:
        start_line = f'START: {start_tensor_name} (tensor info unknown)'

    print(start_line)
    report_lines.append(start_line)
    report_lines.append("")

    suspicious_findings = []

    step_index = 0

    while queue:
        tensor_name = queue.pop(0)

        if tensor_name in visited_tensors:
            continue
        visited_tensors.add(tensor_name)

        if tensor_name not in consumers:
            continue

        for node in consumers[tensor_name]:
            node_key = (node.name, tuple(node.output))
            if node_key in visited_nodes:
                continue
            visited_nodes.add(node_key)

            node_name = node.name if node.name else f"<unnamed_{step_index}>"
            step_header = f"[{step_index}] {node_name} ({node.op_type})"
            step_index += 1

            print("\n" + step_header)
            report_lines.append(step_header)

            # --------------------------------------------------------
            # Inputs
            # --------------------------------------------------------
            print("  Inputs:")
            report_lines.append("  Inputs:")

            for inp_name in node.input:
                if inp_name == "":
                    line = "    <empty optional input>"
                    print(line)
                    report_lines.append(line)
                    continue

                ti = tensor_info.get(inp_name)
                if ti is None:
                    line = f'    {inp_name}: dtype=unknown shape=unknown'
                else:
                    line = (
                        f'    {inp_name}: '
                        f'dtype={dtype_name(ti["dtype"])} '
                        f'shape={shape_to_str(ti["shape"])} '
                        f'source={ti["source"]}'
                    )
                print(line)
                report_lines.append(line)

            # --------------------------------------------------------
            # Outputs
            # --------------------------------------------------------
            print("  Outputs:")
            report_lines.append("  Outputs:")

            for out_name in node.output:
                ti = tensor_info.get(out_name)
                if ti is None:
                    line = f'    {out_name}: dtype=unknown shape=unknown'
                else:
                    line = (
                        f'    {out_name}: '
                        f'dtype={dtype_name(ti["dtype"])} '
                        f'shape={shape_to_str(ti["shape"])} '
                        f'source={ti["source"]}'
                    )
                print(line)
                report_lines.append(line)

            # ========================================================
            # Special diagnostics for token path
            # ========================================================
            # 1) Cast
            if node.op_type == "Cast":
                to_dtype = get_attr(node, "to", None)
                msg = f'  CAST TARGET: to={dtype_name(to_dtype)}'
                print(msg)
                report_lines.append(msg)

            # 2) Gather
            if node.op_type == "Gather":
                if len(node.input) >= 2:
                    data_name = node.input[0]
                    idx_name = node.input[1]

                    data_ti = tensor_info.get(data_name)
                    idx_ti = tensor_info.get(idx_name)

                    data_dtype = data_ti["dtype"] if data_ti else None
                    data_shape = data_ti["shape"] if data_ti else None
                    idx_dtype = idx_ti["dtype"] if idx_ti else None
                    idx_shape = idx_ti["shape"] if idx_ti else None

                    msg = (
                        f'  GATHER CHECK: data={data_name} dtype={dtype_name(data_dtype)} shape={shape_to_str(data_shape)} | '
                        f'indices={idx_name} dtype={dtype_name(idx_dtype)} shape={shape_to_str(idx_shape)}'
                    )
                    print(msg)
                    report_lines.append(msg)

                    if idx_dtype is not None and not is_integer_dtype(idx_dtype):
                        warn = (
                            f'  WARNING: Gather indices are not integer: {dtype_name(idx_dtype)}'
                        )
                        print(warn)
                        report_lines.append(warn)
                        suspicious_findings.append((node_name, "gather_non_integer_indices", warn))

            # 3) Reshape
            if node.op_type == "Reshape" and len(node.input) >= 2:
                shape_input_name = node.input[1]
                shape_arr = load_initializer_array(shape_input_name, init_map)

                if shape_arr is not None:
                    msg = f'  RESHAPE TARGET CONST: name={shape_input_name} values={shape_arr.tolist()} dtype={shape_arr.dtype}'
                    print(msg)
                    report_lines.append(msg)
                else:
                    msg = f'  RESHAPE TARGET NON-CONST: name={shape_input_name}'
                    print(msg)
                    report_lines.append(msg)

            # 4) Expand / Tile / ConstantOfShape
            if node.op_type in {"Expand", "Tile", "ConstantOfShape"}:
                warn = f'  WARNING: {node.op_type} is on token path and may be compiler-sensitive'
                print(warn)
                report_lines.append(warn)
                suspicious_findings.append((node_name, f"{node.op_type.lower()}_on_token_path", warn))

            # 5) Concat / Split / Transpose / Squeeze / Unsqueeze
            if node.op_type in {"Concat", "Split", "Transpose", "Squeeze", "Unsqueeze"}:
                note = f'  NOTE: {node.op_type} changes layout/rank on token path'
                print(note)
                report_lines.append(note)

            # 6) Softmax / MatMul / Add / Mul reached
            if node.op_type in {"MatMul", "Gemm", "Add", "Mul", "Softmax"}:
                note = f'  NOTE: token-derived branch reached semantic math op {node.op_type}'
                print(note)
                report_lines.append(note)

            # --------------------------------------------------------
            # Traversal rule
            # --------------------------------------------------------
            if follow_layout_ops:
                if node.op_type in passthrough_ops or node.op_type in terminal_ops:
                    for out_name in node.output:
                        queue.append(out_name)
            else:
                if node.op_type in passthrough_ops:
                    for out_name in node.output:
                        queue.append(out_name)

    # ============================================================
    # SUMMARY
    # ============================================================
    report_lines.append("")
    report_lines.append("=== SUMMARY ===")
    report_lines.append(f"Visited tensors: {len(visited_tensors)}")
    report_lines.append(f"Visited nodes: {len(visited_nodes)}")

    print("\n=== SUMMARY ===")
    print("Visited tensors:", len(visited_tensors))
    print("Visited nodes:", len(visited_nodes))

    report_lines.append("")
    report_lines.append("=== SUSPICIOUS FINDINGS ===")

    print("\n=== SUSPICIOUS FINDINGS ===")
    if len(suspicious_findings) == 0:
        report_lines.append("No suspicious findings on token path.")
        print("No suspicious findings on token path.")
    else:
        for i, (node_name, kind, detail) in enumerate(suspicious_findings):
            line = f'[{i}] node="{node_name}" kind="{kind}" detail="{detail}"'
            report_lines.append(line)
            print(line)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"\nSaved token path report to: {report_file}")