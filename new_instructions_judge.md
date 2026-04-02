Yes — here are good example config files for the new version.

1) Single-session folder

Use this when the folder only has one annotation session.

{
  "judge_model": "/workspace/shared-dir/SRT/hf_models/InternVL3-78B",
  "question_answers_dir": "/workspace/shared-dir/SRT/VLM_data_resources/stage_2si_model_ann/ann/chartqa_cauldron_llava_format",
  "judge_prompt": "Analyze the given question and its corresponding image. Rank all answers in the list based on their alignment with the input, prioritizing relevance and accuracy. Select the top-ranked answer. Your response must be the exact text of the highest-ranked answer from the provided list. Do not generate new content.",
  "images_path": "/workspace/shared-dir/SRT/VLM_Datasets"
}

In this case, annotation_session_tag is not needed.

2) Multiple sessions in the same folder, with questions files

Example for the st_vqa style case, where the same folder contains:

st_vqa_cauldron_llava_format_task_description
st_vqa_cauldron_llava_format_task_description_textcaps
st_vqa_cauldron_llava_format_task_description_textcaps_aug

To run only the textcaps session:

{
  "judge_model": "/workspace/shared-dir/SRT/hf_models/InternVL3-78B",
  "question_answers_dir": "/workspace/shared-dir/SRT/VLM_data_resources/stage_2si_model_ann/ann/st_vqa_cauldron_llava_format",
  "annotation_session_tag": "st_vqa_cauldron_llava_format_task_description_textcaps",
  "judge_prompt": "Analyze the given question and its corresponding image. Rank all answers in the list based on their alignment with the input, prioritizing relevance and accuracy. Select the top-ranked answer. Your response must be the exact text of the highest-ranked answer from the provided list. Do not generate new content.",
  "images_path": "/workspace/shared-dir/SRT/VLM_Datasets"
}

To run the textcaps_aug session instead:

{
  "judge_model": "/workspace/shared-dir/SRT/hf_models/InternVL3-78B",
  "question_answers_dir": "/workspace/shared-dir/SRT/VLM_data_resources/stage_2si_model_ann/ann/st_vqa_cauldron_llava_format",
  "annotation_session_tag": "st_vqa_cauldron_llava_format_task_description_textcaps_aug",
  "judge_prompt": "Analyze the given question and its corresponding image. Rank all answers in the list based on their alignment with the input, prioritizing relevance and accuracy. Select the top-ranked answer. Your response must be the exact text of the highest-ranked answer from the provided list. Do not generate new content.",
  "images_path": "/workspace/shared-dir/SRT/VLM_Datasets"
}
3) Multiple sessions in the same folder, no questions files

Example for the textocr style case, where the folder has:

textocr_gpt4v_task_information
textocr_gpt4v_aug_task_information
and questions must be reconstructed from the selected annotations files.

For the non-aug session:

{
  "judge_model": "/workspace/shared-dir/SRT/hf_models/InternVL3-78B",
  "question_answers_dir": "/workspace/shared-dir/SRT/VLM_data_resources/stage_2si_model_ann/ann/textocr_gpt4v",
  "annotation_session_tag": "textocr_gpt4v_task_information",
  "judge_prompt": "Analyze the given question and its corresponding image. Rank all answers in the list based on their alignment with the input, prioritizing relevance and accuracy. Select the top-ranked answer. Your response must be the exact text of the highest-ranked answer from the provided list. Do not generate new content.",
  "images_path": "/workspace/shared-dir/SRT/VLM_Datasets"
}

For the aug session:

{
  "judge_model": "/workspace/shared-dir/SRT/hf_models/InternVL3-78B",
  "question_answers_dir": "/workspace/shared-dir/SRT/VLM_data_resources/stage_2si_model_ann/ann/textocr_gpt4v",
  "annotation_session_tag": "textocr_gpt4v_aug_task_information",
  "judge_prompt": "Analyze the given question and its corresponding image. Rank all answers in the list based on their alignment with the input, prioritizing relevance and accuracy. Select the top-ranked answer. Your response must be the exact text of the highest-ranked answer from the provided list. Do not generate new content.",
  "images_path": "/workspace/shared-dir/SRT/VLM_Datasets"
}
4) Another multi-session example with questions files

For the tqa case, the session tags would be things like:

tqa_cauldron_llava_format_task_description_time_related
tqa_cauldron_llava_format_task_description_positional
tqa_cauldron_llava_format_task_description_shapes_counting

Example:

{
  "judge_model": "/workspace/shared-dir/SRT/hf_models/InternVL3-78B",
  "question_answers_dir": "/workspace/shared-dir/SRT/VLM_data_resources/stage_2si_model_ann/ann/tqa_cauldron_llava_format",
  "annotation_session_tag": "tqa_cauldron_llava_format_task_description_positional",
  "judge_prompt": "Analyze the given question and its corresponding image. Rank all answers in the list based on their alignment with the input, prioritizing relevance and accuracy. Select the top-ranked answer. Your response must be the exact text of the highest-ranked answer from the provided list. Do not generate new content.",
  "images_path": "/workspace/shared-dir/SRT/VLM_Datasets"
}
Important note

If the folder contains more than one session and you do not provide annotation_session_tag, the new script is designed to stop and tell you which sessions it found, instead of guessing and mixing them.

If you want, I can also give you a tiny template config with placeholder values only.
