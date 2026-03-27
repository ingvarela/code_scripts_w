import copy
import os
import traceback
import numpy as np
import onnx
import onnxruntime as ort
from onnx import TensorProto, shape_inference, numpy_helper, helper


if __name__ == '__main__':
    # ============================================================
    # CONFIG
    # ============================================================
    onnx_file = "./model.onnx"
    report_file = "./onnx_strong_verifier_report.txt"

    # Optional runtime execution
    RUN_RUNTIME = False
    runtime_inputs = {
        # "input:0": "./input0.npy",
        # "input:1": "./input1.npy",
        # "input:2": "./input2.npy",
        # "input:3": "./input3.npy",
    }

    # Add all intermediate outputs and inspect them
    EXPOSE_INTERMEDIATES = False
    MAX_RUNTIME_OUTPUTS_TO_PRINT = 100
    MAX_VALUES_PER_OUTPUT = 8

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

    def normalize_axis(axis, rank):
        if rank is None:
            return None
        if axis < 0:
            axis += rank
        return axis

    def numel_if_static(shape):
        if shape is None:
            return None
        prod = 1
        for d in shape:
            if not isinstance(d, int) or d <= 0:
                return None
            prod *= d
        return prod

    def is_integer_dtype(dtype):
        return dtype in {
            TensorProto.INT8, TensorProto.INT16, TensorProto.INT32, TensorProto.INT64,
            TensorProto.UINT8, TensorProto.UINT16, TensorProto.UINT32, TensorProto.UINT64
        }

    def broadcast_check(a, b):
        if a is None or b is None:
            return True, None
        aa = list(a)
        bb = list(b)
        n = max(len(aa), len(bb))
        aa = [1] * (n - len(aa)) + aa
        bb = [1] * (n - len(bb)) + bb
        out = []
        for x, y in zip(aa, bb):
            if x == y:
                out.append(x)
            elif x == 1:
                out.append(y)
            elif y == 1:
                out.append(x)
            elif x == "?" or y == "?":
                out.append("?")
            elif isinstance(x, str) or isinstance(y, str):
                out.append("?")
            else:
                return False, None
        return True, out

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

    def load_initializer(name, init_map):
        if name not in init_map:
            return None
        return numpy_helper.to_array(init_map[name])

    def add_issue(issues, severity, node, kind, detail):
        issues.append({
            "severity": severity,
            "node_name": node.name if node is not None and node.name else ("<graph>" if node is None else "<unnamed>"),
            "op_type": None if node is None else node.op_type,
            "kind": kind,
            "detail": detail,
        })

    # ============================================================
    # LOAD + CORE ONNX VALIDATION
    # ============================================================
    issues = []
    report = []
    report.append("=== STRONG ONNX VERIFIER REPORT ===")
    report.append(f"Model: {onnx_file}")
    report.append("")

    try:
        model = onnx.load(onnx_file)
        report.append("Load: PASS")
    except Exception as e:
        report.append(f"Load: FAIL -> {e}")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("\n".join(report))
        raise

    try:
        onnx.checker.check_model(model)
        report.append("onnx.checker: PASS")
    except Exception as e:
        add_issue(issues, "ERROR", None, "onnx_checker_fail", str(e))
        report.append(f"onnx.checker: FAIL -> {e}")

    try:
        inferred = shape_inference.infer_shapes(model)
        report.append("shape_inference: PASS")
    except Exception as e:
        inferred = model
        add_issue(issues, "ERROR", None, "shape_inference_fail", str(e))
        report.append(f"shape_inference: FAIL -> {e}")

    tensor_info = collect_tensor_info(inferred)
    init_map = {x.name: x for x in inferred.graph.initializer}

    report.append("")
    report.append("=== MODEL INTERFACE ===")
    report.append("Inputs:")
    for x in inferred.graph.input:
        ti = tensor_info.get(x.name, {})
        report.append(f'  {x.name}: dtype={dtype_name(ti.get("dtype"))} shape={shape_to_str(ti.get("shape"))}')
    report.append("Outputs:")
    for x in inferred.graph.output:
        ti = tensor_info.get(x.name, {})
        report.append(f'  {x.name}: dtype={dtype_name(ti.get("dtype"))} shape={shape_to_str(ti.get("shape"))}')

    # ============================================================
    # NODE-BY-NODE VERIFICATION
    # ============================================================
    for i, node in enumerate(inferred.graph.node):
        in_shapes = []
        in_dtypes = []

        for name in node.input:
            if name == "":
                in_shapes.append(None)
                in_dtypes.append(None)
                continue
            ti = tensor_info.get(name)
            if ti is None:
                in_shapes.append(None)
                in_dtypes.append(None)
                add_issue(issues, "ERROR", node, "missing_tensor_info", f'No tensor info for input "{name}"')
            else:
                in_shapes.append(ti["shape"])
                in_dtypes.append(ti["dtype"])

        out_shapes = []
        out_dtypes = []
        for name in node.output:
            ti = tensor_info.get(name)
            if ti is None:
                out_shapes.append(None)
                out_dtypes.append(None)
            else:
                out_shapes.append(ti["shape"])
                out_dtypes.append(ti["dtype"])

        # -------- generic checks --------
        for out_name in node.output:
            if out_name == "":
                add_issue(issues, "ERROR", node, "empty_output_name", "Node has empty output name")

        # -------- op-specific checks --------
        op = node.op_type

        if op in {"Add", "Sub", "Mul", "Div", "Pow", "And", "Or", "Where"} and len(in_shapes) >= 2:
            ok, _ = broadcast_check(in_shapes[0], in_shapes[1])
            if not ok:
                add_issue(
                    issues, "ERROR", node, "broadcast_mismatch",
                    f"{op} inputs are not broadcastable: {shape_to_str(in_shapes[0])} vs {shape_to_str(in_shapes[1])}"
                )

        elif op == "MatMul" and len(in_shapes) >= 2:
            a, b = in_shapes[0], in_shapes[1]
            if a is not None and b is not None and len(a) >= 2 and len(b) >= 2:
                ak = a[-1]
                bk = b[-2]
                if isinstance(ak, int) and isinstance(bk, int) and ak != bk:
                    add_issue(
                        issues, "ERROR", node, "matmul_inner_mismatch",
                        f"A[-1]={ak} does not match B[-2]={bk}"
                    )

        elif op == "Gemm" and len(in_shapes) >= 2:
            a, b = in_shapes[0], in_shapes[1]
            transA = get_attr(node, "transA", 0)
            transB = get_attr(node, "transB", 0)
            if a is not None and b is not None and len(a) == 2 and len(b) == 2:
                ak = a[0] if transA else a[1]
                bk = b[1] if transB else b[0]
                if isinstance(ak, int) and isinstance(bk, int) and ak != bk:
                    add_issue(
                        issues, "ERROR", node, "gemm_inner_mismatch",
                        f"Gemm inner mismatch after transpose flags: {ak} vs {bk}"
                    )

        elif op == "Concat" and len(in_shapes) > 1:
            axis = get_attr(node, "axis", 0)
            known = [s for s in in_shapes if s is not None]
            if len(known) > 1:
                ranks = [len(s) for s in known]
                if len(set(ranks)) != 1:
                    add_issue(issues, "ERROR", node, "concat_rank_mismatch", f"Input ranks differ: {ranks}")
                else:
                    rank = ranks[0]
                    axis_n = normalize_axis(axis, rank)
                    if axis_n is None or axis_n < 0 or axis_n >= rank:
                        add_issue(issues, "ERROR", node, "concat_bad_axis", f"Axis {axis} invalid for rank {rank}")
                    else:
                        ref = known[0]
                        for s in known[1:]:
                            for d in range(rank):
                                if d == axis_n:
                                    continue
                                if isinstance(ref[d], int) and isinstance(s[d], int) and ref[d] != s[d]:
                                    add_issue(
                                        issues, "ERROR", node, "concat_dim_mismatch",
                                        f"Dimension {d} mismatch: {shape_to_str(ref)} vs {shape_to_str(s)}"
                                    )
                                    break

        elif op == "Reshape" and len(node.input) >= 2:
            data_shape = in_shapes[0]
            target = load_initializer(node.input[1], init_map)
            if data_shape is not None and target is not None:
                target = target.tolist()
                if not isinstance(target, list):
                    target = [int(target)]

                input_numel = numel_if_static(data_shape)
                minus_ones = 0
                known_prod = 1
                for idx_dim, d in enumerate(target):
                    d = int(d)
                    if d == -1:
                        minus_ones += 1
                    elif d == 0:
                        if idx_dim < len(data_shape) and isinstance(data_shape[idx_dim], int):
                            known_prod *= data_shape[idx_dim]
                        else:
                            known_prod = None
                    else:
                        known_prod *= d

                if minus_ones > 1:
                    add_issue(issues, "ERROR", node, "reshape_multiple_minus_one", f"Target shape has multiple -1: {target}")

                if input_numel is not None and known_prod is not None and minus_ones == 0:
                    if input_numel != known_prod:
                        add_issue(
                            issues, "ERROR", node, "reshape_numel_mismatch",
                            f"Input elements {input_numel} vs target elements {known_prod}, target={target}"
                        )

        elif op == "Transpose" and len(in_shapes) >= 1:
            s = in_shapes[0]
            perm = get_attr(node, "perm", None)
            if s is not None:
                rank = len(s)
                if perm is not None:
                    if len(perm) != rank:
                        add_issue(
                            issues, "ERROR", node, "transpose_perm_rank_mismatch",
                            f"perm length {len(perm)} does not match rank {rank}"
                        )
                    elif sorted(perm) != list(range(rank)):
                        add_issue(
                            issues, "ERROR", node, "transpose_bad_perm",
                            f"perm is not a valid permutation: {perm}"
                        )

        elif op == "Softmax" and len(in_shapes) >= 1:
            s = in_shapes[0]
            axis = get_attr(node, "axis", 1)
            if s is not None:
                rank = len(s)
                axis_n = normalize_axis(axis, rank)
                if axis_n is None or axis_n < 0 or axis_n >= rank:
                    add_issue(
                        issues, "ERROR", node, "softmax_bad_axis",
                        f"Axis {axis} invalid for rank {rank}"
                    )

        elif op == "Gather" and len(in_dtypes) >= 2:
            idx_dtype = in_dtypes[1]
            if idx_dtype is not None and not is_integer_dtype(idx_dtype):
                add_issue(
                    issues, "ERROR", node, "gather_non_integer_indices",
                    f"Indices dtype is {dtype_name(idx_dtype)}, expected integer"
                )

        elif op == "Split" and len(in_shapes) >= 1:
            s = in_shapes[0]
            axis = get_attr(node, "axis", 0)
            split = get_attr(node, "split", None)
            if s is not None:
                rank = len(s)
                axis_n = normalize_axis(axis, rank)
                if axis_n is None or axis_n < 0 or axis_n >= rank:
                    add_issue(issues, "ERROR", node, "split_bad_axis", f"Axis {axis} invalid for rank {rank}")
                elif split is not None and isinstance(s[axis_n], int):
                    if sum(split) != s[axis_n]:
                        add_issue(
                            issues, "ERROR", node, "split_size_mismatch",
                            f"split sizes {split} do not sum to dim {s[axis_n]}"
                        )

        elif op in {"Squeeze", "Unsqueeze"} and len(in_shapes) >= 1:
            axes = get_attr(node, "axes", None)
            s = in_shapes[0]
            if axes is not None and s is not None:
                rank = len(s)
                target_rank = rank if op == "Squeeze" else rank + len(axes)
                for ax in axes:
                    ax_n = normalize_axis(ax, target_rank)
                    if ax_n is None or ax_n < 0 or ax_n >= target_rank:
                        add_issue(
                            issues, "ERROR", node, f"{op.lower()}_bad_axis",
                            f"Axis {ax} invalid"
                        )

        elif op == "Cast":
            to = get_attr(node, "to", None)
            if to is None:
                add_issue(issues, "ERROR", node, "cast_missing_to", "Cast node missing 'to' attribute")

    # ============================================================
    # OPTIONAL RUNTIME
    # ============================================================
    if RUN_RUNTIME:
        try:
            runtime_model = model
            if EXPOSE_INTERMEDIATES:
                runtime_model = copy.deepcopy(model)
                existing = set(x.name for x in runtime_model.graph.output)
                for node in runtime_model.graph.node:
                    for out_name in node.output:
                        if out_name and out_name not in existing:
                            ti = tensor_info.get(out_name)
                            if ti is not None and ti["dtype"] is not None and ti["shape"] is not None:
                                vi = helper.make_tensor_value_info(
                                    out_name,
                                    ti["dtype"],
                                    [d if isinstance(d, int) else None for d in ti["shape"]]
                                )
                                runtime_model.graph.output.append(vi)
                                existing.add(out_name)

            tmp_model_path = "./_runtime_debug_model.onnx"
            onnx.save(runtime_model, tmp_model_path)

            sess = ort.InferenceSession(tmp_model_path, providers=["CPUExecutionProvider"])
            feeds = {}
            for name, path in runtime_inputs.items():
                feeds[name] = np.load(path)

            outputs = sess.run(None, feeds)
            output_defs = sess.get_outputs()

            for i, (od, value) in enumerate(zip(output_defs, outputs)):
                if i >= MAX_RUNTIME_OUTPUTS_TO_PRINT:
                    break

                if np.issubdtype(value.dtype, np.number):
                    if np.any(np.isnan(value)):
                        add_issue(issues, "ERROR", None, "runtime_nan", f'Output "{od.name}" contains NaN')
                    if np.any(np.isinf(value)):
                        add_issue(issues, "ERROR", None, "runtime_inf", f'Output "{od.name}" contains Inf')

            report.append("Runtime execution: PASS")
        except Exception as e:
            add_issue(issues, "ERROR", None, "runtime_fail", f"{type(e).__name__}: {e}")
            report.append(f"Runtime execution: FAIL -> {e}")

    # ============================================================
    # REPORT
    # ============================================================
    report.append("")
    report.append("=== ISSUES ===")
    if not issues:
        report.append("No issues found by strong verifier.")
        print("No issues found by strong verifier.")
    else:
        for i, issue in enumerate(issues):
            line = (
                f'[{i}] severity={issue["severity"]} '
                f'node="{issue["node_name"]}" '
                f'op="{issue["op_type"]}" '
                f'kind="{issue["kind"]}" '
                f'detail="{issue["detail"]}"'
            )
            report.append(line)
            print(line)

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print(f"\nSaved report to: {report_file}")