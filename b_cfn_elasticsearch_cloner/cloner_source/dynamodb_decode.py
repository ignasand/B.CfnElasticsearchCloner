class DynamodbDecoder:
    RESERVED_FIELDS = [
        "uid",
        "_id",
        "_type",
        "_source",
        "_all",
        "_parent",
        "_fieldnames",
        "_routing",
        "_index",
        "_size",
        "_timestamp",
        "_ttl",
    ]

    @staticmethod
    def decode_json(node):
        data = {}
        data["M"] = node
        return DynamodbDecoder.decode_value(data, True)

    @staticmethod
    def decode_value(node, force_num=False):
        for key, value in list(node.items()):
            if key == "NULL":
                return None
            if key in ("S", "BOOL"):
                return value
            if key == "N":
                if force_num:
                    return float(value)
                return value
            if key == "M":
                data = {}
                for key1, value1 in list(value.items()):
                    if key1 in DynamodbDecoder.RESERVED_FIELDS:
                        key1 = key1.replace("_", "__", 1)
                    data[key1] = DynamodbDecoder.decode_value(value1, True)
                return data
            if key in ("BS", "L"):
                data = []
                for item in value:
                    data.append(DynamodbDecoder.decode_value(item))
                return data
            if key == "SS":
                data = []
                for item in value:
                    data.append(item)
                return data
            if key == "NS":
                data = []
                for item in value:
                    if force_num:
                        data.append(float(item))
                    else:
                        data.append(item)
                return data
