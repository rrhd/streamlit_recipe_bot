class retry:
    def __init__(self, *_, **__):
        pass
    def __call__(self, fn):
        return fn
class retry_if_exception:
    def __init__(self, *_, **__):
        pass
class stop_after_attempt:
    def __init__(self, *_, **__):
        pass
