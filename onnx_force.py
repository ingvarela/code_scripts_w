import onnx
from onnx import TensorProto

# Human-friendly name -> ONNX enum
DTYPE_MAP = {
    "float32": TensorProto.FLOAT,
    "float16": TensorProto.FLOAT16,
    "float64": TensorProto.DOUBLE,
    "int8": TensorProto.INT8,
    "uint8": TensorProto.UINT8,
    "int16": TensorProto.INT16,
    "uint16": TensorProto.UINT16,
    "int32": TensorProto.INT32,
    "uint32": TensorProto.UINT32,
    "int64": TensorProto.INT64,
    "uint64": TensorProto.UINT64,
    "bool": TensorProto.BOOL,
}

# Optional: update raw tensor data stored in initializers too
# This example only changes the declared metadata type and the initializer metadata type,
# not the actual numerical payload conversion.
# For a true payload conversion, see notes below.

def set_value_info_dtype(value_info, new_dtype):
    # Only touch tensor types
    if value_info.type.HasField("tensor_type"):
        value_info.type.tensor_type.elem_type = new_dtype


def set_initializer_dtype_only(initializer, new_dtype):
    """
    WARNING:
    This changes the initializer declared data_type field only.
    It does NOT convert the stored tensor payload.
    That can make the model invalid unless you also rewrite the data.
    """
    initializer.data_type = new_dtype


def recurse_graph(graph, new_dtype, change_initializers=False):
    # Update graph inputs / outputs / intermediate value_info
    for vi in graph.input:
        set_value_info_dtype(vi, new_dtype)

    for vi in graph.output:
        set_value_info_dtype(vi, new_dtype)

    for vi in graph.value_info:
        set_value_info_dtype(vi, new_dtype)

    # Update initializers if requested
    if change_initializers:
        for init in graph.initializer:
            set_initializer_dtype_only(init, new_dtype)

    # Recurse into subgraphs stored in node attributes
    for node in graph.node:
        for attr in node.attribute:
            if attr.type == onnx.AttributeProto.GRAPH:
                recurse_graph(attr.g, new_dtype, change_initializers)
            elif attr.type == onnx.AttributeProto.GRAPHS:
                for g in attr.graphs:
                    recurse_graph(g, new_dtype, change_initializers)


def convert_model_types_everywhere(
    input_model_path,
    output_model_path,
    target_dtype_str="float16",
    change_initializers=False,
):
    if target_dtype_str not in DTYPE_MAP:
        raise ValueError(f"Unsupported dtype: {target_dtype_str}")

    target_dtype = DTYPE_MAP[target_dtype_str]

    model = onnx.load(input_model_path)

    recurse_graph(model.graph, target_dtype, change_initializers)

    # Validate if possible
    onnx.checker.check_model(model)

    onnx.save(model, output_model_path)
    print(f"Saved modified model to: {output_model_path}")


if __name__ == "__main__":
    convert_model_types_everywhere(
        input_model_path="model.onnx",
        output_model_path="model_all_float16.onnx",
        target_dtype_str="float16",
        change_initializers=False,  # safer default
    )