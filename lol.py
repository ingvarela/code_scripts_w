import os
from pathlib import Path

def read_fscore(file):
    with open(file,"r",encoding="utf-8") as fin:
        lines = fin.read().splitlines()
    for line in lines:
        if "F_score:" not in line:
            continue
        try:
            f = float(line.replace("F_score:","").strip())
        except:
            f = 0.0

    return f

# In seconds
window_size = [1,2,3,4,5,6,7,8,9,10]
rules = ["one",
         "majority",
        "two",
        "all",
        "two-consecutive",
        "three-consecutive"
        ]


DEVICE=0
EVAL_SCRIPT="suspisious_eval_v2.py"
OUTPUT_PATH="eval_rules"
MODEL="checkpoints/llava-onevision-openai_clip-vit-base-patch16-Qwen_Qwen2.5-0.5B-Instruct_suspicious_bs-256_am9_SRTcommercial-data_dataset-V5_anyres"
TEST_YT="datasets/suspicious_activity_detection_llava_dataset_test_youtube_v3_1fps.json"


set_name = Path(TEST_YT).stem.replace("suspicious_activity_detection_llava_dataset_","")
postfix = "_"
vlm_short = Path(MODEL).name
output_path = f"{OUTPUT_PATH}/{vlm_short}"

# gt rule
count = 0

max_fscore = 0
max_file = ""

for gt_rule in rules:
    if window_size ==  1 and gt_rule not in ["one"]:
        continue
    if window_size == 2 and gt_rule in ["three-consecutive"]:
        continue

    for pred_rule in rules:
        if window_size ==  1 and pred_rule not in ["one"]:
            continue
        if window_size == 2 and pred_rule in ["three-consecutive"]:
            continue

        for ww in window_size:
            for step in range(1,ww+1):
                output_file = f"{output_path}/{set_name}{postfix}_predrule__{pred_rule}_gtrule_{gt_rule}_w{ww}_s{step}_summary.txt"

                if not Path(output_file).exists():
                    cmd = f"CUDA_VISIBLE_DEVICES={DEVICE} python {EVAL_SCRIPT} --model {MODEL} --data {TEST_YT} --output_path {OUTPUT_PATH} --multi_frame --rule {pred_rule} --gt_rule {gt_rule} --window {ww} --step {step}"
                    #print(cmd)
                    os.system(cmd)

                fscore = read_fscore(output_file)

                if fscore > max_fscore:
                    max_fscore = fscore
                    max_file = output_file

                count += 1
                print(count,"/1980", "current_best_f1", max_fscore, max_file)
                #if count == 10:
                #    exit(0)

print("Summary")
print("MAX-Score",max_fscore)
print("file",max_file)
