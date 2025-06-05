class _Secrets(dict):
    def __init__(self):
        super().__init__()
        self._secrets = {}

    def __getattr__(self, name):
        return self._secrets.get(name)

    def __setattr__(self, name, value):
        if name == "_secrets":
            super().__setattr__(name, value)
        else:
            self._secrets[name] = value

secrets = _Secrets()

session_state = {}

class _Sidebar:
    def expander(self, *_, **__):
        return self
    def markdown(self, *_):
        pass

sidebar = _Sidebar()

def __getattr__(name):
    def _stub(*_, **__):
        return None
    return _stub
