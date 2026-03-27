#include <onnxruntime_cxx_api.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// ============================================================
// Minimal NPY loader for float32 C-contiguous 2D arrays
// ============================================================

struct NpyArray2D {
    std::vector<float> data;
    size_t rows = 0;
    size_t cols = 0;
};

static std::string read_exact(std::ifstream& f, size_t n) {
    std::string s(n, '\0');
    f.read(&s[0], static_cast<std::streamsize>(n));
    if (!f) {
        throw std::runtime_error("Failed to read expected number of bytes from file");
    }
    return s;
}

static NpyArray2D load_npy_float32_2d(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        throw std::runtime_error("Failed to open .npy file: " + path);
    }

    // Magic string
    std::string magic = read_exact(f, 6);
    if (magic != "\x93NUMPY") {
        throw std::runtime_error("Invalid .npy file: bad magic header");
    }

    // Version
    uint8_t major = 0;
    uint8_t minor = 0;
    f.read(reinterpret_cast<char*>(&major), 1);
    f.read(reinterpret_cast<char*>(&minor), 1);
    if (!f) {
        throw std::runtime_error("Failed to read .npy version");
    }

    // Header length
    uint32_t header_len = 0;
    if (major == 1) {
        uint16_t hl16 = 0;
        f.read(reinterpret_cast<char*>(&hl16), 2);
        if (!f) throw std::runtime_error("Failed to read .npy v1 header length");
        header_len = hl16;
    } else if (major == 2 || major == 3) {
        f.read(reinterpret_cast<char*>(&header_len), 4);
        if (!f) throw std::runtime_error("Failed to read .npy v2/v3 header length");
    } else {
        throw std::runtime_error("Unsupported .npy version");
    }

    std::string header = read_exact(f, header_len);

    // Very small parser for:
    // descr: '<f4'
    // fortran_order: False
    // shape: (2105, 256)
    if (header.find("'descr': '<f4'") == std::string::npos &&
        header.find("\"descr\": \"<f4\"") == std::string::npos &&
        header.find("'descr': '|f4'") == std::string::npos) {
        throw std::runtime_error("Expected float32 .npy array");
    }

    if (header.find("fortran_order") != std::string::npos &&
        header.find("True") != std::string::npos) {
        throw std::runtime_error("Fortran-order .npy arrays are not supported in this loader");
    }

    auto shape_pos = header.find("shape");
    if (shape_pos == std::string::npos) {
        throw std::runtime_error("Could not find shape in .npy header");
    }

    auto lparen = header.find('(', shape_pos);
    auto comma = header.find(',', lparen);
    auto comma2 = header.find(',', comma + 1);
    auto rparen = header.find(')', comma + 1);

    if (lparen == std::string::npos || comma == std::string::npos || rparen == std::string::npos) {
        throw std::runtime_error("Could not parse 2D shape from .npy header");
    }

    std::string rows_str = header.substr(lparen + 1, comma - lparen - 1);
    std::string cols_str = header.substr(comma + 1, rparen - comma - 1);

    auto trim = [](std::string s) {
        s.erase(std::remove_if(s.begin(), s.end(), ::isspace), s.end());
        return s;
    };

    rows_str = trim(rows_str);
    cols_str = trim(cols_str);

    size_t rows = static_cast<size_t>(std::stoull(rows_str));
    size_t cols = static_cast<size_t>(std::stoull(cols_str));

    std::vector<float> data(rows * cols);
    f.read(reinterpret_cast<char*>(data.data()),
           static_cast<std::streamsize>(data.size() * sizeof(float)));
    if (!f) {
        throw std::runtime_error("Failed to read array payload from .npy file");
    }

    return {std::move(data), rows, cols};
}

// ============================================================
// External substitute for Gather_11
// ============================================================

static std::vector<float> external_embedding_lookup(
    const NpyArray2D& emb,
    int32_t token_id
) {
    if (emb.cols != 256) {
        throw std::runtime_error("Expected embedding width 256");
    }

    if (token_id < 0 || static_cast<size_t>(token_id) >= emb.rows) {
        std::ostringstream oss;
        oss << "Token id out of range: " << token_id
            << " valid range is [0, " << (emb.rows - 1) << "]";
        throw std::runtime_error(oss.str());
    }

    // Output shape must be [1,1,256]
    std::vector<float> out(1 * 1 * 256);

    const float* src = emb.data.data() + static_cast<size_t>(token_id) * emb.cols;
    std::memcpy(out.data(), src, 256 * sizeof(float));

    return out;
}

// ============================================================
// Example inference with modified ONNX
// ============================================================

