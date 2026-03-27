#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

// ============================================================
// Small .npy loader
// Supports:
// - little-endian float32
// - little-endian int64
// - C-contiguous arrays
// ============================================================

struct NpyTensor {
    std::string descr;
    bool fortran_order = false;
    std::vector<int64_t> shape;
    std::vector<char> raw;
};

static std::string read_exact(std::ifstream& f, size_t n) {
    std::string s(n, '\0');
    f.read(&s[0], static_cast<std::streamsize>(n));
    if (!f) {
        throw std::runtime_error("Failed to read expected bytes");
    }
    return s;
}

static std::string trim_spaces(std::string s) {
    s.erase(std::remove_if(s.begin(), s.end(), ::isspace), s.end());
    return s;
}

static std::vector<int64_t> parse_shape_from_header(const std::string& header) {
    auto shape_pos = header.find("shape");
    if (shape_pos == std::string::npos) {
        throw std::runtime_error("Could not find shape in .npy header");
    }

    auto lparen = header.find('(', shape_pos);
    auto rparen = header.find(')', lparen);
    if (lparen == std::string::npos || rparen == std::string::npos) {
        throw std::runtime_error("Could not parse shape tuple in .npy header");
    }

    std::string inside = header.substr(lparen + 1, rparen - lparen - 1);
    std::vector<int64_t> dims;

    size_t start = 0;
    while (start < inside.size()) {
        size_t comma = inside.find(',', start);
        std::string token = (comma == std::string::npos)
            ? inside.substr(start)
            : inside.substr(start, comma - start);

        token = trim_spaces(token);
        if (!token.empty()) {
            dims.push_back(static_cast<int64_t>(std::stoll(token)));
        }

        if (comma == std::string::npos) {
            break;
        }
        start = comma + 1;
    }

    return dims;
}

static NpyTensor load_npy(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        throw std::runtime_error("Failed to open .npy file: " + path);
    }

    std::string magic = read_exact(f, 6);
    if (magic != "\x93NUMPY") {
        throw std::runtime_error("Invalid .npy file: bad magic");
    }

    uint8_t major = 0;
    uint8_t minor = 0;
    f.read(reinterpret_cast<char*>(&major), 1);
    f.read(reinterpret_cast<char*>(&minor), 1);
    if (!f) {
        throw std::runtime_error("Failed to read .npy version");
    }

    uint32_t header_len = 0;
    if (major == 1) {
        uint16_t hl16 = 0;
        f.read(reinterpret_cast<char*>(&hl16), 2);
        if (!f) throw std::runtime_error("Failed to read v1 header length");
        header_len = hl16;
    } else if (major == 2 || major == 3) {
        f.read(reinterpret_cast<char*>(&header_len), 4);
        if (!f) throw std::runtime_error("Failed to read v2/v3 header length");
    } else {
        throw std::runtime_error("Unsupported .npy version");
    }

    std::string header = read_exact(f, header_len);

    NpyTensor t;
    t.shape = parse_shape_from_header(header);

    if (header.find("fortran_order") != std::string::npos &&
        header.find("True") != std::string::npos) {
        throw std::runtime_error("Fortran-order arrays are not supported");
    }
    t.fortran_order = false;

    if (header.find("'descr': '<f4'") != std::string::npos ||
        header.find("\"descr\": \"<f4\"") != std::string::npos ||
        header.find("'descr': '|f4'") != std::string::npos) {
        t.descr = "<f4";
    } else if (header.find("'descr': '<i8'") != std::string::npos ||
               header.find("\"descr\": \"<i8\"") != std::string::npos ||
               header.find("'descr': '|i8'") != std::string::npos) {
        t.descr = "<i8";
    } else {
        throw std::runtime_error("Unsupported dtype in .npy header");
    }

    f.seekg(0, std::ios::end);
    std::streamoff end_pos = f.tellg();
    std::streamoff data_pos = 6 + 2 + ((major == 1) ? 2 : 4) + header_len;
    std::streamoff raw_size = end_pos - data_pos;

    if (raw_size <= 0) {
        throw std::runtime_error("No payload data in .npy file");
    }

    t.raw.resize(static_cast<size_t>(raw_size));
    f.seekg(data_pos, std::ios::beg);
    f.read(t.raw.data(), raw_size);
    if (!f) {
        throw std::runtime_error("Failed to read .npy payload");
    }

    return t;
}

