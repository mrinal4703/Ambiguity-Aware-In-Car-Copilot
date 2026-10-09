import json
import requests

from sklearn.metrics import (
    accuracy_score,
    classification_report
)


API_URL = "http://127.0.0.1:8000/nlu/parse"


with open("data/test_dataset.json", "r") as file:
    dataset = json.load(file)


y_true = []
y_pred = []

action_correct = 0
ambiguity_correct = 0
valid_outputs = 0


for index, sample in enumerate(dataset):

    payload = {
        "session_id": f"evaluation_{index}",
        "utterance": sample["utterance"],
        "vehicle_context": sample["vehicle_context"]
    }

    try:
        response = requests.post(
            API_URL,
            json=payload,
            timeout=60
        )

        response.raise_for_status()
        output = response.json()

        valid_outputs += 1

        y_true.append(sample["expected_intent"])
        y_pred.append(output["intent"])

        predicted_actions = [
            item["action"]
            for item in output["action_candidates"]
        ]

        expected_action = sample["expected_action"]

        if expected_action is None:
            if not predicted_actions:
                action_correct += 1
        elif expected_action in predicted_actions:
            action_correct += 1

        if (
            output["ambiguity"]["is_ambiguous"]
            == sample["expected_ambiguity"]
        ):
            ambiguity_correct += 1

    except requests.RequestException as error:
        print(
            f"Request failed for sample {index}: {error}"
        )


total = len(dataset)

if y_true:
    print(
        "Intent accuracy:",
        accuracy_score(y_true, y_pred)
    )

    print(
        classification_report(
            y_true,
            y_pred,
            zero_division=0
        )
    )

print(
    "Action accuracy:",
    action_correct / total
)

print(
    "Ambiguity accuracy:",
    ambiguity_correct / total
)

print(
    "Valid API output rate:",
    valid_outputs / total
)