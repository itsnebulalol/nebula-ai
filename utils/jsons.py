import json


class JSONObject(object):
    def __init__(self, path: str) -> None:
        self.path = path  # TODO: not sure if pathlib is better but using str for now

    @staticmethod
    def __load__(data):
        return data

    def load_json(self):
        with open(self.path, "r") as f:
            result = JSONObject.__load__(json.loads(f.read()))
        return result

    def write_json(self, data) -> None:
        with open(self.path, "w") as f:
            json.dump(data, f, indent=4)


class ConfigJSON(JSONObject):
    def __init__(self) -> None:
        super().__init__("config/config.json")


class AIConfigJSON(JSONObject):
    def __init__(self) -> None:
        super().__init__("config/ai.json")