int main() {
    try {
        // ------------------------------------------------------------
        // Paths
        // ------------------------------------------------------------
        const std::string model_path =
            "best_eval_epoch_49_decoder_single_legalized_DeleteExpandConstant_GemmToMatMul_surgeon_int64_modi_gather_replaced.onnx";

        const std::string embedding_npy_path =
            "decoder_emb_weight (1).npy";

        // ------------------------------------------------------------
        // Load embedding table
        // ------------------------------------------------------------
        NpyArray2D embedding = load_npy_float32_2d(embedding_npy_path);

        std::cout << "Loaded embedding matrix: ["
                  << embedding.rows << ", " << embedding.cols << "]\n";

        // ------------------------------------------------------------
        // Example runtime inputs
        //
        // Replace these with your real tensors in production.
        // ------------------------------------------------------------
        std::vector<float> input0(1 * 352 * 2 * 8, 0.0f);     // input:0
        std::vector<float> input2(1 * 1 * 256, 0.0f);         // input:2
        std::vector<float> input3(1 * 1 * 256, 0.0f);         // input:3

        // Token id that originally would have gone into input:1
        int32_t token_id = 1;

        // ------------------------------------------------------------
        // External substitute for Gather_11
        // ------------------------------------------------------------
        std::vector<float> embedded_token =
            external_embedding_lookup(embedding, token_id);

        // ------------------------------------------------------------
        // ONNX Runtime setup
        // ------------------------------------------------------------
        Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "decoder_external_gather");
        Ort::SessionOptions session_options;
        session_options.SetIntraOpNumThreads(1);
        session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

        Ort::Session session(env, model_path.c_str(), session_options);

        Ort::AllocatorWithDefaultOptions allocator;

        std::cout << "Inputs:\n";
        for (size_t i = 0; i < session.GetInputCount(); ++i) {
            auto name = session.GetInputNameAllocated(i, allocator);
            std::cout << "  " << i << ": " << name.get() << "\n";
        }

        std::cout << "Outputs:\n";
        for (size_t i = 0; i < session.GetOutputCount(); ++i) {
            auto name = session.GetOutputNameAllocated(i, allocator);
            std::cout << "  " << i << ": " << name.get() << "\n";
        }

        // ------------------------------------------------------------
        // Prepare tensors
        //
        // IMPORTANT:
        // This assumes the modified model inputs are:
        //   input:0         float [1,352,2,8]
        //   embedded_token  float [1,1,256]
        //   input:2         float [1,1,256]
        //   input:3         float [1,1,256]
        // ------------------------------------------------------------
        std::vector<int64_t> shape_input0 = {1, 352, 2, 8};
        std::vector<int64_t> shape_emb    = {1, 1, 256};
        std::vector<int64_t> shape_state  = {1, 1, 256};

        Ort::MemoryInfo mem_info = Ort::MemoryInfo::CreateCpu(
            OrtArenaAllocator, OrtMemTypeDefault);

        Ort::Value tensor_input0 = Ort::Value::CreateTensor<float>(
            mem_info, input0.data(), input0.size(),
            shape_input0.data(), shape_input0.size());

        Ort::Value tensor_emb = Ort::Value::CreateTensor<float>(
            mem_info, embedded_token.data(), embedded_token.size(),
            shape_emb.data(), shape_emb.size());

        Ort::Value tensor_input2 = Ort::Value::CreateTensor<float>(
            mem_info, input2.data(), input2.size(),
            shape_state.data(), shape_state.size());

        Ort::Value tensor_input3 = Ort::Value::CreateTensor<float>(
            mem_info, input3.data(), input3.size(),
            shape_state.data(), shape_state.size());

        std::vector<const char*> input_names = {
            "input:0",
            "embedded_token",
            "input:2",
            "input:3"
        };

        std::vector<Ort::Value> input_tensors;
        input_tensors.emplace_back(std::move(tensor_input0));
        input_tensors.emplace_back(std::move(tensor_emb));
        input_tensors.emplace_back(std::move(tensor_input2));
        input_tensors.emplace_back(std::move(tensor_input3));

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
            output_names.size());

        // ------------------------------------------------------------
        // Inspect output:0 (logits)
        // ------------------------------------------------------------
        float* logits = outputs[0].GetTensorMutableData<float>();
        auto logits_info = outputs[0].GetTensorTypeAndShapeInfo();
        auto logits_shape = logits_info.GetShape();

        std::cout << "output:0 shape = [";
        for (size_t i = 0; i < logits_shape.size(); ++i) {
            std::cout << logits_shape[i];
            if (i + 1 < logits_shape.size()) std::cout << ", ";
        }
        std::cout << "]\n";

        std::cout << "First 10 logits: ";
        size_t num_logits = logits_info.GetElementCount();
        for (size_t i = 0; i < std::min<size_t>(10, num_logits); ++i) {
            std::cout << logits[i] << " ";
        }
        std::cout << "\n";

        std::cout << "Inference finished successfully.\n";
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