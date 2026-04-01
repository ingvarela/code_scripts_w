from PIL import Image
import torch
import json
import string
import os
import warnings
import argparse
import random
from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path
from internvl_utils import split_model, load_image
from transformers import AutoModel, AutoTokenizer
from tqdm import tqdm
import numpy as np

warnings.filterwarnings("ignore")

# Performs inference using a Qwen model
def run_inference_qwen_vl(prompt: str, image_path: str, model: Any, processor: Any, generation_config: Dict[str, Any]):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": image_path,
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt"
    )
    inputs = inputs.to(model.device)
    generated_ids = model.generate(**inputs, **generation_config)
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )
    return output_text[0]

def get_image(ann: Dict[str, Any], model_type: Optional[str], complement_path: str):
    file = os.path.join(complement_path, ann['image'])
    try:
        _ = Image.open(file)
    except Exception as e:
        print(f'Error opening image: {e}')
    if model_type != "qwen":
        pixel_values = load_image(file, max_num=12).to(torch.bfloat16).cuda()
    else:
        pixel_values = None
    return file, pixel_values

def clean_string(s: str) -> str:
    s = s.lower()
    s = s.rstrip(string.punctuation)
    return s

def compare_strings(s1: str, s2: str) -> bool:
    cleaned_s1 = clean_string(s1)
    cleaned_s2 = clean_string(s2)
    return cleaned_s1 == cleaned_s2

def get_hist(hist_data):
    if not hist_data:
        return {"0": 0}
    max_number_of_models = max(hist_data)
    hist = [0] * (max_number_of_models + 1)
    names = [str(i) for i in range(max_number_of_models + 1)]
    for i_data in hist_data:
        hist[i_data] += 1
    return dict(zip(names, hist))

def apply_fallback_strategy(
        final_answer: str,
        answers: List[str],
        answers_files: List[str],
        frequency_models: Dict[str, int],
        fallback_index: int = 0,  #Alphabetically defined,
        question_id: Optional[str] = None
) -> Tuple[str, List[str]]:

    # Validate fallback_index
    if fallback_index >= len(answers) or fallback_index < 0:
        raise IndexError(f"fallback_index {fallback_index} is out of bounds for answers (model index not found) list of length {len(answers)}")

    # Based on the string comparison identifies the model's answer selected.
    model_chosen = []
    for n_model, answer_ in enumerate(answers):
        if compare_strings(final_answer, answer_):
            model_chosen.append(answers_files[n_model])
            frequency_models[answers_files[n_model]] = frequency_models.get(answers_files[n_model], 0) + 1

    #Uses the answer of the pre-defined fallback model using an index
    if not model_chosen:
        fallback_answer = answers[fallback_index]
        final_answer = fallback_answer
        model_chosen.append(answers_files[fallback_index])
        frequency_models[answers_files[fallback_index]] = frequency_models.get(answers_files[fallback_index], 0) + 1
        #print(f"Fallback used for question ID {question_id}: Using model {answers_files[fallback_index]}")
    return final_answer, model_chosen


def simplify_conversations(original_data: List[Dict]) -> List[Dict]:
    simplified_data = []
    for item in original_data:
        new_item = {
            "id": item["id"],
            "image": item["image"],
            "conversations": []
        }
        for conv in item["conversations"]:
            new_conv = {
                "from": conv["from"],
                "value": conv["value"]
            }
            # Copy only essential fields; ignore others like 'source_model'
            new_item["conversations"].append(new_conv)
        simplified_data.append(new_item)
    return simplified_data


# NEW: helper to keep the original annotations-file loading behavior
# while skipping files that end with "_log.txt".
def get_answer_files(question_answers_dir: str) -> List[str]:
    answer_files = []
    for f in os.listdir(question_answers_dir):
        f_lower = f.lower()

        if not f_lower.startswith("annotations"):
            continue

        if f_lower.endswith("_log.txt"):
            continue

        answer_files.append(os.path.join(question_answers_dir, f))

    return answer_files


