import onnx
from onnx import TensorProto

# Map readable names to ONNX tensor types
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


def find_or_create_value_info(graph, tensor_name):
    """
    Look for type info for a tensor in:
      - graph.input
      - graph.output
      - graph.value_info

    If it does not exist, create a minimal graph.value_info entry.
    """
    for vi in list(graph.input) + list(graph.output) + list(graph.value_info):
        if vi.name == tensor_name:
            return vi

    # Create a new empty ValueInfoProto in graph.value_info
    vi = graph.value_info.add()
    vi.name = tensor_name
    return vi


def set_tensor_elem_type(value_info, new_elem_type):
    """
    Set the tensor element type.
    """
    value_info.type.tensor_type.elem_type = new_elem_type


def modify_node_io_types(
    input_model_path,
    output_model_path,
    node_name,
    input_index=None,
    input_dtype=None,
    output_index=None,
    output_dtype=None,
):
    model = onnx.load(input_model_path)
    graph = model.graph

    # Find node by name
    target_node = None
    for node in graph.node:
        if node.name == node_name:
            target_node = node
            break

    if target_node is None:
        raise ValueError(f"Node '{node_name}' not found.")

    print(f"Found node: {target_node.name} ({target_node.op_type})")

    # Modify one input tensor type
    if input_index is not None and input_dtype is not None:
        if input_index >= len(target_node.input):
            raise IndexError(f"Input index {input_index} out of range.")

        input_tensor_name = target_node.input[input_index]
        vi = find_or_create_value_info(graph, input_tensor_name)
        set_tensor_elem_type(vi, DTYPE_MAP[input_dtype])
        print(f"Changed input[{input_index}] '{input_tensor_name}' -> {input_dtype}")

    # Modify one output tensor type
    if output_index is not None and output_dtype is not None:
        if output_index >= len(target_node.output):
            raise IndexError(f"Output index {output_index} out of range.")

        output_tensor_name = target_node.output[output_index]
        vi = find_or_create_value_info(graph, output_tensor_name)
        set_tensor_elem_type(vi, DTYPE_MAP[output_dtype])
        print(f"Changed output[{output_index}] '{output_tensor_name}' -> {output_dtype}")

    # Validate and save
    onnx.checker.check_model(model)
    onnx.save(model, output_model_path)
    print(f"Saved modified model to: {output_model_path}")


if __name__ == "__main__":
    modify_node_io_types(
        input_model_path="model.onnx",
        output_model_path="model_modified.onnx",
        node_name="MyNodeName",
        input_index=0,
        input_dtype="float16",
        output_index=0,
        output_dtype="float32",
    )