static int64_t num_elements(const std::vector<int64_t>& shape) {
    if (shape.empty()) return 1;
    return std::accumulate(shape.begin(), shape.end(), int64_t{1}, std::multiplies<int64_t>());
}

template <typename T>
static std::vector<T> tensor_as_vector(const NpyTensor& t, const std::string& expected_descr) {
    if (t.descr != expected_descr) {
        throw std::runtime_error("Unexpected dtype. Expected " + expected_descr + ", got " + t.descr);
    }

    int64_t n = num_elements(t.shape);
    size_t expected_bytes = static_cast<size_t>(n) * sizeof(T);
    if (t.raw.size() != expected_bytes) {
        throw std::runtime_error("Raw byte size does not match expected tensor size");
    }

    std::vector<T> out(static_cast<size_t>(n));
    std::memcpy(out.data(), t.raw.data(), expected_bytes);
    return out;
}

static void print_shape(const std::vector<int64_t>& shape) {
    std::cout << "[";
    for (size_t i = 0; i < shape.size(); ++i) {
        std::cout << shape[i];
        if (i + 1 < shape.size()) std::cout << ", ";
    }
    std::cout << "]";
}

// ============================================================
// Main
// ============================================================

int main() {
    try {
        // ------------------------------------------------------------
        // Paths
        // ------------------------------------------------------------
        const std::string onnx_file =
            "./best_eval_epoch_49_decoder_single_legalized_DeleteExpandConstant_GemmToMatMul_surgeon_int64_modi.onnx";

        const std::string input0_npy = "./input0.npy";   // float32 [1,352,2,8]
        const std::string input1_npy = "./input1.npy";   // int64 [1,1] or float32 [1,1] depending on model
        const std::string input2_npy = "./input2.npy";   // float32 [1,1,256]
        const std::string input3_npy = "./input3.npy";   // float32 [1,1,256]

        // ------------------------------------------------------------
        // Load .npy tensors
        // ------------------------------------------------------------
        NpyTensor input0_npy_tensor = load_npy(input0_npy);
        NpyTensor input1_npy_tensor = load_npy(input1_npy);
        NpyTensor input2_npy_tensor = load_npy(input2_npy);
        NpyTensor input3_npy_tensor = load_npy(input3_npy);

        std::vector<float> input0 = tensor_as_vector<float>(input0_npy_tensor, "<f4");
        std::vector<float> input2 = tensor_as_vector<float>(input2_npy_tensor, "<f4");
        std::vector<float> input3 = tensor_as_vector<float>(input3_npy_tensor, "<f4");

        // IMPORTANT:
        // This example assumes your current model expects input:1 as int64.
        // If your model expects float32 there, switch this to float and adjust
        // CreateTensor below.
        std::vector<int64_t> input1 = tensor_as_vector<int64_t>(input1_npy_tensor, "<i8");

        std::cout << "Loaded inputs from .npy:\n";
        std::cout << " input0 dtype=float32 shape=";
        print_shape(input0_npy_tensor.shape);
        std::cout << "\n";

        std::cout << " input1 dtype=int64 shape=";
        print_shape(input1_npy_tensor.shape);
        std::cout << "\n";

        std::cout << " input2 dtype=float32 shape=";
        print_shape(input2_npy_tensor.shape);
        std::cout << "\n";

        std::cout << " input3 dtype=float32 shape=";
        print_shape(input3_npy_tensor.shape);
        std::cout << "\n\n";

        // ------------------------------------------------------------
        // ONNX Runtime setup
        // ------------------------------------------------------------
        Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "decoder_runner");
        Ort::SessionOptions session_options;
        session_options.SetIntraOpNumThreads(1);
        session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

        Ort::Session session(env, onnx_file.c_str(), session_options);
        Ort::AllocatorWithDefaultOptions allocator;

        std::cout << "Model inputs:\n";
        for (size_t i = 0; i < session.GetInputCount(); ++i) {
            auto name = session.GetInputNameAllocated(i, allocator);
            auto info = session.GetInputTypeInfo(i).GetTensorTypeAndShapeInfo();
            std::cout << "  " << name.get() << " type=" << info.GetElementType() << " shape=";
            print_shape(info.GetShape());
            std::cout << "\n";
        }

        std::cout << "\nModel outputs:\n";
        for (size_t i = 0; i < session.GetOutputCount(); ++i) {
            auto name = session.GetOutputNameAllocated(i, allocator);
            auto info = session.GetOutputTypeInfo(i).GetTensorTypeAndShapeInfo();
            std::cout << "  " << name.get() << " type=" << info.GetElementType() << " shape=";
            print_shape(info.GetShape());
            std::cout << "\n";
        }
        std::cout << "\n";

        // ------------------------------------------------------------
        // Create ORT tensors
        // ------------------------------------------------------------
        Ort::MemoryInfo mem_info = Ort::MemoryInfo::CreateCpu(
            OrtArenaAllocator, OrtMemTypeDefault);

        Ort::Value input0_tensor = Ort::Value::CreateTensor<float>(
            mem_info,
            input0.data(),
            input0.size(),
            input0_npy_tensor.shape.data(),
            input0_npy_tensor.shape.size()
        );

        Ort::Value input1_tensor = Ort::Value::CreateTensor<int64_t>(
            mem_info,
            input1.data(),
            input1.size(),
            input1_npy_tensor.shape.data(),
            input1_npy_tensor.shape.size()
        );

        Ort::Value input2_tensor = Ort::Value::CreateTensor<float>(
            mem_info,
            input2.data(),
            input2.size(),
            input2_npy_tensor.shape.data(),
            input2_npy_tensor.shape.size()
        );

        Ort::Value input3_tensor = Ort::Value::CreateTensor<float>(
            mem_info,
            input3.data(),
            input3.size(),
            input3_npy_tensor.shape.data(),
            input3_npy_tensor.shape.size()
        );

        std::vector<const char*> input_names = {
            "input:0",
            "input:1",
            "input:2",
            "input:3"
        };

        std::vector<Ort::Value> input_tensors;
        input_tensors.emplace_back(std::move(input0_tensor));
        input_tensors.emplace_back(std::move(input1_tensor));
        input_tensors.emplace_back(std::move(input2_tensor));
        input_tensors.emplace_back(std::move(input3_tensor));

        std::vector<const char*> output_names = {
            "output:0",
            "output:1",
            "output:2"
        };

        // ------------------------------------------------------------
        // Run inference
        // ------------------------------------------------------------
        auto outputs = session.Run(
            Ort::RunOptions{nullptr},
            input_names.data(),
            input_tensors.data(),
            input_tensors.size(),
            output_names.data(),
            output_names.size()
        );

        // ------------------------------------------------------------
        // Print output summaries
        // ------------------------------------------------------------
        std::cout << "Outputs:\n";

        for (size_t i = 0; i < outputs.size(); ++i) {
            auto info = outputs[i].GetTensorTypeAndShapeInfo();
            auto shape = info.GetShape();
            auto elem_count = info.GetElementCount();

            std::cout << "\noutput " << i << "\n";
            std::cout << " shape=";
            print_shape(shape);
            std::cout << "\n";
            std::cout << " element_count=" << elem_count << "\n";

            float* data = outputs[i].GetTensorMutableData<float>();

            float min_val = data[0];
            float max_val = data[0];
            double sum = 0.0;

            for (size_t j = 0; j < elem_count; ++j) {
                min_val = std::min(min_val, data[j]);
                max_val = std::max(max_val, data[j]);
                sum += data[j];
            }

            double mean = sum / static_cast<double>(elem_count);

            std::cout << " min=" << min_val << "\n";
            std::cout << " max=" << max_val << "\n";
            std::cout << " mean=" << mean << "\n";

            std::cout << " first 10 values: ";
            size_t show_n = std::min<size_t>(10, elem_count);
            for (size_t j = 0; j < show_n; ++j) {
                std::cout << data[j] << " ";
            }
            std::cout << "\n";
        }

        std::cout << "\nfinished\n";
        return 0;
    }
    catch (const Ort::Exception& e) {
        std::cerr << "ONNX Runtime error: " << e.what() << "\n";
        return 1;
    }
    catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << "\n";
        return 2;
    }
}