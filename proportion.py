import json
import matplotlib.pyplot as plt

def load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def count_responses(conversations):
    yes_count = 0
    no_count = 0
    other_count = 0

    for conversation in conversations:
        if conversation['from'] == 'gpt':
            value = conversation['value'].strip().lower()
            if value == 'yes':
                yes_count += 1
            elif value == 'no':
                no_count += 1
            else:
                other_count += 1

    return yes_count, no_count, other_count

def calculate_proportions(yes_count, no_count, other_count, total_count):
    yes_prop = (yes_count / total_count) * 100
    no_prop = (no_count / total_count) * 100
    other_prop = (other_count / total_count) * 100
    return yes_prop, no_prop, other_prop

def plot_comparison(file1_name, file2_name, yes1_prop, no1_prop, other1_prop, yes2_prop, no2_prop, other2_prop):
    categories = ['Yes', 'No', 'Other']
    proportions1 = [yes1_prop, no1_prop, other1_prop]
    proportions2 = [yes2_prop, no2_prop, other2_prop]

    x = range(len(categories))
    width = 0.35

    plt.bar([xi - width/2 for xi in x], proportions1, width, label=file1_name)
    plt.bar([xi + width/2 for xi in x], proportions2, width, label=file2_name)

    plt.xlabel('Response Types')
    plt.ylabel('Proportion (%)')
    plt.title('Comparison of Response Proportions')
    plt.xticks(x, categories)
    plt.legend()
    plt.show()

def main():
    file1_path = 'suspicious_activity_detection_llava_dataset_test_youtube_v3_0.5fps.json'  # Replace with your first JSON file path
    file2_path = 'suspicious_activity_detection_llava_dataset_test_youtube_v3_1fps_v2.json'  # Replace with your second JSON file path

    data1 = load_json(file1_path)
    data2 = load_json(file2_path)

    yes1, no1, other1 = count_responses([conv for entry in data1 for conv in entry['conversations']])
    yes2, no2, other2 = count_responses([conv for entry in data2 for conv in entry['conversations']])

    total1 = len([conv for entry in data1 for conv in entry['conversations'] if conv['from'] == 'gpt'])
    total2 = len([conv for entry in data2 for conv in entry['conversations'] if conv['from'] == 'gpt'])

    yes1_prop, no1_prop, other1_prop = calculate_proportions(yes1, no1, other1, total1)
    yes2_prop, no2_prop, other2_prop = calculate_proportions(yes2, no2, other2, total2)

    plot_comparison('test_youtube_v3_0.5fps', 'test_youtube_v3_1fps_v2', yes1_prop, no1_prop, other1_prop, yes2_prop, no2_prop, other2_prop)

if __name__ == "__main__":
    main()




[
  {
    "id": "1kioULfHjhg_000001.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000001.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000002.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000002.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000003.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000003.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000004.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000004.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000005.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000005.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000006.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000006.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000007.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000007.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "1kioULfHjhg_000008.png",
    "image": "test_videos_YT/videos_subsampled_1fps/1kioULfHjhg/000008.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "other"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000001.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000001.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "other"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000002.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000002.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "other"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000003.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000003.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "other"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000004.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000004.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000005.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000005.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000006.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000006.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000007.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000007.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
  },
  {
    "id": "2gY_H8Qszzs_000008.png",
    "image": "test_videos_YT/videos_subsampled_1fps/2gY_H8Qszzs/000008.png",
    "conversations": [
      {
        "from": "human",
        "value": "<image>\nAnalyze the provided image and determine if any of the persons present pose a potential security threat. For example, the person is trying to hide his face, carries a weapon, etc.\nAnswer Yes or No"
      },
      {
        "from": "gpt",
        "value": "yes"
      }
    ]