# NEW: fallback helper used only when there is no questions file.
# It reconstructs a questions-only structure from one annotations file
# by keeping id, image, and only the human turns.
def build_questions_from_answers(answer_json: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    questions_json = []

    for item in answer_json:
        new_item = {
            "id": item["id"],
            "image": item["image"],
            "conversations": []
        }

        for conv in item.get("conversations", []):
            if conv.get("from") == "human":
                new_item["conversations"].append({
                    "from": conv["from"],
                    "value": conv["value"]
                })

        questions_json.append(new_item)

    return questions_json


def main(data_judge: str):
    # Index for model to fallback in case of empty selection (2 = Qwen).
    fallback_index = 2

    # Define save interval
    SAVE_EVERY_N_IMAGES = 50

    with open(data_judge, "r", encoding="utf8") as fin:
        judge_metadata = json.load(fin)

    question_answers_dir = judge_metadata['question_answers_dir']
    base_folder_name = os.path.basename(question_answers_dir.rstrip('/'))
    output_dir = os.path.join(question_answers_dir, "judge_results")
    os.makedirs(output_dir, exist_ok=True)

    #Files generated
    final_output_path = os.path.join(output_dir, f"{base_folder_name}_selections.json")
    log_output_path = os.path.join(output_dir, f"{base_folder_name}.log")
    state_file = os.path.join(output_dir, f"{base_folder_name}_selections_state.json")
    temp_output_path = os.path.join(output_dir, f"{base_folder_name}_selections_temp.json")
    simplified_output_path = os.path.join(output_dir, f"annotations_InternVL3-78B_JudgeVLM_{base_folder_name}.json")

    if os.path.exists(simplified_output_path):
        print(f"Final output {simplified_output_path} already exists. Skipping processing.")
        return

    #Detect resuming the judging process
    resume = os.path.exists(state_file)
    if resume:
        print(f"Resuming from state file: {state_file}")

    # Initialize state variables
    start_index = 0
    final_json = []
    log_results = []
    total_questions = 0
    number_of_models_per_question = []
    frequency_models = {}
    processed_images = set()

    # Resume from saved state
    if resume:
        try:
            with open(state_file, "r", encoding="utf8") as f:
                state = json.load(f)
            start_index = state.get('last_index', 0) + 1
            final_json = state.get('final_json', [])
            log_results = state.get('log_results', [])
            total_questions = state.get('total_questions', 0)
            number_of_models_per_question = state.get('number_of_models_per_question', [])
            frequency_models = state.get('frequency_models', {})
            processed_images = set(state.get('processed_images', []))
            print(f"Resuming from image index {start_index}")
        except Exception as e:
            print(f"Error loading state file: {e}. Starting from scratch.")
            resume = False  # Reset if loading fails

    # Check for questions file
    questions_file = os.path.join(question_answers_dir, 'questions.json')
    if not Path(questions_file).exists():
        questions_files = [f for f in os.listdir(question_answers_dir) if f.endswith('_questions.json')]
        if questions_files:
            questions_file = os.path.join(question_answers_dir, questions_files[0])
        else:
            questions_file = None

    # Load questions file if present; otherwise reconstruct questions from the first annotations file
    if questions_file and Path(questions_file).exists():
        with open(questions_file, "r", encoding="utf8") as fin:
            questions_json = json.load(fin)
    else:
        # NEW: alternative flow only when no questions file is present
        answers_files_for_fallback = get_answer_files(question_answers_dir)

        if not answers_files_for_fallback:
            print(f'Error: No questions file found in {question_answers_dir} and no annotations files available to reconstruct questions')
            return

        fallback_annotations_file = answers_files_for_fallback[0]
        print(f'No questions file found in {question_answers_dir}. Reconstructing questions from {os.path.basename(fallback_annotations_file)}')

        with open(fallback_annotations_file, "r", encoding="utf8") as fin:
            fallback_answer_json = json.load(fin)

        questions_json = build_questions_from_answers(fallback_answer_json)

    # Skip already processed images
    questions_json = [ann for i, ann in enumerate(questions_json) if i not in processed_images]

    # Use helper so annotations*_log.txt files are skipped automatically
    answers_files = get_answer_files(question_answers_dir)
    jsons_with_answers = []
    for answer_file in answers_files:
        with open(answer_file, "r", encoding="utf8") as fin:
            jsons_with_answers.append(json.load(fin))

    model_path = judge_metadata['judge_model']
    model_type = None
    if "internvl" in str(model_path).lower():
        device_map = split_model(model_path)
        model = AutoModel.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            load_in_8bit=False,
            low_cpu_mem_usage=True,
            use_flash_attn=True,
            trust_remote_code=True,
            device_map=device_map).eval()
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True, use_fast=False)
        processor = None
        generation_config = dict(max_new_tokens=1024, do_sample=True)
        model_type = "internvl"
    elif "qwen" in str(model_path).lower():
        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            dtype=torch.bfloat16,
            attn_implementation="flash_attention_2",
            device_map="auto"
        )
        tokenizer = None
        processor = AutoProcessor.from_pretrained(model_path)
        generation_config = dict(max_new_tokens=1024, do_sample=True)
        model_type = "qwen"

    try:
        processed_count = 0
        for n_ann, ann in tqdm(enumerate(questions_json, start=start_index),
                               total=len(questions_json),
                               initial=start_index,
                               desc="Processing images"):
            if n_ann in processed_images:
                continue

            ann_with_answer = {}
            file, pixel_values = get_image(ann, model_type, judge_metadata['images_path'])
            ann_with_answer['image'] = ann['image']
            ann_with_answer['id'] = ann['id']
            ann_with_answer['conversations'] = []

            for n_question, question in enumerate(ann['conversations']):
                total_questions += 1
                answers = []
                for answer_json in jsons_with_answers:
                    try:
                        answer_to_question = answer_json[n_ann]['conversations'][2 * n_question + 1]['value']
                        answers.append(answer_to_question)
                    except IndexError:
                        answers.append("")

                question_alone = question['value']
                query_prompt = "<image>\n" + judge_metadata[
                    "judge_prompt"] + "Question:" + question_alone + "\n" + "Answers:" + str(answers)

                if model_type == "internvl":
                    final_answer = model.chat(tokenizer, pixel_values, query_prompt, generation_config).encode(
                        'utf-8').decode()
                elif model_type == "qwen":
                    final_answer = run_inference_qwen_vl(query_prompt, file, model, processor, generation_config)

                value_answer = {'from': "gpt", 'value': final_answer}
                ann_with_answer['conversations'].append(question)
                ann_with_answer['conversations'].append(value_answer)

                final_answer, model_chosen = apply_fallback_strategy(
                    final_answer, answers, answers_files, frequency_models, fallback_index, ann['id']
                )

                number_of_models_per_question.append(len(model_chosen))
                log_answer = ann_with_answer.copy()
                log_answer['conversations'][-1]['source_model'] = model_chosen

            final_json.append(ann_with_answer)
            log_results.append(log_answer)
            processed_images.add(n_ann)
            processed_count += 1

            # Save state frequency
            if processed_count % SAVE_EVERY_N_IMAGES == 0:
                with open(temp_output_path, "w", encoding="utf8") as fout:
                    json.dump(final_json, fout, indent=4)

                state = {
                    'last_index': n_ann,
                    'final_json': final_json,
                    'log_results': log_results,
                    'total_questions': total_questions,
                    'number_of_models_per_question': number_of_models_per_question,
                    'frequency_models': frequency_models,
                    'processed_images': list(processed_images)
                }
                with open(state_file, "w", encoding="utf8") as f:
                    json.dump(state, f, indent=4)
                processed_count = 0

                # Final save after processing all images
        with open(temp_output_path, "w", encoding="utf8") as fout:
            json.dump(final_json, fout, indent=4)

        state = {
            'last_index': n_ann,
            'final_json': final_json,
            'log_results': log_results,
            'total_questions': total_questions,
            'number_of_models_per_question': number_of_models_per_question,
            'frequency_models': frequency_models,
            'processed_images': list(processed_images)

        }
        with open(state_file, "w", encoding="utf8") as f:
                    json.dump(state, f, indent=4)

    except KeyboardInterrupt:
            print("\nProcess interrupted. Saving current state...")
            with open(temp_output_path, "w", encoding="utf8") as fout:
                json.dump(final_json, fout, indent=4)

            state = {
                'last_index': n_ann,
                'final_json': final_json,
                'log_results': log_results,
                'total_questions': total_questions,
                'number_of_models_per_question': number_of_models_per_question,
                'frequency_models': frequency_models,
                'processed_images': list(processed_images)
            }
            with open(state_file, "w", encoding="utf8") as f:
                json.dump(state, f, indent=4)
            print(f"State saved. To resume, rerun the script.")
            return

    # Final save
    total_log = {
        'total_questions': total_questions,
        'number_of_models_used_by_question': number_of_models_per_question,
        'hist_number_of_models_used_by_question': get_hist(number_of_models_per_question),
        'models_correct_answers': frequency_models,
        'anns_with_models_used': log_results
    }

    with open(final_output_path, "w", encoding="utf8") as fout:
        json.dump(final_json, fout, indent=4)

    with open(log_output_path, "w", encoding="utf8") as fout:
        json.dump(total_log, fout, indent=4)

    # Generate simplified annotations
    simplified_output_path = os.path.join(output_dir, f"annotations_InternVL3-78B_JudgeVLM_{base_folder_name}.json")
    simplified_data = simplify_conversations(final_json)
    with open(simplified_output_path, "w", encoding="utf8") as fout:
        json.dump(simplified_data, fout, indent=2)

    # Cleanup temporary files
    if os.path.exists(state_file):
        os.remove(state_file)
    if os.path.exists(temp_output_path):
        os.remove(temp_output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_judge", type=str, required=True, help="Path to judge metadata JSON")
    args = parser.parse_args()
    main(args.data_judge)
