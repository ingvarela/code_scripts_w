from PIL import Image
import torch
import json
import string
import os
import warnings
import argparse
import random
from typing import Any, Dict, Optional

from pathlib import Path

from internvl_utils import split_model, load_image
from transformers import AutoModel, AutoTokenizer
from tqdm import tqdm

import numpy as np

warnings.filterwarnings("ignore")

def run_inference_qwen_vl(prompt: str, image_path: str, model: Any, processor: Any, generation_config: Dict[str, Any]):
    # print(f"INFERENCE WITH QWEN MODEL.\ntype(model): {type(model)}\ntype(processor): {type(processor)}")
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
    # Preparation for inference
    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt"
    )
    inputs = inputs.to(model.device)
    # Inference: Generation of the output
    generated_ids = model.generate(**inputs, **generation_config)
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )
    return output_text[0]

def get_image(ann: Dict[str, Any], model_type: Optional[str], complement_path: str):
        file = os.path.join(complement_path, ann['image'])
        try:
            _ = Image.open(file)
        except:
            print(f'Image can not be open')

        if model_type != "qwen":
            pixel_values = load_image(file, max_num=12).to(torch.bfloat16).cuda()
        else:
            pixel_values = None

        return file, pixel_values

def clean_string(s: str) -> str:
    # Convert to lowercase
    s = s.lower()
    # Remove punctuation from the end
    s = s.rstrip(string.punctuation)
    return s

def compare_strings(s1: str, s2: str) -> bool:
    """
    Compare two strings s1 and s2.
    Example usage:
    string1 = "Hello, World."
    string2 = "hello world"
    result = compare_strings(string1, string2)
    print(result)  # Output: True    
    """
    cleaned_s1 = clean_string(s1)
    cleaned_s2 = clean_string(s2)
    return cleaned_s1 == cleaned_s2

def get_hist(hist_data):
    
    max_number_of_models = max(hist_data)     
    hist = [0]*(max_number_of_models+1)  
    names = [str(i) for i in range(max_number_of_models+1)]
    
    for i_data in hist_data:
        hist[i_data] += 1

    hist_dict = dict(zip(names, hist))
    return hist_dict


def main(data_judge: str):
    with open(data_judge,"r",encoding="utf8") as fin:
        judge_metadata = json.load(fin)

    question_answers_dir = judge_metadata['question_answers_dir']
    questions_file = os.path.join(question_answers_dir, 'questions.json')
    
    if Path(questions_file).exists():
        with open(questions_file,"r",encoding="utf8") as fin:
            questions_json = json.load(fin)

           
        answers_files = [os.path.join(question_answers_dir, f) for f in os.listdir(question_answers_dir) if f.lower().startswith(('annotations'))]
       # print(answers_files)
        jsons_with_answers = []
        for answer_file in answers_files:
            with open(answer_file,"r",encoding="utf8") as fin:
                jsons_with_answers.append(json.load(fin))

    else:
        print(f'Error: the folder with questions and answers does not exist')

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


    final_json = []
    log_results = []
    total_questions = 0
    number_of_models_per_question = [] # Number of used models per question. If 0, then the response from the Judge does not match any of the model responses.
    frequency_models = {}


    for n_ann, ann in tqdm(enumerate(questions_json)):
        ann_with_answer = {}
        file, pixel_values = get_image(ann, model_type, judge_metadata['images_path'])
        ann_with_answer['image'] = ann['image']
        ann_with_answer['id'] = ann['id']
        ann_with_answer['conversations'] = []

        for n_question, question in enumerate(ann['conversations']):
            total_questions +=1
            answers = []
            for answer_json in jsons_with_answers:
                #print(f'The json with answer is:{answer_json}')
                answer_to_question = answer_json[n_ann]['conversations'][2*n_question+1]['value']
                #print(f'With answer:{answer_to_question}')
                answers.append(answer_to_question)
            question_alone = question['value']         
            query_prompt = "<image>\n" + judge_metadata["judge_pre_prompt"] + judge_metadata["judge_prompt"] + judge_metadata["judge_post_prompt"] + "Question:" + question_alone + "\n" + "Answers:" + str(answers)
            
            #print(f'query prompt = {query_prompt}')
            if model_type == "internvl":
                final_answer = model.chat(tokenizer, pixel_values, query_prompt, generation_config).encode('utf-8').decode()
            elif model_type == "qwen":
                final_answer = run_inference_qwen_vl(query_prompt, file, model, processor, generation_config)
            print(f' For question: {question_alone}, with options: {answers}, the final_answer is {final_answer} \n\n\n')

            value_answer = {'from':"gpt",'value':final_answer}
            ann_with_answer['conversations'].append(question)
            ann_with_answer['conversations'].append(value_answer)
            model_chosen = []

            for n_model, answer_ in enumerate(answers):
                if compare_strings(final_answer, answer_):
                    model_chosen.append(answers_files[n_model])
                    if answers_files[n_model] in frequency_models:
                        frequency_models[answers_files[n_model]] += 1
                    else:
                        frequency_models[answers_files[n_model]] = 1
                        
            number_of_models_per_question.append(len(model_chosen))

            log_answer = ann_with_answer.copy()
            log_answer['conversations'][-1]['source_model'] = model_chosen

        final_json.append(ann_with_answer)
        log_results.append(log_answer)

    
    total_log = {}
    total_log['total_questions'] = total_questions
    total_log['number_of_models_used_by_question'] = number_of_models_per_question
   # frequency_models['None'] = number_of_models_per_question.count(0)
    total_log['hist_number_of_models_used_by_question'] = get_hist(number_of_models_per_question)
    total_log['models_correct_answers'] = frequency_models
    total_log['anns_with_models_used'] = log_results

    with open(os.path.join(question_answers_dir, f'judge_answers_based_on_{args.data_judge}'), "w", encoding="utf8") as fout:
            json.dump(final_json, fout, indent=4)

    with open(os.path.join(question_answers_dir, f'judge_answers_based_on_{Path(args.data_judge).stem}.log'), "w", encoding="utf8") as fout:
            json.dump(total_log, fout, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OCR extraction with VLMs')
    parser.add_argument('--data_judge', default="data_judge.json", type=str, help='.json file with the specific config for the judge.')
    args = parser.parse_args()
    random.seed(42)
    np.random.seed(42)

    main(**vars(args))
